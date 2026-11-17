"""Conector Windsor.ai — SOMENTE LEITURA.

Windsor.ai agrega as plataformas de anúncios e devolve linhas agregadas pelas dimensões pedidas.
Este módulo tem duas partes:

- `WindsorClient`: transporte HTTP (autenticação, tentativas, erros). É o ÚNICO lugar que conhece o
  formato da requisição.
- `WindsorConnector`: normalização para o contrato do Borges (`connectors/base.py`).

Os nomes de campos abaixo foram conferidos contra o catálogo real do Windsor.ai (Meta e Google Ads).

Decisões de normalização (todas testadas em tests/test_windsor.py):
- Meta devolve `campaign_daily_budget` em centavos -> dividido por 100.
- Meta omite (null) ações que não ocorreram. Em uma linha com entrega, null em uma contagem de ação
  significa zero. Em métricas de entrega (impressões, alcance), null permanece indisponível.
- "Leads" na Meta = leads + conversas iniciadas por mensagem (campanhas de WhatsApp).
- No Google, `conversions` são as conversões primárias da conta; entram como leads. Não há como saber
  por esta fonte se são compras, então compras atribuídas ficam indisponíveis.
- O nome da campanha é uma dimensão: se ele muda no meio do período, a mesma campanha/dia vem em
  duas linhas. As linhas são somadas pelo ID e o fato é reportado.
- Alcance é pedido no nível da campanha (não é somável entre anúncios).
- Uma chave Windsor costuma enxergar contas de vários clientes. Além de pedir só as contas
  selecionadas, toda linha de conta não selecionada é descartada aqui (defesa em profundidade).
"""
from __future__ import annotations

import time
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

import httpx

from app.connectors.base import (
    AdRecord,
    AdSetRecord,
    BreakdownRecord,
    CampaignRecord,
    ConnectionStatus,
    MetricRecord,
    Payload,
)
from app.core.config import get_settings

PLATFORMS = {"meta": "facebook", "google": "google_ads"}

META_CAMPAIGN_FIELDS = [
    "date", "account_id", "account_name", "account_currency", "campaign", "campaign_id", "campaign_status",
    "campaign_objective", "campaign_daily_budget", "spend", "impressions", "reach", "clicks", "link_clicks",
    "actions_lead", "actions_onsite_conversion_messaging_conversation_started_7d", "actions_purchase",
    "action_values_purchase",
]
META_AD_FIELDS = [
    "date", "account_id", "campaign_id", "adset_id", "adset_name", "ad_id", "ad_name", "spend", "impressions",
    "clicks", "link_clicks", "actions_lead", "actions_onsite_conversion_messaging_conversation_started_7d",
    "actions_purchase", "action_values_purchase",
]
GOOGLE_CAMPAIGN_FIELDS = [
    "date", "account_id", "account_name", "account_currency_code", "campaign", "campaign_id", "campaign_status",
    "campaign_type", "spend", "impressions", "clicks", "conversions", "conversion_value",
]
GOOGLE_ADGROUP_FIELDS = [
    "date", "account_id", "campaign_id", "ad_group_id", "ad_group_name", "spend", "impressions", "clicks",
    "conversions", "conversion_value",
]
ACCOUNT_FIELDS = {"meta": ["account_id", "account_name", "account_currency", "spend"],
                  "google": ["account_id", "account_name", "account_currency_code", "spend"]}

STATUS = {"ACTIVE": "active", "ENABLED": "active", "PAUSED": "paused", "ARCHIVED": "archived", "DELETED": "removed",
          "REMOVED": "removed"}


class WindsorError(Exception):
    """Falha ao consultar o Windsor.ai. A mensagem é segura para exibir (nunca contém a chave)."""


class WindsorAuthError(WindsorError):
    pass


def build_http_client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(120.0, connect=10.0))


class WindsorClient:
    MAX_ATTEMPTS = 3

    def __init__(self, api_key: str, http: httpx.Client | None = None, base_url: str | None = None,
                 sleep=time.sleep):
        self._api_key = api_key
        self._http = http or build_http_client()
        self._base = (base_url or get_settings().windsor_base_url).rstrip("/")
        self._sleep = sleep

    def query(self, connector: str, fields: list[str], start: date, end: date,
              accounts: list[str] | None = None) -> list[dict[str, Any]]:
        params = {"api_key": self._api_key, "date_from": start.isoformat(), "date_to": end.isoformat(),
                  "fields": ",".join(fields)}
        if accounts:
            params["select_accounts"] = ",".join(accounts)
        last = "sem resposta"
        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                resp = self._http.get(f"{self._base}/{connector}", params=params)
            except httpx.HTTPError as exc:
                # type(exc).__name__ apenas: a mensagem do httpx inclui a URL, que contém a chave.
                last = f"falha de rede ({type(exc).__name__})"
            else:
                if resp.status_code in (401, 403):
                    raise WindsorAuthError("Windsor.ai recusou a chave de API (não autorizada).")
                if resp.status_code == 429 or resp.status_code >= 500:
                    last = f"HTTP {resp.status_code}"
                elif resp.status_code >= 400:
                    raise WindsorError(f"Windsor.ai rejeitou a consulta a {connector} (HTTP {resp.status_code}).")
                else:
                    return self._rows(resp, connector)
            if attempt < self.MAX_ATTEMPTS:
                self._sleep(2 ** attempt)
        raise WindsorError(f"Windsor.ai indisponível para {connector} após {self.MAX_ATTEMPTS} tentativas ({last}).")

    @staticmethod
    def _rows(resp: httpx.Response, connector: str) -> list[dict[str, Any]]:
        try:
            body = resp.json()
        except ValueError as exc:
            raise WindsorError(f"Resposta do Windsor.ai para {connector} não é JSON.") from exc
        rows = body.get("data") if isinstance(body, dict) else body
        if not isinstance(rows, list) or not all(isinstance(r, dict) for r in rows):
            raise WindsorError(f"Resposta do Windsor.ai para {connector} em formato inesperado.")
        return rows


# --- normalização ---------------------------------------------------------------------------------

def _money(v: Any) -> Decimal | None:
    return None if v is None else Decimal(str(v)).quantize(Decimal("0.01"))


def _int(v: Any) -> int | None:
    return None if v is None else int(round(float(v)))


def _count(v: Any, delivered: bool) -> int | None:
    """Contagem de ação: null em linha com entrega = zero; sem entrega = indisponível."""
    if v is None:
        return 0 if delivered else None
    return int(round(float(v)))


def _add(a, b):
    return b if a is None else a if b is None else a + b


def _norm_account(platform: str, external_id: Any) -> str:
    return str(external_id).strip()


class WindsorConnector:
    source = "windsor"
    sales_source = None  # Windsor.ai entrega dados de mídia; vendas confirmadas vêm do CRM (Fase 5)
    is_demo = False

    def __init__(self, client: WindsorClient, accounts: list[dict[str, Any]], currency: str = "BRL"):
        self.client = client
        self.currency = currency
        self.accounts: dict[str, set[str]] = defaultdict(set)
        for a in accounts:
            self.accounts[a["platform"]].add(_norm_account(a["platform"], a["external_id"]))

    # -- conexão e descoberta ------------------------------------------------------------------

    def check(self) -> ConnectionStatus:
        try:
            found = self.discover_accounts(days=7)
        except WindsorAuthError as exc:
            return ConnectionStatus(ok=False, detail=str(exc))
        except WindsorError as exc:
            return ConnectionStatus(ok=False, detail=str(exc))
        return ConnectionStatus(ok=True, can_read=True, can_write=False,
                                detail=f"Leitura confirmada. {len(found)} conta(s) com dados nos últimos 7 dias.")

    def discover_accounts(self, days: int = 30, today: date | None = None) -> list[dict[str, Any]]:
        """Contas visíveis para a chave. Só aparecem contas com dados no período consultado."""
        from datetime import timedelta

        end = today or date.today()
        out = []
        for platform, connector in PLATFORMS.items():
            for r in self.client.query(connector, ACCOUNT_FIELDS[platform], end - timedelta(days=days), end):
                if r.get("account_id") is None:
                    continue
                out.append({
                    "platform": platform,
                    "external_id": _norm_account(platform, r["account_id"]),
                    "name": r.get("account_name") or str(r["account_id"]),
                    "currency": r.get("account_currency") or r.get("account_currency_code"),
                    "spend": float(r["spend"]) if r.get("spend") is not None else None,
                })
        return sorted(out, key=lambda a: (a["platform"], a["name"].lower()))

    # -- leitura -------------------------------------------------------------------------------

    def fetch(self, start: date, end: date) -> Payload:
        payload = Payload()
        if self.accounts.get("meta"):
            ids = sorted(self.accounts["meta"])
            self._campaign_level(payload, "meta", self.client.query("facebook", META_CAMPAIGN_FIELDS, start, end, ids))
            self._breakdown(payload, "meta", self.client.query("facebook", META_AD_FIELDS, start, end, ids))
        if self.accounts.get("google"):
            ids = sorted(self.accounts["google"])
            self._campaign_level(payload, "google",
                                 self.client.query("google_ads", GOOGLE_CAMPAIGN_FIELDS, start, end, ids))
            self._breakdown(payload, "google",
                            self.client.query("google_ads", GOOGLE_ADGROUP_FIELDS, start, end, ids))
        return payload

    def _allowed(self, payload: Payload, platform: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kept = [r for r in rows if _norm_account(platform, r.get("account_id")) in self.accounts[platform]]
        if len(kept) != len(rows):
            payload.issues.append(f"{len(rows) - len(kept)} linha(s) de contas não selecionadas foram descartadas "
                                  f"({platform}).")
        return kept

    def _metrics(self, platform: str, r: dict[str, Any]) -> dict[str, Any]:
        delivered = bool(r.get("impressions"))
        if platform == "meta":
            leads = _add(_count(r.get("actions_lead"), delivered),
                         _count(r.get("actions_onsite_conversion_messaging_conversation_started_7d"), delivered))
            return {
                "spend": _money(r.get("spend")), "impressions": _int(r.get("impressions")),
                "clicks": _int(r.get("clicks")), "link_clicks": _count(r.get("link_clicks"), delivered),
                "leads": leads, "attributed_purchases": _count(r.get("actions_purchase"), delivered),
                "attributed_revenue": _money(r.get("action_values_purchase")) if r.get("action_values_purchase")
                is not None else (Decimal("0.00") if delivered else None),
            }
        return {
            "spend": _money(r.get("spend")), "impressions": _int(r.get("impressions")), "clicks": _int(r.get("clicks")),
            "link_clicks": None, "leads": _int(r.get("conversions")), "attributed_purchases": None,
            "attributed_revenue": _money(r.get("conversion_value")),
        }

    def _campaign_level(self, payload: Payload, platform: str, rows: list[dict[str, Any]]) -> None:
        skipped_currency: set[str] = set()
        merged: dict[tuple[str, date], dict[str, Any]] = {}
        campaigns: dict[str, CampaignRecord] = {}
        renamed: set[str] = set()
        for r in self._allowed(payload, platform, rows):
            if r.get("campaign_id") is None or r.get("date") is None:
                continue
            currency = r.get("account_currency") or r.get("account_currency_code")
            account = _norm_account(platform, r["account_id"])
            if currency and currency != self.currency:
                skipped_currency.add(f"{r.get('account_name') or account} ({currency})")
                continue
            cid = str(r["campaign_id"])
            budget = r.get("campaign_daily_budget") if platform == "meta" else None
            previous = campaigns.get(cid)
            if previous and previous.name != (r.get("campaign") or cid):
                renamed.add(cid)
            campaigns[cid] = CampaignRecord(
                platform=platform, account_external_id=account, account_name=r.get("account_name") or account,
                external_id=cid, name=r.get("campaign") or cid,
                objective=r.get("campaign_objective") or r.get("campaign_type"),
                status=STATUS.get(str(r.get("campaign_status") or "").upper(), "unknown"),
                daily_budget=(Decimal(str(budget)) / 100).quantize(Decimal("0.01")) if budget else None,
                currency=currency,
            )
            day = date.fromisoformat(str(r["date"])[:10])
            m = self._metrics(platform, r)
            m["reach"] = _int(r.get("reach")) if platform == "meta" else None
            slot = merged.get((cid, day))
            merged[(cid, day)] = m if slot is None else {k: _add(slot[k], v) for k, v in m.items()}
        if renamed:
            payload.issues.append(f"{len(renamed)} campanha(s) mudaram de nome no período; as linhas foram somadas "
                                  "pelo ID (o alcance desses dias fica superestimado).")
        for label in sorted(skipped_currency):
            payload.issues.append(f"Conta {label} ignorada: moeda diferente da moeda do cliente ({self.currency}). "
                                  "Não há conversão de câmbio.")
        payload.campaigns.extend(campaigns.values())
        payload.metrics.extend(
            MetricRecord(campaign_external_id=cid, date=day, **m) for (cid, day), m in merged.items())

    def _breakdown(self, payload: Payload, platform: str, rows: list[dict[str, Any]]) -> None:
        known = {c.external_id for c in payload.campaigns}
        set_key, ad_key = ("adset_id", "ad_id") if platform == "meta" else ("ad_group_id", None)
        set_name = "adset_name" if platform == "meta" else "ad_group_name"
        sets: dict[str, AdSetRecord] = {}
        ads: dict[str, AdRecord] = {}
        merged: dict[tuple[str, str, str | None, date], dict[str, Any]] = {}
        for r in self._allowed(payload, platform, rows):
            cid = str(r.get("campaign_id"))
            if cid not in known or r.get(set_key) is None or r.get("date") is None:
                continue  # campanhas ignoradas (ex.: moeda) e campanhas sem grupo (ex.: Performance Max)
            sid = str(r[set_key])
            sets[sid] = AdSetRecord(cid, sid, r.get(set_name) or sid)
            aid = str(r[ad_key]) if ad_key and r.get(ad_key) is not None else None
            if aid:
                ads[aid] = AdRecord(sid, aid, r.get("ad_name") or aid)
            key = (cid, sid, aid, date.fromisoformat(str(r["date"])[:10]))
            m = self._metrics(platform, r)
            slot = merged.get(key)
            merged[key] = m if slot is None else {k: _add(slot[k], v) for k, v in m.items()}
        payload.ad_sets.extend(sets.values())
        payload.ads.extend(ads.values())
        payload.breakdown.extend(
            BreakdownRecord(cid, sid, aid, day, **m) for (cid, sid, aid, day), m in merged.items())
