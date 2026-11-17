"""Especialistas Meta Ads e Google Ads: diagnóstico abaixo do nível da campanha.

Funções puras, como o motor de campanha. Recebem o retrato da campanha e os totais do período de cada
anúncio (Meta) ou grupo de anúncios (Google) e devolvem recomendações. Só olham para o que a fonte
entrega nesse nível: investimento, cliques e leads/conversas/conversões. Vendas confirmadas existem só
no nível da campanha, então nenhuma regra daqui fala em CAC.

Regras:
- ad_no_results      investiu ao menos 3x o custo por lead da campanha e não trouxe nenhum lead.
                     Se o anúncio convertesse como a média da campanha, a chance de zero leads nesse
                     gasto seria de cerca de 5% (Poisson, média 3): é sinal, não ruído.
- ad_cpl_outlier     custo por lead 1,5x o da campanha, com volume e participação relevantes.
- ad_dilution        (Meta) verba pulverizada: metade ou mais dos anúncios ativos recebe menos de 5%.
- conversion_value_missing  (Google) conversões registradas sem nenhum valor: o Google não consegue
                     otimizar por valor e o ROAS reportado fica zerado.

Limiares conservadores, a calibrar com dados reais (Fase 6).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.decision.engine import AccountContext, CampaignSnapshot, Draft, brl, num, pct

MIN_CAMPAIGN_LEADS = 10
NO_RESULT_CPL_MULTIPLE = 3.0
NO_RESULT_MIN_SHARE = 0.05
OUTLIER_CPL_FACTOR = 1.5
OUTLIER_MIN_SHARE = 0.15
OUTLIER_MIN_LEADS = 5
DILUTION_MIN_ADS = 6
DILUTION_TINY_SHARE = 0.05
VALUE_MIN_CONVERSIONS = 10


@dataclass
class EntityStats:
    """Totais do período de um anúncio (Meta) ou grupo de anúncios (Google)."""

    ad_set_id: int
    ad_set_name: str
    ad_id: int | None
    ad_name: str | None
    status: str | None
    spend: float | None
    impressions: float | None
    clicks: float | None
    leads: float | None

    @property
    def short(self) -> str:
        return f"“{self.ad_name}”" if self.ad_id else f"grupo “{self.ad_set_name}”"

    @property
    def label(self) -> str:
        return f"“{self.ad_name}” (conjunto “{self.ad_set_name}”)" if self.ad_id else f"grupo “{self.ad_set_name}”"


def _div(a: float | None, b: float | None) -> float | None:
    return None if a is None or not b else a / b


def evaluate_entities(s: CampaignSnapshot, entities: list[EntityStats], acc: AccountContext) -> list[Draft]:
    camp_spend, camp_leads = s.kpis.get("spend"), s.kpis.get("leads")
    if not camp_spend:
        return []
    meta = s.platform == "meta"
    agent = "Meta Ads Specialist" if meta else "Google Ads Specialist"
    unit = "anúncio" if meta else "grupo de anúncios"
    # Meta: avalia anúncios. Google: avalia grupos (o Windsor não entrega anúncios do Google por linha).
    items = [e for e in entities if (e.spend or 0) > 0 and (e.ad_id is not None) == meta]
    account_spend = acc.kpis.get("spend") or camp_spend
    camp_cpl = _div(camp_spend, camp_leads)

    def ev(metric: str, value: str, benchmark: str = "") -> dict:
        return {"metric": metric, "value": value, "benchmark": benchmark, "period": acc.period_label,
                "source": acc.sources}

    drafts: list[Draft] = []
    if camp_leads and camp_leads >= MIN_CAMPAIGN_LEADS and camp_cpl:
        for e in items:
            share = e.spend / camp_spend
            leads = e.leads or 0
            base = [ev(f"Investimento do {unit}", brl(e.spend), f"{pct(share)} da campanha"),
                    ev(f"Leads / conversas do {unit}", num(leads, 0)),
                    ev("Custo por lead da campanha", brl(camp_cpl))]
            if leads == 0 and e.spend >= NO_RESULT_CPL_MULTIPLE * camp_cpl and share >= NO_RESULT_MIN_SHARE:
                multiple = e.spend / camp_cpl
                pausable = e.status != "paused"
                action = ("pause_ad" if meta else "pause_ad_group") if pausable else "manual_review"
                payload = ({"ad_id": e.ad_id} if meta else {"ad_set_id": e.ad_set_id}) if pausable else {}
                drafts.append(Draft(
                    s.campaign_id, agent, "ad_no_results",
                    f"{'Pausar' if pausable else 'Revisar'} {e.short} em “{s.name}”: gasto sem resultado",
                    f"O {unit} investiu {brl(e.spend)} ({num(multiple, 1)}x o custo por lead da campanha) e não "
                    "trouxe nenhum lead no período.",
                    "Criativo ou mensagem que não gera intenção neste público; o algoritmo continua entregando "
                    "por sinais de engajamento que não viram conversa.",
                    f"Retirando o {unit}, a verba volta para os demais, que convertem; o custo por lead da "
                    "campanha deve cair sem perda de volume.",
                    action,
                    (f"Pausar o {unit} {e.label}. Manter os demais e o orçamento da campanha." if pausable
                     else f"Revisar o {unit} {e.label}: pausar ou trocar a abordagem."),
                    f"Economia de até {brl(e.spend / max(1, (s.kpis.get('days') or 30)) )} por dia redirecionados "
                    "aos anúncios que convertem. O ganho em leads é uma hipótese, não uma garantia.",
                    "O anúncio pode estar ajudando de forma indireta (alcance, lembrança) e o conjunto pode "
                    "reentrar em aprendizado.",
                    "Custo por lead da campanha e volume de leads nos 7 dias seguintes.",
                    "média" if multiple >= 5 else "baixa", True, 1.3,
                    evidence=base + [ev("Investimento sem nenhum lead", f"{num(multiple, 1)}x o CPL da campanha",
                                        f"limite {num(NO_RESULT_CPL_MULTIPLE, 0)}x")],
                    alternatives=["O lead pode ter sido atribuído a outro anúncio do mesmo conjunto.",
                                  "Anúncio recente, ainda em aprendizado."],
                    action_payload=payload,
                    ad_set_id=e.ad_set_id, ad_id=e.ad_id, spend_share=e.spend / account_spend,
                ))
            elif (leads >= OUTLIER_MIN_LEADS and share >= OUTLIER_MIN_SHARE and len(items) >= 2
                  and e.spend / leads >= OUTLIER_CPL_FACTOR * camp_cpl):
                cpl = e.spend / leads
                drafts.append(Draft(
                    s.campaign_id, agent, "ad_cpl_outlier",
                    f"Custo por lead alto: {e.short} em “{s.name}”",
                    f"O custo por lead do {unit} ({brl(cpl)}) é {num(cpl / camp_cpl, 1)}x o da campanha, com "
                    f"{pct(share)} do investimento.",
                    "Criativo menos eficiente que os demais para o mesmo público e oferta.",
                    f"Testar uma variação deste {unit}, ou reduzir sua participação, deve baixar o custo por lead "
                    "da campanha. Custo por lead menor só importa se a qualidade do lead se mantiver.",
                    "creative_review",
                    f"Criar uma variação do {unit} com outro ângulo ou formato e comparar com o atual por 7 dias, "
                    "mantendo público e orçamento.",
                    "Redução do custo por lead da campanha proporcional à participação deste anúncio; incerta.",
                    "Leads mais baratos podem ser menos qualificados; acompanhe a taxa lead→venda.",
                    f"Custo por lead do {unit} e da campanha, e taxa lead→venda quando houver vendas confirmadas.",
                    "média" if leads >= 20 else "baixa", True, 1.0,
                    evidence=base + [ev(f"Custo por lead do {unit}", brl(cpl), f"campanha {brl(camp_cpl)}")],
                    alternatives=["Diferença de posicionamento ou público dentro do conjunto.",
                                  "Este anúncio pode trazer leads de melhor qualidade, o que só o CRM mostra."],
                    ad_set_id=e.ad_set_id, ad_id=e.ad_id, spend_share=e.spend / account_spend,
                ))

    if meta and len(items) >= DILUTION_MIN_ADS:
        tiny = [e for e in items if e.spend / camp_spend < DILUTION_TINY_SHARE]
        if len(tiny) * 2 >= len(items):
            drafts.append(Draft(
                s.campaign_id, agent, "ad_dilution",
                f"Consolidar anúncios de “{s.name}”: verba pulverizada",
                f"{len(tiny)} de {len(items)} anúncios ativos receberam menos de {int(DILUTION_TINY_SHARE * 100)}% do "
                "investimento cada.",
                "Muitos anúncios disputando a mesma verba: a maioria não recebe entrega suficiente para ser "
                "avaliada, e o aprendizado do algoritmo fica dividido.",
                "Com menos anúncios por conjunto, cada um recebe dados suficientes para o algoritmo e para a "
                "avaliação, sem mudar o orçamento.",
                "restructure",
                "Manter de 3 a 6 anúncios por conjunto: pausar os de menor entrega sem resultado e concentrar "
                "os testes de criativo em rodadas menores.",
                "Avaliação de criativos mais rápida e confiável; efeito sobre custo por lead incerto.",
                "Pausar muitos anúncios de uma vez pode reiniciar o aprendizado do conjunto.",
                "Número de anúncios com volume para avaliação e custo por lead da campanha.",
                "média", True, 0.6,
                evidence=[ev("Anúncios ativos com investimento", str(len(items))),
                          ev("Anúncios com menos de 5% do investimento", str(len(tiny)),
                             f"limite: metade ({len(items) // 2})")],
                alternatives=["Pode ser um teste de criativos intencional, ainda em andamento."],
            ))

    if not meta and camp_leads and camp_leads >= VALUE_MIN_CONVERSIONS and s.kpis.get("attributed_revenue") == 0:
        drafts.append(Draft(
            s.campaign_id, agent, "conversion_value_missing",
            f"Configurar valor das conversões em “{s.name}”",
            f"A campanha registrou {num(camp_leads, 0)} conversões no período, todas sem valor.",
            "As ações de conversão da conta não têm valor definido (nem fixo, nem dinâmico).",
            "Com valor por conversão, o Google pode otimizar lances por retorno e o relatório passa a mostrar "
            "ROAS; sem isso, conversões baratas e caras valem igual para o algoritmo.",
            "tracking_fix",
            "Definir um valor para as conversões no Google Ads (valor médio da venda × taxa de fechamento, ou "
            "valor dinâmico pela tag) e conferir se a conversão principal é a correta.",
            "Melhor alocação de lances ao longo de semanas; não há ganho imediato garantido.",
            "Um valor mal estimado distorce a otimização; revise-o quando houver vendas confirmadas.",
            "Valor de conversão reportado e custo por conversão nos 14 dias seguintes.",
            "média", True, 1.2,
            evidence=[ev("Conversões", num(camp_leads, 0)), ev("Valor de conversão reportado", brl(0.0))],
            alternatives=["O valor pode estar configurado em outra conversão, fora da coluna principal."],
        ))
    return drafts
