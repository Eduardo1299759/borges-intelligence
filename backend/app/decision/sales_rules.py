"""Regras de Sales Intelligence e Tracking & CRO que dependem de dados do CRM (funções puras).

- slow_response: mediana do tempo de primeira resposta acima de 30 minutos (com 20+ leads respondidos).
  Leads de mídia paga esfriam rápido; atendimento lento costuma pesar mais no CAC que o anúncio.
- crm_leads_gap: a plataforma registrou 30+ leads numa campanha e o CRM recebeu menos da metade.
  Ou os leads não estão sendo registrados, ou a plataforma conta como lead o que não é (ex.: conversa sem
  mensagem). Só roda quando o cliente importou leads do CRM.
"""
from __future__ import annotations

from typing import Any

from app.decision.engine import AccountContext, Draft, num, pct

SLOW_MINUTES = 30
MIN_ANSWERED = 20
GAP_MIN_PLATFORM_LEADS = 30
GAP_RATIO = 0.5


def evaluate(sales: dict[str, Any], acc: AccountContext) -> list[Draft]:
    if not sales.get("has_crm_data"):
        return []

    def ev(metric: str, value: str, benchmark: str = "") -> dict:
        return {"metric": metric, "value": value, "benchmark": benchmark, "period": acc.period_label,
                "source": "crm_import"}

    drafts: list[Draft] = []
    resp = sales["response"]
    if resp["answered"] >= MIN_ANSWERED and resp["median_min"] is not None and resp["median_min"] > SLOW_MINUTES:
        drafts.append(Draft(
            None, "Sales Intelligence", "slow_response",
            "Reduzir o tempo de primeira resposta aos leads",
            f"Metade dos leads espera mais de {num(resp['median_min'], 0)} minutos pela primeira resposta.",
            "Atendimento sem fila priorizada para leads de anúncio, ou fora do horário comercial.",
            "Responder em até 5 minutos aumenta a taxa lead → venda sem mudar nada na mídia.",
            "process_change",
            "Definir resposta inicial automática e um responsável por fila de leads de anúncio; medir a mediana "
            "de resposta por semana.",
            "Aumento da taxa lead → venda e queda do CAC; a magnitude depende do segmento.",
            "Mensagem automática genérica pode irritar; personalize e mantenha um humano logo em seguida.",
            "Mediana do tempo de primeira resposta e taxa lead → venda nas próximas 2 semanas.",
            "média", True, 1.0,
            evidence=[ev("Leads com tempo de resposta registrado", num(resp["answered"], 0)),
                      ev("Mediana da primeira resposta", f"{num(resp['median_min'], 0)} min",
                         f"referência: até {SLOW_MINUTES} min"),
                      ev("Respondidos em até 5 minutos", pct(resp["within_5_min"]))],
            alternatives=["O tempo registrado no CRM pode não refletir o primeiro contato real (ex.: WhatsApp)."],
            spend_share=0.3,
        ))
    for row in sales["by_campaign"]:
        platform, crm = row.get("platform_leads"), row.get("crm_leads")
        if row["campaign_id"] is None or not platform or platform < GAP_MIN_PLATFORM_LEADS:
            continue
        if crm < platform * GAP_RATIO:
            drafts.append(Draft(
                row["campaign_id"], "Tracking & CRO", "crm_leads_gap",
                f"Leads de “{row['campaign']}” não estão chegando ao CRM",
                f"A plataforma registrou {num(platform, 0)} leads e o CRM, {num(crm, 0)}.",
                "Leads não registrados no CRM (atendimento direto no WhatsApp), UTM ausente no link, ou a "
                "plataforma contando como lead conversas sem mensagem.",
                "Com o registro completo, o CAC por campanha passa a ser confiável e as decisões de verba também.",
                "tracking_audit",
                "Conferir a UTM da campanha no link do anúncio, o registro de todo lead no CRM e a definição de "
                "conversa/lead usada na otimização da campanha.",
                "Nenhum ganho direto em vendas; evita decisões baseadas em dados incompletos.",
                "Enquanto não corrigido, CAC e taxa de conversão desta campanha estão distorcidos.",
                "Razão leads no CRM / leads na plataforma (alvo: acima de 80%).",
                "média", True, 1.2,
                evidence=[ev("Leads na plataforma", num(platform, 0)), ev("Leads no CRM", num(crm, 0)),
                          ev("Razão CRM / plataforma", pct(crm / platform), f"mínimo {pct(GAP_RATIO)}")],
                alternatives=["A importação do CRM pode estar incompleta para o período."],
            ))
    return drafts
