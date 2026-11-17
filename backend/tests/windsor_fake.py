"""Servidor Windsor.ai falso para testes.

O formato das linhas (nomes de campos, nulls, centavos, casas decimais) reproduz o que a API real
devolve; nomes e IDs são fictícios. De propósito, ele IGNORA o filtro de contas e devolve linhas de
todas as contas da chave, para provar que o conector descarta o que não foi selecionado.
"""
from datetime import date, timedelta

import httpx

VALID_KEY = "wk_test_valid_key_1234"
META_A, META_OTHER, GOOGLE_A = "1000000000000001", "2000000000000002", "111-222-3333"


def _days(request: httpx.Request) -> list[date]:
    start = date.fromisoformat(request.url.params["date_from"])
    end = date.fromisoformat(request.url.params["date_to"])
    # A plataforma só tem dados até ontem.
    last = min(end, date.today() - timedelta(days=1))
    return [start + timedelta(days=i) for i in range((last - start).days + 1)]


def meta_campaign_row(day: date, account=META_A, name="[Studio] [Eng-WPP] [Pilates]", campaign_id="c-meta-1",
                      currency="BRL", **over) -> dict:
    row = {"date": day.isoformat(), "account_id": account, "account_name": f"CA {account[-4:]}",
           "account_currency": currency, "campaign": name, "campaign_id": campaign_id, "campaign_status": "ACTIVE",
           "campaign_objective": "OUTCOME_ENGAGEMENT", "campaign_daily_budget": 2100, "spend": 20.0,
           "impressions": 1000, "reach": 800, "clicks": 30, "link_clicks": 12, "actions_lead": None,
           "actions_onsite_conversion_messaging_conversation_started_7d": 4, "actions_purchase": None,
           "action_values_purchase": None, "datasource": "facebook"}
    return {**row, **over}


def meta_ad_rows(day: date, account=META_A, campaign_id="c-meta-1") -> list[dict]:
    base = {"date": day.isoformat(), "account_id": account, "campaign_id": campaign_id, "adset_id": "as-1",
            "adset_name": "[Pub Frio]", "actions_lead": None, "actions_purchase": None,
            "action_values_purchase": None, "datasource": "facebook"}
    return [
        {**base, "ad_id": "ad-1", "ad_name": "[Ads - Vídeo]", "spend": 14.5, "impressions": 700, "clicks": 22,
         "link_clicks": 9, "actions_onsite_conversion_messaging_conversation_started_7d": 3},
        {**base, "ad_id": "ad-2", "ad_name": "[Ads - Imagem]", "spend": 5.5, "impressions": 300, "clicks": 8,
         "link_clicks": None, "actions_onsite_conversion_messaging_conversation_started_7d": 1},
    ]


def google_campaign_row(day: date, **over) -> dict:
    row = {"date": day.isoformat(), "account_id": GOOGLE_A, "account_name": "Studio Pilates",
           "account_currency_code": "BRL", "campaign": "[Studio] [Matriculas]", "campaign_id": "9001",
           "campaign_status": "ENABLED", "campaign_type": "SEARCH", "spend": 19.3987, "impressions": 66, "clicks": 9,
           "conversions": 2, "conversion_value": 0, "datasource": "google_ads"}
    return {**row, **over}


def google_adgroup_row(day: date) -> dict:
    return {"date": day.isoformat(), "account_id": GOOGLE_A, "campaign_id": "9001", "ad_group_id": "ag-1",
            "ad_group_name": "[Pilates]", "spend": 19.3987, "impressions": 66, "clicks": 9, "conversions": 2,
            "conversion_value": 0, "datasource": "google_ads"}


class FakeWindsor:
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.fail_with: int | None = None  # força um status HTTP em todas as respostas

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.params.get("api_key") != VALID_KEY:
            return httpx.Response(401, json={"error": "Invalid API key"})
        if self.fail_with:
            return httpx.Response(self.fail_with, text="upstream error")
        connector = request.url.path.strip("/")
        fields = set(request.url.params["fields"].split(","))
        days = _days(request)
        if "date" not in fields:  # descoberta de contas
            if connector == "facebook":
                rows = [{"account_id": META_A, "account_name": "CA Studio", "account_currency": "BRL", "spend": 157.08},
                        {"account_id": META_OTHER, "account_name": "CA Outro Cliente", "account_currency": "BRL",
                         "spend": 421.66}]
            else:
                rows = [{"account_id": GOOGLE_A, "account_name": None, "account_currency_code": "BRL", "spend": 129.78}]
        elif connector == "facebook" and "ad_id" in fields:
            rows = [r for d in days for r in meta_ad_rows(d) + meta_ad_rows(d, META_OTHER, "c-other")]
        elif connector == "facebook":
            rows = [r for d in days for r in (meta_campaign_row(d),
                                              meta_campaign_row(d, META_OTHER, "Campanha de outro cliente", "c-other",
                                                                spend=999.0))]
        elif "ad_group_id" in fields:
            rows = [google_adgroup_row(d) for d in days]
        else:
            rows = [google_campaign_row(d) for d in days]
        return httpx.Response(200, json={"data": rows})

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))
