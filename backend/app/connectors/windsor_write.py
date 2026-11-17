"""Escrita nas plataformas pelo Windsor.ai (ações). Usada só para clientes reais com escrita ligada.

API (documentação oficial do Windsor.ai): POST https://connectors.windsor.ai/{conector}/actions?api_key=...
com corpo {"account", "action", "params"}; sucesso: {"result": "..."}; erros 400 (parâmetros), 403 (escrita
não habilitada no time), 404, 500. Ações e parâmetros conferidos na listagem real do Windsor.ai:
- facebook  set_campaign_budget {campaign_id, budget_type: daily, amount (centavos)}
- facebook  pause_ad {ad_id}
- google_ads pause_ad_group {ad_group_id}
Ações que aumentam gasto podem voltar com um confirmation_token (prévia): o Borges NÃO confirma sozinho;
a execução fica aguardando uma segunda confirmação humana. O nome do campo enviado de volta
(confirmation_token) segue a ferramenta oficial do Windsor.ai; a documentação REST não o descreve.

Verificação: relê o valor pelos dados do Windsor.ai. Esses dados têm cache (minutos a horas); se ainda não
refletem a mudança, a execução fica "aguardando verificação" e pode ser verificada depois.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import httpx

from app.connectors import windsor
from app.connectors.windsor import WindsorAuthError, WindsorClient, WindsorError
from app.core.config import get_settings

CONNECTOR = {"meta": "facebook", "google": "google_ads"}


@dataclass
class WriteOutcome:
    status: str  # accepted | needs_confirmation | failed
    detail: str
    response: dict[str, Any]
    confirmation_token: str | None = None


class WindsorWriter:
    def __init__(self, api_key: str, http: httpx.Client | None = None, base_url: str | None = None):
        self._key = api_key
        self._http = http or windsor.build_http_client()
        self._base = (base_url or get_settings().windsor_base_url).rstrip("/")
        self.reader = WindsorClient(api_key, http=self._http, base_url=self._base)

    def execute(self, platform: str, account: str, action: str, params: dict[str, Any],
                confirmation_token: str | None = None) -> WriteOutcome:
        body: dict[str, Any] = {"account": account, "action": action, "params": params}
        if confirmation_token:
            body["confirmation_token"] = confirmation_token
        try:
            resp = self._http.post(f"{self._base}/{CONNECTOR[platform]}/actions", params={"api_key": self._key},
                                   json=body)
        except httpx.HTTPError as exc:
            return WriteOutcome("failed", f"falha de rede ({type(exc).__name__})", {})
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {"result": data}
        safe = {k: v for k, v in data.items() if k != "api_key"}
        if resp.status_code == 403:
            return WriteOutcome("failed", "Escrita não habilitada no Windsor.ai (Team management) ou sem permissão.",
                                safe)
        if resp.status_code in (401,) or str(data.get("code", "")).lower() == "unauthorized":
            return WriteOutcome("failed", "Windsor.ai recusou a chave de API.", safe)
        if resp.status_code >= 400:
            msg = data.get("error") or data.get("detail") or data.get("result") or ""
            return WriteOutcome("failed", f"Windsor.ai rejeitou a ação (HTTP {resp.status_code}). {msg}"[:400], safe)
        token = data.get("confirmation_token")
        if token and not confirmation_token:
            return WriteOutcome("needs_confirmation", str(data.get("result") or data.get("preview") or
                                                          "A plataforma pediu confirmação para esta mudança."),
                                safe, confirmation_token=str(token))
        return WriteOutcome("accepted", str(data.get("result") or "Ação aceita pela plataforma."), safe)

    # --- releitura para verificação --------------------------------------------------------------

    def _rows(self, platform: str, fields: list[str], account: str) -> list[dict[str, Any]]:
        end = date.today()
        return self.reader.query(CONNECTOR[platform], fields, end - timedelta(days=2), end, [account])

    def read_meta_campaign_budget(self, account: str, campaign_id: str) -> float | None:
        """Orçamento diário atual na moeda (centavos convertidos). None se não encontrado."""
        rows = [r for r in self._rows("meta", ["date", "campaign_id", "campaign_daily_budget"], account)
                if str(r.get("campaign_id")) == campaign_id and r.get("campaign_daily_budget") is not None]
        if not rows:
            return None
        latest = max(rows, key=lambda r: str(r.get("date")))
        return round(float(latest["campaign_daily_budget"]) / 100, 2)

    def read_meta_ad_status(self, account: str, ad_id: str) -> str | None:
        rows = [r for r in self._rows("meta", ["date", "ad_id", "effective_status"], account)
                if str(r.get("ad_id")) == ad_id and r.get("effective_status")]
        return str(max(rows, key=lambda r: str(r.get("date")))["effective_status"]).lower() if rows else None

    def read_google_ad_group_status(self, account: str, ad_group_id: str) -> str | None:
        rows = [r for r in self._rows("google", ["date", "ad_group_id", "ad_group_status"], account)
                if str(r.get("ad_group_id")) == ad_group_id and r.get("ad_group_status")]
        return str(max(rows, key=lambda r: str(r.get("date")))["ad_group_status"]).lower() if rows else None


__all__ = ["WindsorWriter", "WriteOutcome", "WindsorError", "WindsorAuthError"]
