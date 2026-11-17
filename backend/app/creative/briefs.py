"""Briefings de criativo com 3 a 5 variações para teste.

Com a IA ativa, as variações são escritas pela IA a partir dos fatos (cliente, oferta informada, desempenho
dos anúncios). Proibido inventar preço, desconto, prazo ou promessa: todo número das variações precisa estar
nos fatos (por exemplo, na oferta que o gestor digitou). Sem IA, o Borges monta um modelo com ângulos
clássicos e campos a completar.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.ai import runner
from app.decision.engine import brl, pct
from app.models import Client

CTAS = ["Saiba mais", "Enviar mensagem", "Pedir agora", "Comprar agora", "Cadastre-se", "Ver cardápio",
        "Agendar", "Fale conosco"]
FORMATS = ["1:1", "4:5", "9:16"]

SYSTEM = """Você é o Creative Intelligence de uma agência de tráfego pago. Escreva variações de anúncio para \
Meta Ads (Facebook e Instagram), em português do Brasil, a partir dos fatos em JSON.

Regras:
- Cada variação testa UM ângulo diferente e diz qual hipótese está sendo testada.
- Não invente preço, desconto, prazo, garantia, número de clientes ou qualquer dado: use apenas o que está \
na oferta e nos fatos. Se faltar um dado, escreva sem ele.
- Título com até 40 caracteres; texto principal com até 300 caracteres; linguagem clara, sem exageros nem \
promessas que dependam de resultado.
- O CTA deve ser exatamente um dos valores permitidos.
- visual_brief descreve a peça para um designer: cena, elementos, texto na imagem (curto) e proporção.
- Respeite as políticas de anúncio da Meta (sem atributos pessoais do público, sem antes/depois enganoso)."""

SCHEMA = {
    "type": "object",
    "properties": {
        "variations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "angle": {"type": "string"},
                    "test_hypothesis": {"type": "string"},
                    "format": {"type": "string", "enum": FORMATS},
                    "headline": {"type": "string"},
                    "primary_text": {"type": "string"},
                    "cta": {"type": "string", "enum": CTAS},
                    "visual_brief": {"type": "string"},
                },
                "required": ["name", "angle", "test_hypothesis", "format", "headline", "primary_text", "cta",
                             "visual_brief"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["variations"],
    "additionalProperties": False,
}


def template_variations(offer: str, audience: str) -> list[dict[str, str]]:
    """Modelo sem IA: ângulos clássicos, com o texto da oferta e campos a completar entre colchetes."""
    base = offer.strip().rstrip(".")
    return [
        {"name": "Benefício direto", "angle": "Benefício principal da oferta, sem rodeios",
         "test_hypothesis": "Deixar o benefício explícito no início aumenta a taxa de clique → lead.",
         "format": "4:5", "headline": "[benefício principal em até 40 caracteres]",
         "primary_text": f"{base}. [explique em uma frase por que isso resolve o problema de {audience}].",
         "cta": "Saiba mais", "visual_brief": "Produto/serviço em destaque, fundo limpo, texto curto com o benefício."},
        {"name": "Prova social", "angle": "Experiência de clientes reais",
         "test_hypothesis": "Depoimentos reduzem a desconfiança e melhoram a qualidade do lead.",
         "format": "9:16", "headline": "[frase de um cliente real]",
         "primary_text": f"[depoimento real e autorizado]. {base}.",
         "cta": "Enviar mensagem",
         "visual_brief": "Vídeo curto de um cliente (com autorização) ou print de avaliação."},
        {"name": "Objeção principal", "angle": "Responde à dúvida que mais trava a compra",
         "test_hypothesis": "Responder à objeção no anúncio filtra curiosos e aumenta a conversão em venda.",
         "format": "1:1", "headline": "[a objeção, como pergunta]",
         "primary_text": f"[resposta direta à objeção]. {base}.",
         "cta": "Fale conosco", "visual_brief": "Pergunta grande na imagem e a resposta em uma linha."},
    ]


def facts_for(client: Client, objective: str, audience: str, offer: str, angle: str | None,
              reference: dict[str, Any] | None, recommendation: dict[str, Any] | None) -> dict[str, Any]:
    ref = None
    if reference:
        ref = {"anuncio": reference["name"], "campanha": reference["campaign"],
               "classificacao": reference["class_label"], "ctr": pct(reference["ctr"]),
               "custo_por_lead": brl(reference["cpl"]), "custo_por_lead_campanha": brl(reference["campaign_cpl"])}
    return {"cliente": client.name, "segmento": client.segment,
            "objetivo_comercial_do_cliente": client.business_goal,
            "objetivo_do_criativo": objective, "publico": audience, "oferta": offer, "angulo_sugerido": angle,
            "anuncio_de_referencia": ref, "recomendacao": recommendation, "ctas_permitidos": CTAS}


def generate(db: Session, client: Client, facts: dict[str, Any], n: int = 4
             ) -> tuple[list[dict[str, Any]], str, str | None, str | None]:
    """Retorna (variações, fonte, modelo da IA, observação)."""
    facts_text = json.dumps(facts, ensure_ascii=False, default=str)
    result = runner.run_structured(
        db, purpose="creative_brief", client_id=client.id, system=SYSTEM,
        user_text=f"Escreva {n} variações.\n\nFatos (JSON):\n{facts_text}", schema=SCHEMA,
        guard_numbers_against=facts_text,
    )
    if result is not None and result.ok:
        variations = [v for v in result.data.get("variations", []) if v.get("cta") in CTAS][:5]
        if len(variations) >= 2:
            return variations, "ia", result.model, None
        note = "IA não usada: a resposta veio com menos de 2 variações válidas."
    else:
        note = result.error if result is not None else None
    return template_variations(facts["oferta"], facts["publico"]), "modelo", None, note
