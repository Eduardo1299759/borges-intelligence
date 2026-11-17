"""Fase 5: importação de vendas/leads (LGPD), funil, regras comerciais, verificação de página e escrita real."""
import socket
from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.models import Campaign, Execution, LeadRecord, Recommendation, SalesDaily
from app.sales import importer
from app.tracking import page_check
from tests.conftest import login, make_user
from tests.test_sync_flow import ACCOUNTS, connect
from tests.test_sync_flow import fake as fake  # noqa: F401  (fixture)
from tests.windsor_fake import META_A

CAMPAIGN = "[Studio] [Eng-WPP] [Pilates]"


def day(n):
    return (date.today() - timedelta(days=n)).strftime("%d/%m/%Y")


@pytest.fixture()
def live(admin):
    r = admin.post("/api/clients", json={"name": "Studio Real", "data_mode": "live", "target_cac": "40",
                                         "target_roas": "3", "gross_margin_pct": "40"})
    return r.json()


@pytest.fixture()
def synced(admin, live, fake):  # noqa: F811
    connect(admin, live["id"])
    assert admin.post(f"/api/clients/{live['id']}/sync", json={"days": 30}).json()["status"] == "completed"
    return live


def orders_csv(n=30, extra=""):
    rows = ["Pedido;Data;Nome;Telefone;E-mail;Valor;utm_campaign;Status"]
    for i in range(n):
        rows.append(f"P{i};{day(1 + i % 25)};Fulano {i};11999990000;f{i}@x.com;R$ 100,00;"
                    f"studio-eng-wpp-pilates;pago")
    return "\n".join(rows) + extra


# --- importação -------------------------------------------------------------------------------------

def test_parsers():
    assert importer.parse_money("R$ 1.234,56") == importer.Decimal("1234.56")
    assert importer.parse_money("1,234.56") == importer.Decimal("1234.56")
    assert importer.parse_money("89.9") == importer.Decimal("89.90")
    assert importer.parse_date("31/12/2025") == date(2025, 12, 31)
    assert importer.parse_date("2025-12-31T10:00:00") == date(2025, 12, 31)
    assert importer.norm("Conversas WhatsApp — Público aberto") == "conversas-whatsapp-publico-aberto"


def test_orders_import_drops_personal_data_and_unlocks_cac(admin, synced, db):
    cid = synced["id"]
    before = admin.get(f"/api/clients/{cid}/dashboard").json()["kpis"]
    assert before["real_cac"] is None
    extra = (f"\nP0;{day(2)};x;x;x;R$ 100,00;studio-eng-wpp-pilates;pago"  # pedido repetido
             f"\nP90;{day(2)};x;x;x;R$ 50,00;campanha-que-nao-existe;pago"
             f"\nP91;{day(2)};x;x;x;R$ 70,00;studio-eng-wpp-pilates;cancelado")
    preview = admin.post(f"/api/clients/{cid}/imports", json={"kind": "orders", "csv_text": orders_csv(extra=extra)})
    p = preview.json()
    assert preview.status_code == 200 and p["committed"] is False
    assert set(p["ignored_personal_columns"]) == {"Nome", "Telefone", "E-mail"}
    assert p["imported"] == 30 and p["skipped"] == {"pedido repetido no arquivo": 1, "status não pago": 1}
    assert p["unmatched_campaigns"] == [["campanha-que-nao-existe", 1]]
    assert db.scalar(select(func.count()).select_from(SalesDaily)) == 0  # prévia não grava
    done = admin.post(f"/api/clients/{cid}/imports", json={"kind": "orders", "csv_text": orders_csv(extra=extra),
                                                           "commit": True}).json()
    assert done["committed"] and done["totals"]["sales"] == 30 and done["totals"]["revenue"] == 3000.0
    k = admin.get(f"/api/clients/{cid}/dashboard?days=30").json()["kpis"]
    assert k["confirmed_sales"] == 30 and k["real_cac"] == pytest.approx(k["spend"] / 30)
    # nada de dado pessoal no banco nem na auditoria
    assert "Fulano" not in admin.get(f"/api/audit?client_id={cid}").text
    # reimportar o mesmo arquivo não duplica
    admin.post(f"/api/clients/{cid}/imports", json={"kind": "orders", "csv_text": orders_csv(extra=extra),
                                                    "commit": True})
    assert admin.get(f"/api/clients/{cid}/dashboard?days=30").json()["kpis"]["confirmed_sales"] == 30
    findings = admin.get(f"/api/clients/{cid}/tracking").json()["findings"]
    assert any("Vendas sem campanha identificada" in f["title"] for f in findings)


def test_import_errors_and_demo_guard(admin, synced, demo_client):
    cid = synced["id"]
    bad = admin.post(f"/api/clients/{cid}/imports", json={"kind": "orders", "csv_text": "data;campanha\n01/01/2026;x"})
    assert bad.status_code == 422 and "valor" in bad.json()["detail"]
    no_camp = admin.post(f"/api/clients/{cid}/imports",
                         json={"kind": "orders", "csv_text": "data;valor\n01/01/2026;10"})
    assert no_camp.status_code == 422
    demo = admin.post(f"/api/clients/{demo_client['id']}/imports",
                      json={"kind": "orders", "csv_text": orders_csv(), "commit": True})
    assert demo.status_code == 409


def leads_csv(n=40, minutes=45, stage_cycle=("novo", "contato", "qualificado", "proposta", "venda", "perdido")):
    rows = ["ID,Data,Nome,WhatsApp,Campanha,Status,Tempo resposta (min),Motivo perda"]
    for i in range(n):
        stage = stage_cycle[i % len(stage_cycle)]
        rows.append(f"L{i},{day(1 + i % 20)},Pessoa {i},11988887777,{CAMPAIGN},{stage},{minutes},"
                    f"{'preço' if stage == 'perdido' else ''}")
    return "\n".join(rows)


def test_leads_import_funnel_and_sales_rules(admin, synced, db):
    cid = synced["id"]
    r = admin.post(f"/api/clients/{cid}/imports", json={"kind": "leads", "csv_text": leads_csv(), "commit": True})
    out = r.json()
    assert r.status_code == 200 and out["imported"] == 40
    assert set(out["ignored_personal_columns"]) == {"Nome", "WhatsApp"}
    assert db.scalar(select(func.count()).select_from(LeadRecord)) == 40
    assert all(len(lead.ref_hash) == 64 for lead in db.scalars(select(LeadRecord)))  # só hash, sem o ID original
    admin.post(f"/api/clients/{cid}/imports", json={"kind": "leads", "csv_text": leads_csv(), "commit": True})
    assert db.scalar(select(func.count()).select_from(LeadRecord)) == 40  # reimportação idempotente
    s = admin.get(f"/api/clients/{cid}/sales?days=30").json()
    funnel = {f["stage"]: f["count"] for f in s["funnel"]}
    # 40 leads em ciclo de 6 etapas: perdidos contam só na entrada
    assert funnel["novo"] == 40 and funnel["venda"] == 6 and funnel["qualificado"] == 6 + 7 + 7
    assert s["response"]["median_min"] == 45 and s["lost_reasons"][0][0] == "preço"
    camp = next(c for c in s["by_campaign"] if c["campaign"] == CAMPAIGN)
    assert camp["crm_leads"] == 40 and camp["sales"] == 6 and camp["cost_per_sale"] == pytest.approx(camp["spend"] / 6)
    a = admin.post(f"/api/clients/{cid}/analyses", json={"question": "Como está o atendimento?", "days": 30}).json()
    rules = {rec["rule"]: rec for rec in a["recommendations"]}
    assert "slow_response" in rules and rules["slow_response"]["campaign_id"] is None
    assert rules["slow_response"]["agent"] == "Sales Intelligence"
    # 120 leads na plataforma (4 por dia) e 40 no CRM: menos da metade chega ao CRM
    assert "crm_leads_gap" in rules and rules["crm_leads_gap"]["agent"] == "Tracking & CRO"
    assert rules["slow_response"]["id"] in a["summary"]["matched_ids"]


# --- verificação de página (com proteção contra acesso à rede interna) ------------------------------

PAGE = """<html><head><title>Studio</title><meta name="viewport" content="width=device-width">
<script>!function(f,b,e,v){}(window,document,'script','https://connect.facebook.net/en_US/fbevents.js');
fbq('init', '1234567890123'); fbq('track','PageView');</script>
<script async src="https://www.googletagmanager.com/gtag/js?id=G-ABC123XYZ"></script></head>
<body><a href="https://wa.me/5511999999999">Fale no WhatsApp</a></body></html>"""


def checker(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_page_check_detects_tags(monkeypatch):
    monkeypatch.setattr(page_check, "resolve", lambda host: ["93.184.216.34"])
    result = page_check.check("https://exemplo.test/lp", checker(lambda r: httpx.Response(200, html=PAGE)))
    items = {i["key"]: i for i in result["items"]}
    assert items["meta_pixel"]["ok"] and "1234567890123" in items["meta_pixel"]["detail"]
    assert items["ga4"]["ok"] and "G-ABC123XYZ" in items["ga4"]["detail"]
    assert items["viewport"]["ok"] and items["conversion_path"]["ok"] and items["https"]["ok"]
    assert items["gtm"]["ok"] is False and result["title"] == "Studio"


@pytest.mark.parametrize("url,ip", [("http://localhost/", "127.0.0.1"), ("http://interno.test/", "10.0.0.5"),
                                    ("http://metadata.test/", "169.254.169.254"), ("http://v6.test/", "::1")])
def test_page_check_blocks_internal_addresses(monkeypatch, url, ip):
    monkeypatch.setattr(page_check, "resolve", lambda host: [ip])
    with pytest.raises(page_check.PageCheckError, match="não público"):
        page_check.check(url, checker(lambda r: httpx.Response(200, html=PAGE)))


def test_page_check_blocks_redirect_to_internal_and_bad_schemes(monkeypatch):
    ips = {"publico.test": ["93.184.216.34"], "interno.test": ["192.168.0.10"]}
    monkeypatch.setattr(page_check, "resolve", lambda host: ips[host])

    def handler(request):
        if request.url.host == "publico.test":
            return httpx.Response(302, headers={"location": "http://interno.test/admin"})
        return httpx.Response(200, html="segredo")
    with pytest.raises(page_check.PageCheckError, match="não público"):
        page_check.check("https://publico.test/", checker(handler))
    for bad in ("file:///etc/passwd", "ftp://publico.test/", "https://publico.test:8443/"):
        with pytest.raises(page_check.PageCheckError):
            page_check.check(bad, checker(handler))


def test_page_check_unknown_domain(monkeypatch):
    def boom(host):
        raise socket.gaierror("x")
    monkeypatch.setattr(page_check, "resolve", boom)
    with pytest.raises(page_check.PageCheckError, match="domínio"):
        page_check.check("https://nao-existe.test/", checker(lambda r: httpx.Response(200)))


def test_page_check_endpoint_and_audit(admin, synced, monkeypatch):
    monkeypatch.setattr(page_check, "resolve", lambda host: ["93.184.216.34"])
    real_check = page_check.check
    monkeypatch.setattr(page_check, "check",
                        lambda url: real_check(url, checker(lambda r: httpx.Response(200, html="<html>nada</html>"))))
    cid = synced["id"]
    r = admin.post(f"/api/clients/{cid}/tracking/page-check", json={"url": "https://lp.test/"})
    assert r.status_code == 201 and r.json()["problems"] >= 3
    t = admin.get(f"/api/clients/{cid}/tracking").json()
    assert any(f["area"] == "Página" for f in t["findings"]) and len(t["page_checks"]) == 1
    assert t["utm"]["campaigns"][0]["utm_campaign"] in ("studio-eng-wpp-pilates", "studio-matriculas")
    bad = admin.post(f"/api/clients/{cid}/tracking/page-check", json={"url": "javascript:alert(1)"})
    assert bad.status_code == 422


# --- escrita real (contra o Windsor.ai falso) -------------------------------------------------------

def enable_write(admin, cid, name="Studio Real"):
    return admin.put(f"/api/clients/{cid}/write-access", json={"enabled": True, "confirm_name": name})


def scale_rec(admin, cid):
    """Importa vendas suficientes para a regra de escala propor aumento de orçamento na campanha Meta."""
    admin.post(f"/api/clients/{cid}/imports", json={"kind": "orders", "csv_text": orders_csv(60), "commit": True})
    a = admin.post(f"/api/clients/{cid}/analyses", json={"question": "Vale escalar?", "days": 30}).json()
    rec = next(r for r in a["recommendations"] if r["rule"] == "scale_winner")
    assert rec["action_type"] == "adjust_budget" and rec["action_payload"]["from"] == 21.0
    return rec


def test_write_access_rules(admin, synced, demo_client, db):
    cid = synced["id"]
    assert enable_write(admin, cid, name="nome errado").status_code == 422
    assert enable_write(admin, demo_client["id"], name=demo_client["name"]).status_code == 409
    make_user(db, "gestor2@example.com", "manager")
    assert login("gestor2@example.com").put(f"/api/clients/{cid}/write-access",  # só administradores
                                            json={"enabled": True, "confirm_name": "Studio Real"}).status_code == 403
    assert enable_write(admin, cid).json() == {"write_enabled": True}
    assert admin.get(f"/api/clients/{cid}").json()["write_enabled"] is True


def test_live_budget_change_blocked_while_write_disabled(admin, synced, fake):  # noqa: F811
    cid = synced["id"]
    rec = scale_rec(admin, cid)
    out = admin.post(f"/api/clients/{cid}/recommendations/{rec['id']}/decision", json={"decision": "approve"}).json()
    assert out["status"] == "failed" and "desligada" in out["executions"][0]["error"]
    assert fake.actions == []  # nada foi enviado à plataforma


def test_live_budget_change_executes_and_verifies(admin, synced, fake, db):  # noqa: F811
    cid = synced["id"]
    enable_write(admin, cid)
    rec = scale_rec(admin, cid)
    out = admin.post(f"/api/clients/{cid}/recommendations/{rec['id']}/decision", json={"decision": "approve"}).json()
    ex = out["executions"][0]
    assert out["status"] == "completed" and ex["mode"] == "live" and ex["verified"]
    assert fake.actions == [{"account": META_A, "action": "set_campaign_budget",
                             "params": {"campaign_id": "c-meta-1", "budget_type": "daily", "amount": 2520}}]
    assert ex["after_state"] == {"daily_budget": 25.2} and ex["request"]["action"] == "set_campaign_budget"
    camp = db.scalar(select(Campaign).where(Campaign.external_id == "c-meta-1"))
    db.refresh(camp)
    assert float(camp.daily_budget) == 25.2


def test_cache_lag_leaves_execution_awaiting_verification(admin, synced, fake, db):  # noqa: F811
    cid = synced["id"]
    enable_write(admin, cid)
    fake.stale_reads = 1
    rec = scale_rec(admin, cid)
    out = admin.post(f"/api/clients/{cid}/recommendations/{rec['id']}/decision", json={"decision": "approve"}).json()
    ex = out["executions"][0]
    assert out["status"] == "executing" and ex["status"] == "awaiting_verification" and not ex["verified"]
    assert "Verificar agora" in ex["error"]
    camp = db.scalar(select(Campaign).where(Campaign.external_id == "c-meta-1"))
    assert float(camp.daily_budget) == 21.0  # sem verificação, o Borges não assume a mudança
    verified = admin.post(f"/api/clients/{cid}/executions/{ex['id']}/verify").json()
    assert verified["status"] == "completed" and verified["verified"]
    assert db.get(Recommendation, rec["id"]).status == "completed"


def test_spend_increase_needs_second_human_confirmation(admin, synced, fake):  # noqa: F811
    cid = synced["id"]
    enable_write(admin, cid)
    fake.confirm_increases = True
    rec = scale_rec(admin, cid)
    out = admin.post(f"/api/clients/{cid}/recommendations/{rec['id']}/decision", json={"decision": "approve"}).json()
    ex = out["executions"][0]
    assert ex["status"] == "awaiting_confirmation" and fake.budget_cents["c-meta-1"] == 2100  # ainda não mudou
    assert "Prévia" in ex["response"]["detail"]
    done = admin.post(f"/api/clients/{cid}/executions/{ex['id']}/confirm").json()
    assert done["status"] == "completed" and fake.budget_cents["c-meta-1"] == 2520
    assert fake.actions[-1]["confirmation_token"] == "tok-123"
    assert admin.post(f"/api/clients/{cid}/executions/{ex['id']}/confirm").status_code == 409


def test_windsor_write_not_enabled_fails_cleanly(admin, synced, fake):  # noqa: F811
    cid = synced["id"]
    enable_write(admin, cid)
    fake.writes_enabled = False
    rec = scale_rec(admin, cid)
    out = admin.post(f"/api/clients/{cid}/recommendations/{rec['id']}/decision", json={"decision": "approve"}).json()
    assert out["status"] == "failed" and "Team management" in out["executions"][0]["error"]


def test_live_pause_ad_group_on_google(admin, synced, fake, db):  # noqa: F811
    """Grupo do Google gastando sem conversão: pausado de verdade pelo Windsor.ai e verificado."""
    from app.models import AdSet
    cid = synced["id"]
    enable_write(admin, cid)
    group = db.scalar(select(AdSet).where(AdSet.external_id == "ag-1"))
    camp = db.get(Campaign, group.campaign_id)
    run = db.scalar(select(Recommendation.analysis_run_id).limit(1))
    if run is None:
        run = admin.post(f"/api/clients/{cid}/analyses", json={"question": "x" * 5, "days": 30}).json()["id"]
    rec = Recommendation(client_id=cid, analysis_run_id=run, campaign_id=camp.id, ad_set_id=group.id,
                         agent="Google Ads Specialist", rule="ad_no_results", title="Pausar grupo", problem="p",
                         evidence=[], probable_cause="c", alternatives=[], hypothesis="h", action_type="pause_ad_group",
                         action_payload={"ad_set_id": group.id}, recommended_action="a", expected_impact="i",
                         priority="baixa", confidence="baixa", risks="r", validation_metric="v")
    db.add(rec)
    db.commit()
    out = admin.post(f"/api/clients/{cid}/recommendations/{rec.id}/decision", json={"decision": "approve"}).json()
    assert out["status"] == "completed", out["executions"]
    assert fake.actions[-1]["action"] == "pause_ad_group" and fake.group_status["ag-1"] == "paused"
    db.refresh(group)
    assert group.status == "paused"
    assert db.scalar(select(func.count()).select_from(Execution)) == 1
    _ = ACCOUNTS
