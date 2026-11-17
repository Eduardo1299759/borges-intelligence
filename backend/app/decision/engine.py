"""Motor de decisão: transforma o retrato de cada campanha em uma recomendação estruturada.

Funções puras (sem banco), para serem testáveis e auditáveis. Cada campanha recebe exatamente uma
recomendação, pela primeira regra aplicável, nesta ordem:

1. amostra insuficiente  -> NÃO alterar (não decidir sobre ruído)
2. divergência de rastreamento -> auditar antes de mexer em orçamento (dado não confiável)
3. fadiga criativa -> renovar criativos
4. CAC acima do sustentável -> investigar qualidade do lead OU reduzir orçamento
5. desempenho acima da meta -> escalar com limite
6. nenhuma das anteriores -> manter

Os limiares abaixo são pontos de partida conservadores, não verdades universais; devem ser
calibrados por cliente com dados reais (Fase 6: memória de aprendizados).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

MIN_DAYS = 7
MIN_LEADS = 30
MIN_SALES = 10
TRACKING_DIVERGENCE = 1.5  # receita atribuída / confirmada (ou o inverso)
FATIGUE_CTR_DROP = 0.80  # CTR da 2ª metade <= 80% da 1ª
FATIGUE_FREQ_RISE = 1.20  # frequência da 2ª metade >= 120% da 1ª
CAC_TOLERANCE = 1.20
SCALE_ROAS_FACTOR = 1.20
DEFAULT_BUDGET_STEP_PCT = 20.0


@dataclass
class AccountContext:
    target_cac: float | None
    target_roas: float | None
    margin_pct: float | None
    max_budget_change_pct: float
    kpis: dict[str, float | None]
    period_label: str
    sources: str


@dataclass
class CampaignSnapshot:
    campaign_id: int
    name: str
    platform: str
    daily_budget: float | None
    kpis: dict[str, float | None]
    first_half: dict[str, float | None]
    second_half: dict[str, float | None]
    spend_share: float | None


@dataclass
class Draft:
    campaign_id: int
    agent: str
    rule: str
    title: str
    problem: str
    probable_cause: str
    hypothesis: str
    action_type: str
    recommended_action: str
    expected_impact: str
    risks: str
    validation_metric: str
    confidence: str
    requires_approval: bool
    severity: float
    evidence: list[dict[str, Any]] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    action_payload: dict[str, Any] = field(default_factory=dict)
    priority: str = "baixa"
    priority_score: int = 0


def brl(v: float | None) -> str:
    if v is None:
        return "indisponível"
    return "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v: float | None) -> str:
    return "indisponível" if v is None else f"{v * 100:.1f}%".replace(".", ",")


def num(v: float | None, digits: int = 2) -> str:
    return "indisponível" if v is None else f"{v:.{digits}f}".replace(".", ",")


def _confidence(sales: float | None) -> str:
    if sales is not None and sales >= 50:
        return "alta"
    if sales is not None and sales >= 20:
        return "média"
    return "baixa"


def evaluate(s: CampaignSnapshot, acc: AccountContext) -> Draft:
    k = s.kpis

    def ev(metric: str, value: str, benchmark: str = "") -> dict[str, Any]:
        return {"metric": metric, "value": value, "benchmark": benchmark,
                "period": acc.period_label, "source": acc.sources}

    base_evidence = [
        ev("Investimento", brl(k["spend"])),
        ev("Leads / conversas", num(k["leads"], 0)),
        ev("Vendas confirmadas", num(k["confirmed_sales"], 0)),
    ]
    days, leads, sales = k["days"] or 0, k["leads"] or 0, k["confirmed_sales"] or 0

    # 1. Amostra insuficiente -------------------------------------------------------------------
    if days < MIN_DAYS or (leads < MIN_LEADS and sales < MIN_SALES):
        return Draft(
            s.campaign_id, "Performance Auditor", "insufficient_sample",
            f"Manter sem alterações: amostra insuficiente em “{s.name}”",
            "Ainda não há volume de dados suficiente para avaliar esta campanha.",
            "Campanha recente ou de baixo volume; qualquer leitura agora seria dominada por ruído.",
            "Com mais dias e conversões, os indicadores estabilizam e permitem um diagnóstico confiável.",
            "no_change", "Não alterar a campanha. Reavaliar quando houver ao menos "
            f"{MIN_DAYS} dias de dados e {MIN_LEADS} leads ou {MIN_SALES} vendas confirmadas.",
            "Evita decisões baseadas em oscilações aleatórias e preserva a fase de aprendizado da plataforma.",
            "Continuar investindo em uma campanha ainda não avaliada; o gasto é limitado pelo orçamento diário atual.",
            "Dias com dados, leads e vendas confirmadas acumulados.",
            "baixa", False, 0.0,
            evidence=[ev("Dias com dados", str(days), f"mínimo {MIN_DAYS}"),
                      ev("Leads / conversas", num(leads, 0), f"mínimo {MIN_LEADS}"),
                      ev("Vendas confirmadas", num(sales, 0), f"mínimo {MIN_SALES}")],
            alternatives=["O volume pode ser estruturalmente baixo (público ou termos restritos)."],
        )

    # 2. Divergência de rastreamento ------------------------------------------------------------
    att, conf = k["attributed_revenue"], k["confirmed_revenue"]
    if att and conf and sales >= MIN_SALES:
        ratio = att / conf
        if ratio >= TRACKING_DIVERGENCE or ratio <= 1 / TRACKING_DIVERGENCE:
            direction = "acima" if ratio > 1 else "abaixo"
            return Draft(
                s.campaign_id, "Performance Auditor", "tracking_divergence",
                f"Auditar rastreamento de “{s.name}” antes de alterar orçamento",
                f"A receita atribuída pela plataforma está {num(ratio)}x {direction} da receita confirmada.",
                "Eventos de conversão duplicados, janela de atribuição ampla ou crédito por vendas que "
                "ocorreriam de qualquer forma (ex.: buscas de marca dentro de Performance Max).",
                "Corrigindo a mensuração, o ROAS reportado passa a refletir a receita real e as decisões de "
                "orçamento desta campanha tornam-se confiáveis.",
                "tracking_audit",
                "Auditar eventos de compra (deduplicação Pixel/API de Conversões ou tag do Google), janela de "
                "atribuição e conciliação com pedidos confirmados. Não escalar nem reduzir esta campanha até concluir.",
                "Sem impacto direto em vendas; reduz o risco de alocar verba com base em ROAS inflado. "
                "A magnitude do desvio após a correção é incerta.",
                "Enquanto a auditoria ocorre, a campanha segue com o orçamento atual, possivelmente subótimo.",
                "Razão receita atribuída / receita confirmada (alvo: entre 0,8 e 1,25).",
                "média", True, 1.5,
                evidence=base_evidence + [
                    ev("Receita atribuída (plataforma)", brl(att)),
                    ev("Receita confirmada", brl(conf)),
                    ev("ROAS atribuído", num(k["attributed_roas"]), f"ROAS confirmado {num(k['confirmed_roas'])}"),
                ],
                alternatives=["Vendas confirmadas podem estar sub-registradas no CRM/pedidos.",
                              "Diferença de fuso horário ou de data de registro entre as fontes."],
            )

    # 3. Fadiga criativa ------------------------------------------------------------------------
    ctr1, ctr2 = s.first_half.get("ctr"), s.second_half.get("ctr")
    f1, f2 = s.first_half.get("avg_daily_frequency"), s.second_half.get("avg_daily_frequency")
    if ctr1 and ctr2 and f1 and f2 and ctr2 / ctr1 <= FATIGUE_CTR_DROP and f2 / f1 >= FATIGUE_FREQ_RISE:
        cac1, cac2 = s.first_half.get("real_cac"), s.second_half.get("real_cac")
        return Draft(
            s.campaign_id, "Performance Auditor", "creative_fatigue",
            f"Renovar criativos de “{s.name}”: sinais de fadiga",
            "O CTR caiu e a frequência subiu dentro do próprio período analisado.",
            "O mesmo público está vendo os mesmos anúncios repetidamente (saturação criativa).",
            "Novos criativos, com ângulos diferentes para o mesmo público, devem recuperar a taxa de clique. "
            "Isso só tem valor se o CAC acompanhar: mais cliques não garantem mais vendas.",
            "creative_refresh",
            "Preparar de 3 a 5 novas variações criativas com ângulos distintos e testá-las contra o criativo atual, "
            "mantendo público e orçamento constantes.",
            "Recuperação parcial do CTR e do custo por lead; efeito sobre vendas é uma hipótese a validar em teste.",
            "Novos criativos reiniciam parte do aprendizado; o desempenho pode oscilar nos primeiros dias.",
            "CAC real e taxa lead→venda das novas variações versus o criativo atual (CTR como métrica secundária).",
            "média", True, 1.2,
            evidence=base_evidence + [
                ev("CTR — 1ª metade do período", pct(ctr1)),
                ev("CTR — 2ª metade do período", pct(ctr2), f"queda de {pct(1 - ctr2 / ctr1)}"),
                ev("Frequência média diária — 1ª metade", num(f1)),
                ev("Frequência média diária — 2ª metade", num(f2), f"alta de {pct(f2 / f1 - 1)}"),
                ev("CAC real — 1ª → 2ª metade", f"{brl(cac1)} → {brl(cac2)}"),
            ],
            alternatives=["Sazonalidade ou aumento de concorrência no leilão no mesmo intervalo.",
                          "Mudança de oferta ou de preço no período."],
        )

    # 4. CAC acima do sustentável ---------------------------------------------------------------
    cac = k["real_cac"]
    if acc.target_cac and cac and sales >= MIN_SALES and cac > acc.target_cac * CAC_TOLERANCE:
        cac_evidence = base_evidence + [
            ev("CAC real", brl(cac), f"meta {brl(acc.target_cac)}"),
            ev("Custo por lead", brl(k["cpl"]), f"conta {brl(acc.kpis.get('cpl'))}"),
            ev("Taxa lead→venda", pct(k["lead_to_sale_rate"]), f"conta {pct(acc.kpis.get('lead_to_sale_rate'))}"),
        ]
        cpl, acc_cpl = k["cpl"], acc.kpis.get("cpl")
        rate, acc_rate = k["lead_to_sale_rate"], acc.kpis.get("lead_to_sale_rate")
        if cpl and acc_cpl and rate is not None and acc_rate and cpl <= acc_cpl * 1.1 and rate < acc_rate * 0.7:
            return Draft(
                s.campaign_id, "Performance Auditor", "lead_quality",
                f"Investigar qualidade dos leads de “{s.name}”",
                f"Custo por cliente ({brl(cac)}) acima da meta ({brl(acc.target_cac)}), apesar de um custo por "
                "lead normal.",
                "A campanha gera conversas baratas que não viram venda: provável atração de leads pouco qualificados.",
                "Um criativo e uma abordagem que qualifiquem a intenção de compra devem elevar a taxa lead→venda, "
                "mesmo com custo por lead maior.",
                "investigate_lead_quality",
                "Analisar uma amostra das conversas desta campanha (objeções, tempo de resposta, perfil) e testar um "
                "criativo que qualifique melhor a intenção do comprador. Não reduzir orçamento antes dessa análise.",
                "Redução do CAC se a hipótese se confirmar; a magnitude depende do diagnóstico das conversas.",
                "Se a causa for atendimento comercial lento, mudar o anúncio não resolve.",
                "CAC real e taxa lead→venda após o teste, comparados ao período atual.",
                _confidence(sales), True, 1.5,
                evidence=cac_evidence,
                alternatives=["Atendimento comercial lento ou sem follow-up para esta origem.",
                              "Oferta desalinhada com o público alcançado.",
                              "Vendas desta origem não estão sendo registradas no CRM."],
            )
        return _budget_draft(
            s, acc, direction=-1, rule="cac_above_target",
            title=f"Reduzir orçamento de “{s.name}”: CAC acima do sustentável",
            problem=f"Custo por cliente ({brl(cac)}) acima da meta ({brl(acc.target_cac)}) com volume suficiente "
                    "para descartar ruído.",
            cause="Custo de aquisição estruturalmente alto nesta campanha (leilão, público ou oferta).",
            hypothesis="Reduzir a verba corta primeiro a entrega marginal, mais cara, e libera orçamento para "
                       "campanhas com CAC dentro da meta.",
            impact="Redução do investimento ineficiente; o CAC da campanha pode melhorar, mas isso não é garantido.",
            risks="Perda de volume de vendas; reduções bruscas podem reiniciar o aprendizado da plataforma.",
            validation="CAC real da campanha e CAC real da conta nos 14 dias seguintes.",
            confidence=_confidence(sales), severity=1.5, evidence=cac_evidence,
            alternatives=["O problema pode estar na página ou no atendimento, não na mídia.",
                          "Vendas podem estar sub-registradas para esta origem."],
        )

    # 5. Escalar ---------------------------------------------------------------------------------
    roas = k["confirmed_roas"]
    if (acc.target_roas and roas and sales >= MIN_SALES and roas >= acc.target_roas * SCALE_ROAS_FACTOR
            and (not acc.target_cac or (cac is not None and cac <= acc.target_cac))):
        return _budget_draft(
            s, acc, direction=1, rule="scale_winner",
            title=f"Escalar “{s.name}” de forma gradual",
            problem="Campanha com retorno confirmado acima da meta e possivelmente limitada por orçamento.",
            cause="Público e oferta com alta intenção de compra; a verba atual pode não capturar toda a demanda.",
            hypothesis="Um aumento gradual de orçamento deve gerar mais vendas mantendo o CAC dentro da meta.",
            impact="Mais vendas confirmadas; o retorno marginal tende a ser menor que o médio, então o ROAS "
                   "deve cair um pouco.",
            risks="Saturação do público (especialmente em remarketing) e aumento de frequência; ROAS marginal "
                  "desconhecido.",
            validation="CAC real e ROAS confirmado nos 7 a 14 dias seguintes; reverter se o CAC ultrapassar a meta.",
            confidence=_confidence(sales), severity=1.0,
            evidence=base_evidence + [
                ev("ROAS confirmado", num(roas), f"meta {num(acc.target_roas)}"),
                ev("CAC real", brl(cac), f"meta {brl(acc.target_cac)}"),
            ],
            alternatives=["O resultado pode refletir demanda já existente, e não efeito incremental do anúncio."],
        )

    # 6. Manter ----------------------------------------------------------------------------------
    return Draft(
        s.campaign_id, "Performance Auditor", "keep",
        f"Manter “{s.name}” sem alterações",
        "Nenhum desvio relevante encontrado em relação às metas.",
        "Campanha operando dentro dos parâmetros definidos para o cliente.",
        "Manter a estrutura preserva o aprendizado da plataforma e evita instabilidade desnecessária.",
        "no_change", "Não alterar. Reavaliar na próxima análise.",
        "Estabilidade de resultados.",
        "Oportunidades de melhoria podem existir fora do alcance das regras atuais.",
        "CAC real e ROAS confirmado permanecendo dentro das metas.",
        _confidence(sales), False, 0.0,
        evidence=base_evidence + [
            ev("CAC real", brl(cac), f"meta {brl(acc.target_cac)}" if acc.target_cac else "meta não informada"),
            ev("ROAS confirmado", num(roas),
               f"meta {num(acc.target_roas)}" if acc.target_roas else "meta não informada"),
        ],
        alternatives=(
            ([] if acc.target_cac and acc.target_roas else
             ["Sem metas de CAC/ROAS cadastradas, as regras de eficiência não puderam ser avaliadas."])
            + ([] if k["confirmed_sales"] is not None else
               ["Sem vendas confirmadas para esta campanha, CAC real e ROAS confirmado não puderam ser avaliados; "
                "apenas amostra e fadiga criativa foram verificadas."])
        ),
    )


def _budget_draft(s: CampaignSnapshot, acc: AccountContext, *, direction: int, rule: str, title: str, problem: str,
                  cause: str, hypothesis: str, impact: str, risks: str, validation: str, confidence: str,
                  severity: float, evidence: list[dict[str, Any]], alternatives: list[str]) -> Draft:
    step = min(DEFAULT_BUDGET_STEP_PCT, acc.max_budget_change_pct)
    verb = "Aumentar" if direction > 0 else "Reduzir"
    if s.daily_budget is None or step <= 0:
        action_type, payload = "manual_review", {}
        action = f"{verb} o orçamento manualmente: o orçamento diário atual não está disponível para o sistema."
    else:
        new_budget = round(s.daily_budget * (1 + direction * step / 100), 2)
        action_type = "adjust_budget"
        payload = {"campaign_id": s.campaign_id, "from": s.daily_budget, "to": new_budget,
                   "change_pct": direction * step}
        action = (f"{verb} o orçamento diário em {num(step, 0)}%: de {brl(s.daily_budget)} para {brl(new_budget)}.")
    evidence = evidence + [{"metric": "Orçamento diário atual", "value": brl(s.daily_budget), "benchmark": "",
                            "period": "configuração atual", "source": acc.sources}]
    return Draft(s.campaign_id, "Performance Auditor", rule, title, problem, cause, hypothesis, action_type, action,
                 impact, risks, validation, confidence, True, severity, evidence=evidence,
                 alternatives=alternatives, action_payload=payload)


def prioritize(drafts: list[Draft], snapshots: dict[int, CampaignSnapshot]) -> list[Draft]:
    """Prioridade = participação no investimento x severidade da regra (impacto financeiro em jogo)."""
    for d in drafts:
        share = snapshots[d.campaign_id].spend_share or 0.0
        d.priority_score = int(round(min(100.0, share * 100 * d.severity)))
        d.priority = "alta" if d.priority_score >= 25 else "média" if d.priority_score >= 10 else "baixa"
    return sorted(drafts, key=lambda d: d.priority_score, reverse=True)
