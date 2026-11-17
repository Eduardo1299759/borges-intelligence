"""Chamada estruturada à IA com as salvaguardas do Borges, comum a todos os usos.

- só roda com a IA ativada e chave cadastrada;
- confere o pior custo possível contra o limite mensal ANTES de chamar;
- pede saída em JSON validado por esquema;
- reserva no servidor (fallbacks) para recusas por política;
- opcionalmente descarta a resposta se ela citar números que não estão nos fatos enviados;
- registra tokens e custo de toda tentativa em ai_usage.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import anthropic
from sqlalchemy.orm import Session

from app.ai import pricing
from app.ai.client import build_client
from app.ai.settings import get_settings_row, month_spend
from app.core import crypto
from app.models import AIUsage

MAX_TOKENS = 16000
_NUMBER = re.compile(r"\d[\d.,]*\d|\d")


def _variants(token: str) -> set[float]:
    """Um número escrito pode estar em formato brasileiro (1.234,56) ou inglês (1,234.56 / 1234.56)."""
    out: set[float] = set()
    for candidate in (token.replace(".", "").replace(",", "."), token.replace(",", "")):
        try:
            out.add(float(candidate))
        except ValueError:
            pass
    return out


def numbers_in(text: str) -> set[float]:
    found: set[float] = set()
    for tok in _NUMBER.findall(text):
        found |= _variants(tok)
    return found


def unsupported_numbers(text: str, facts_text: str) -> list[str]:
    """Números do texto que não aparecem nos fatos. Contagens pequenas (até 99) são livres."""
    facts = numbers_in(facts_text)
    bad = []
    for tok in _NUMBER.findall(text):
        values = _variants(tok)
        if any(v.is_integer() and 0 <= v < 100 for v in values):
            continue
        if not any(abs(v - f) <= max(0.011, abs(f) * 0.0005) for v in values for f in facts):
            bad.append(tok)
    return bad


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


@dataclass
class AIResult:
    data: dict[str, Any] | None = None
    model: str | None = None
    cost_usd: float = 0.0
    error: str | None = None  # motivo (em português) quando a IA estava ativa mas não pôde ser usada

    @property
    def ok(self) -> bool:
        return self.data is not None


def enabled(db: Session) -> bool:
    cfg = get_settings_row(db)
    return bool(cfg.enabled and cfg.api_key_encrypted)


def run_structured(db: Session, *, purpose: str, client_id: int | None, system: str, user_text: str,
                   schema: dict[str, Any], guard_numbers_against: str | None = None,
                   analysis_run_id: int | None = None) -> AIResult | None:
    """None quando a IA está desligada. Senão, AIResult com dados validados ou com o motivo da falha."""
    cfg = get_settings_row(db)
    if not cfg.enabled or not cfg.api_key_encrypted:
        return None
    model = cfg.model if cfg.model in pricing.PRICES else "claude-opus-5-5"

    def record(status: str, detail: str | None, used_model: str = model, tokens_in: int = 0, tokens_out: int = 0,
               cost: Decimal = Decimal("0")) -> None:
        db.add(AIUsage(client_id=client_id, analysis_run_id=analysis_run_id, purpose=purpose, model=used_model,
                       status=status, input_tokens=tokens_in, output_tokens=tokens_out, cost_usd=cost, detail=detail))
        db.flush()

    estimate = pricing.worst_case(model, len(system + user_text) // 3 + 500, MAX_TOKENS)
    spent, cap = month_spend(db), Decimal(cfg.monthly_cap_usd)
    if spent + estimate > cap:
        reason = (f"limite mensal de US$ {cap:.2f} atingido (gasto no mês: US$ {spent:.2f}; "
                  f"esta chamada poderia custar até US$ {estimate:.2f})")
        record("blocked_budget", reason)
        return AIResult(error=f"IA não usada: {reason}.")

    try:
        api = build_client(crypto.decrypt(cfg.api_key_encrypted))
        response = api.beta.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user_text}],
            output_config={"effort": cfg.effort, "format": {"type": "json_schema", "schema": schema}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except crypto.EncryptionUnavailable as exc:
        record("error", str(exc))
        return AIResult(error=f"IA não usada: {exc}")
    except anthropic.AuthenticationError:
        record("error", "chave de API recusada")
        return AIResult(error="IA não usada: a Anthropic recusou a chave de API.")
    except anthropic.RateLimitError:
        record("error", "limite de requisições da Anthropic")
        return AIResult(error="IA não usada: limite de requisições da Anthropic atingido. Tente mais tarde.")
    except anthropic.APIStatusError as exc:
        record("error", f"HTTP {exc.status_code}")
        return AIResult(error=f"IA não usada: a Anthropic respondeu com erro (HTTP {exc.status_code}).")
    except anthropic.APIConnectionError:
        record("error", "falha de conexão")
        return AIResult(error="IA não usada: falha de conexão com a Anthropic.")

    usage = response.usage
    tokens_in = (usage.input_tokens or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0) \
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
    tokens_out = usage.output_tokens or 0
    billed_model = response.model or model
    cost = pricing.cost(billed_model, tokens_in, tokens_out)

    def finish(status: str, detail: str | None) -> None:
        record(status, detail, billed_model, tokens_in, tokens_out, cost)

    if response.stop_reason == "refusal":
        finish("refused", getattr(response.stop_details, "category", None))
        return AIResult(error="IA não usada: o modelo recusou o pedido.", cost_usd=float(cost))
    if response.stop_reason == "max_tokens":
        finish("error", "resposta cortada (max_tokens)")
        return AIResult(error="IA não usada: a resposta ficou longa demais e foi cortada.", cost_usd=float(cost))
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError
    except ValueError:
        finish("error", "JSON inválido")
        return AIResult(error="IA não usada: resposta em formato inválido.", cost_usd=float(cost))

    if guard_numbers_against is not None:
        bad = [n for s in _strings(data) for n in unsupported_numbers(s, guard_numbers_against)]
        if bad:
            finish("rejected_validation", f"números fora dos fatos: {', '.join(bad[:5])}")
            return AIResult(error=f"Resposta da IA descartada: citou números que não estão nos dados "
                                  f"({', '.join(bad[:5])}).", cost_usd=float(cost))
    finish("ok", None)
    return AIResult(data=data, model=billed_model, cost_usd=float(cost))
