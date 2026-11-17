"""IA no Borges Core: salvaguardas (limite de gasto, números inventados, falhas) e formato da chamada."""
import json
from decimal import Decimal
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from sqlalchemy import select

from app.ai import narrator, pricing
from app.models import AIUsage

KEY = "sk-ant-test-0000000000000000000000"


def enable(admin, cap="10", key=KEY, model="claude-opus-5-5"):
    r = admin.put("/api/ai/settings", json={"enabled": True, "model": model, "effort": "medium",
                                             "monthly_cap_usd": cap, "api_key": key})
    assert r.status_code == 200, r.text
    return r.json()


class FakeAnthropic:
    """Imita client.beta.messages.create. `reply` decide o texto e o motivo de parada."""

    def __init__(self, reply):
        self.calls = []
        self.reply = reply
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        facts = json.loads(kwargs["messages"][0]["content"].split("Fatos (JSON):\n", 1)[1])
        text, stop = self.reply(facts)
        return SimpleNamespace(
            model=kwargs["model"], stop_reason=stop, stop_details=None,
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(input_tokens=12_000, output_tokens=1_500, cache_read_input_tokens=0,
                                  cache_creation_input_tokens=0),
        )


def grounded(facts):
    """Resposta que só usa números presentes nos fatos."""
    first = facts["recommendations"][0]
    text = (f"No período {facts['period']}, o investimento foi de {facts['account']['investimento']} e o CAC real "
            f"ficou em {facts['account']['cac_real']}. O ponto mais urgente: {first['title']}.")
    return json.dumps({"answer": text, "relevant_recommendation_ids": [first["id"], 999_999]}), "end_turn"


@pytest.fixture()
def fake(monkeypatch):
    holder = {}

    def build(api_key):
        assert api_key == KEY  # a chave chega decifrada só no momento da chamada
        return holder["client"]

    monkeypatch.setattr(narrator, "build_client", build)
    return holder


def analyze(http, cid, q="Como está o CAC e o que devo priorizar?"):
    r = http.post(f"/api/clients/{cid}/analyses", json={"question": q, "days": 30})
    assert r.status_code == 201, r.text
    return r.json()


def test_numbers_guard():
    facts = json.dumps({"investimento": "R$ 12.205,75", "roas": "3,61", "taxa": "20,1%", "raw": 1702.5})
    assert narrator.unsupported_numbers("Investiu R$ 12.205,75 com ROAS 3,61 e taxa de 20,1%.", facts) == []
    assert narrator.unsupported_numbers("Foram 7 campanhas em 30 dias; R$ 1.702,50 no remarketing.", facts) == []
    assert narrator.unsupported_numbers("O ROAS subiu para 4,25 e o CAC caiu R$ 18,40.", facts) == ["4,25", "18,40"]


def test_pricing_and_worst_case():
    assert pricing.cost("claude-opus-5-5", 1_000_000, 100_000) == Decimal("6.00")  # 4 + 2
    assert pricing.cost("modelo-desconhecido", 0, 1_000_000) == Decimal("25.00")  # o mais caro da tabela
    assert pricing.worst_case("claude-haiku-5-5", 0, 16_000) == Decimal("0.4")  # reserva pode ser mais cara


def test_ai_is_off_by_default_and_rules_answer_is_used(admin, demo_client):
    a = analyze(admin, demo_client["id"])
    assert a["summary"]["ai"] == {"used": False} and "Analisei" in a["summary"]["answer"]
    s = admin.get("/api/ai/settings").json()
    assert s["enabled"] is False and s["configured"] is False and s["model"] == "claude-opus-5-5"


def test_settings_require_admin_key_and_never_return_it(admin, db):
    from tests.conftest import login, make_user
    make_user(db, "gestor@example.com", "manager")
    gestor = login("gestor@example.com")
    body = {"enabled": True, "model": "claude-opus-5-5", "effort": "medium", "monthly_cap_usd": "10"}
    assert gestor.put("/api/ai/settings", json={**body, "api_key": KEY}).status_code == 403
    assert admin.put("/api/ai/settings", json=body).status_code == 422  # ativar sem chave
    assert admin.put("/api/ai/settings", json={**body, "model": "gpt-qualquer", "api_key": KEY}).status_code == 422
    out = enable(admin)
    assert out["configured"] and out["key_hint"] == KEY[-4:] and KEY not in json.dumps(out)
    assert KEY not in admin.get("/api/audit").text
    # salvar de novo sem chave mantém a chave atual
    again = admin.put("/api/ai/settings", json={**body, "monthly_cap_usd": "25"}).json()
    assert again["configured"] and again["monthly_cap_usd"] == 25.0


def test_grounded_answer_is_used_and_cost_recorded(admin, demo_client, fake, db):
    enable(admin)
    fake["client"] = FakeAnthropic(grounded)
    a = analyze(admin, demo_client["id"])
    ai = a["summary"]["ai"]
    assert ai["used"] and ai["model"] == "claude-opus-5-5" and "Analisei" in ai["rules_answer"]
    assert a["summary"]["answer"].startswith("No período")
    first = a["recommendations"][0]["id"]
    assert a["summary"]["matched_ids"] == [first]  # id inexistente (999999) descartado
    call = fake["client"].calls[0]
    assert call["output_config"]["effort"] == "medium" and call["fallbacks"] == "default"
    assert call["output_config"]["format"]["type"] == "json_schema"
    usage = db.scalar(select(AIUsage))
    assert usage.status == "ok" and usage.cost_usd == Decimal("0.0780")  # 12k x $4 + 1,5k x $20 por milhão
    assert admin.get("/api/ai/settings").json()["month_spend_usd"] == pytest.approx(0.078)


def test_invented_numbers_are_rejected(admin, demo_client, fake, db):
    enable(admin)
    fake["client"] = FakeAnthropic(lambda f: (json.dumps(
        {"answer": "O CAC vai cair para R$ 17,35 se você escalar.", "relevant_recommendation_ids": []}), "end_turn"))
    s = analyze(admin, demo_client["id"])["summary"]
    assert s["ai"]["used"] is False and "17,35" in s["ai"]["note"]
    assert s["answer"].startswith("Analisei")  # resposta das regras
    assert db.scalar(select(AIUsage)).status == "rejected_validation"


def test_budget_cap_blocks_the_call_before_spending(admin, demo_client, fake, db):
    enable(admin, cap="0.10")  # o pior caso de uma chamada (~US$ 0,46) passa do limite
    fake["client"] = FakeAnthropic(grounded)
    s = analyze(admin, demo_client["id"])["summary"]
    assert s["ai"]["used"] is False and "limite mensal" in s["ai"]["note"]
    assert fake["client"].calls == []
    row = db.scalar(select(AIUsage))
    assert row.status == "blocked_budget" and row.cost_usd == 0


def test_refusal_and_api_errors_fall_back_to_rules(admin, demo_client, fake, monkeypatch):
    enable(admin)
    fake["client"] = FakeAnthropic(lambda f: ("", "refusal"))
    assert "recusou" in analyze(admin, demo_client["id"])["summary"]["ai"]["note"]

    def boom(api_key):
        raise anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    monkeypatch.setattr(narrator, "build_client", boom)
    s = analyze(admin, demo_client["id"])["summary"]
    assert "falha de conexão" in s["ai"]["note"] and s["answer"].startswith("Analisei")


def test_real_sdk_request_shape(monkeypatch, admin, demo_client):
    """Usa o SDK oficial com um servidor falso: valida o que de fato sai na requisição HTTP."""
    seen = {}

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen["path"] = request.url.path
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        facts = json.loads(seen["body"]["messages"][0]["content"].split("Fatos (JSON):\n", 1)[1])
        text, _ = grounded(facts)
        return httpx2.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": text}], "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 9000, "output_tokens": 800}})

    def build(api_key):
        return anthropic.Anthropic(api_key=api_key, base_url="https://anthropic.test", max_retries=0,
                                   http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler)))
    monkeypatch.setattr(narrator, "build_client", build)
    enable(admin)
    s = analyze(admin, demo_client["id"])["summary"]
    assert s["ai"]["used"], s["ai"]
    body, headers = seen["body"], seen["headers"]
    # o SDK 2.x envia a chave como Bearer no cabeçalho Authorization
    assert seen["path"] == "/v1/messages" and headers["authorization"] == f"Bearer {KEY}"
    assert "server-side-fallback-2026-07-01" in headers["anthropic-beta"]
    assert body["model"] == "claude-opus-5-5" and body["max_tokens"] == 16000 and body["fallbacks"] == "default"
    assert body["output_config"]["effort"] == "medium"
    assert body["output_config"]["format"]["schema"]["required"] == ["answer", "relevant_recommendation_ids"]
    assert "temperature" not in body and "thinking" not in body
