"""IA no Borges Core: interpreta a pergunta e redige a resposta a partir dos fatos já calculados.

A IA não calcula indicadores nem cria recomendações. Ela recebe os fatos (indicadores da conta, qualidade
dos dados, recomendações já geradas pelas regras) e devolve, em JSON validado:
- a resposta em português, usando só esses fatos;
- quais recomendações respondem à pergunta.

Salvaguardas:
- limite de gasto mensal verificado ANTES da chamada, pelo pior custo possível;
- todo número da resposta precisa existir nos fatos enviados; se não existir, a resposta é descartada;
- recusa, erro de rede ou resposta inválida: o Borges segue com a resposta das regras.
Dados enviados à Anthropic: nome do cliente, nomes de campanhas/anúncios e métricas agregadas. Nenhum
dado pessoal de leads.
"""
from __future__ import annotations

import json
import logging
import re
from decimal import Decimal
from typing import Any

import anthropic
from sqlalchemy.orm import Session

from app.ai import pricing
from app.ai.client import build_client
from app.ai.settings import get_settings_row, month_spend
from app.core import crypto
from app.models import AIUsage, Client

log = logging.getLogger(__name__)
MAX_TOKENS = 16000
PURPOSE = "analysis_narrative"

SYSTEM_PROMPT = """Você é o Borges Core, diretor estratégico de uma agência de tráfego pago. Você recebe, em JSON, \
fatos já calculados sobre as campanhas de um cliente e as recomendações geradas por regras auditáveis. \
Sua tarefa é responder à pergunta do gestor em português do Brasil, de forma direta e útil.

Regras:
- Use somente os fatos do JSON. Não invente números, campanhas, causas ou resultados.
- Ao citar um número, copie-o exatamente como aparece nos fatos (mesmo arredondamento e formato). Não calcule \
números novos (somas, diferenças, porcentagens): se um número não está nos fatos, descreva sem ele.
- Separe fato de hipótese: o que os dados mostram, o que provavelmente explica, e o que ainda precisa ser testado.
- Se os fatos não respondem à pergunta, diga isso e indique qual dado faltaria.
- Correlação não é causalidade. Receita não é lucro. Dado indisponível não é zero.
- Se os dados forem demonstrativos (is_demo), deixe isso claro.
- Seja conciso: no máximo 4 parágrafos curtos. Sem cabeçalhos nem tabelas.
- Em relevant_recommendation_ids, liste apenas ids que existem nos fatos e que respondem à pergunta, do mais \
importante para o menos importante; lista vazia se nenhuma responde."""

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "relevant_recommendation_ids": {"type": "array", "items": {"type": "integer"}},
    },
    "required": ["answer", "relevant_recommendation_ids"],
    "additionalProperties": False,
}

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


def unsupported_numbers(answer: str, facts_text: str) -> list[str]:
    """Números da resposta que não aparecem nos fatos. Contagens pequenas (até 99) são livres."""
    facts = numbers_in(facts_text)
    bad = []
    for tok in _NUMBER.findall(answer):
        values = _variants(tok)
        if any(v.is_integer() and 0 <= v < 100 for v in values):
            continue
        if not any(abs(v - f) <= max(0.011, abs(f) * 0.0005) for v in values for f in facts):
            bad.append(tok)
    return bad


def _record(db: Session, client: Client, run_id: int | None, model: str, status: str, detail: str | None,
            input_tokens: int = 0, output_tokens: int = 0, cost: Decimal = Decimal("0")) -> None:
    db.add(AIUsage(client_id=client.id, analysis_run_id=run_id, purpose=PURPOSE, model=model, status=status,
                   input_tokens=input_tokens, output_tokens=output_tokens, cost_usd=cost, detail=detail))
    db.flush()


def narrate(db: Session, client: Client, run_id: int | None, question: str, facts: dict[str, Any]
            ) -> dict[str, Any] | None:
    """Retorna {"answer", "relevant_ids", "model", "cost_usd"} ou None quando a IA não está ativa.

    Quando a IA está ativa mas não pôde ser usada, retorna {"error": motivo} (a análise segue pelas regras).
    """
    cfg = get_settings_row(db)
    if not cfg.enabled or not cfg.api_key_encrypted:
        return None
    model = cfg.model if cfg.model in pricing.PRICES else "claude-opus-5-5"
    facts_text = json.dumps(facts, ensure_ascii=False, default=str)
    user_text = f"Pergunta do gestor: {question}\n\nFatos (JSON):\n{facts_text}"

    estimate = pricing.worst_case(model, len(SYSTEM_PROMPT + user_text) // 3 + 500, MAX_TOKENS)
    spent = month_spend(db)
    cap = Decimal(cfg.monthly_cap_usd)
    if spent + estimate > cap:
        reason = (f"limite mensal de US$ {cap:.2f} atingido (gasto no mês: US$ {spent:.2f}; "
                  f"esta chamada poderia custar até US$ {estimate:.2f})")
        _record(db, client, run_id, model, "blocked_budget", reason)
        return {"error": f"IA não usada: {reason}."}

    try:
        api = build_client(crypto.decrypt(cfg.api_key_encrypted))
        # Reserva no servidor: se o modelo recusar por política, a própria API refaz o pedido em outro modelo.
        response = api.beta.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_text}],
            output_config={"effort": cfg.effort, "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except crypto.EncryptionUnavailable as exc:
        _record(db, client, run_id, model, "error", str(exc))
        return {"error": f"IA não usada: {exc}"}
    except anthropic.AuthenticationError:
        _record(db, client, run_id, model, "error", "chave de API recusada")
        return {"error": "IA não usada: a Anthropic recusou a chave de API."}
    except anthropic.RateLimitError:
        _record(db, client, run_id, model, "error", "limite de requisições da Anthropic")
        return {"error": "IA não usada: limite de requisições da Anthropic atingido. Tente mais tarde."}
    except anthropic.APIStatusError as exc:
        _record(db, client, run_id, model, "error", f"HTTP {exc.status_code}")
        return {"error": f"IA não usada: a Anthropic respondeu com erro (HTTP {exc.status_code})."}
    except anthropic.APIConnectionError:
        _record(db, client, run_id, model, "error", "falha de conexão")
        return {"error": "IA não usada: falha de conexão com a Anthropic."}

    usage = response.usage
    tokens_in = (usage.input_tokens or 0) + (getattr(usage, "cache_read_input_tokens", 0) or 0) \
        + (getattr(usage, "cache_creation_input_tokens", 0) or 0)
    tokens_out = usage.output_tokens or 0
    billed_model = response.model or model
    cost = pricing.cost(billed_model, tokens_in, tokens_out)

    def finish(status: str, detail: str | None) -> None:
        _record(db, client, run_id, billed_model, status, detail, tokens_in, tokens_out, cost)

    if response.stop_reason == "refusal":
        finish("refused", getattr(response.stop_details, "category", None))
        return {"error": "IA não usada: o modelo recusou o pedido."}
    if response.stop_reason == "max_tokens":
        finish("error", "resposta cortada (max_tokens)")
        return {"error": "IA não usada: a resposta ficou longa demais e foi cortada."}
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        data = json.loads(text)
        answer = str(data["answer"]).strip()
        ids = [int(i) for i in data["relevant_recommendation_ids"]]
    except (ValueError, KeyError, TypeError):
        finish("error", "JSON inválido")
        return {"error": "IA não usada: resposta em formato inválido."}

    bad = unsupported_numbers(answer, facts_text + " " + question)
    if bad or not answer:
        finish("rejected_validation", f"números fora dos fatos: {', '.join(bad[:5])}" if bad else "resposta vazia")
        return {"error": "Resposta da IA descartada: citou números que não estão nos dados"
                         + (f" ({', '.join(bad[:5])})." if bad else ".")}
    known = {r["id"] for r in facts.get("recommendations", [])}
    finish("ok", None)
    return {"answer": answer, "relevant_ids": [i for i in ids if i in known], "model": billed_model,
            "cost_usd": float(cost)}
