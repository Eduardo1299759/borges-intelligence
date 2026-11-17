"""IA no Borges Core: interpreta a pergunta e redige a resposta a partir dos fatos já calculados.

A IA não calcula indicadores nem cria recomendações. Recebe os fatos (indicadores da conta, qualidade dos
dados, recomendações já geradas pelas regras) e devolve, em JSON validado, a resposta em português e quais
recomendações respondem à pergunta. Salvaguardas em app/ai/runner.py.
Dados enviados à Anthropic: nome do cliente, nomes de campanhas/anúncios e métricas agregadas. Nenhum
dado pessoal de leads.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.ai import runner
from app.ai.runner import unsupported_numbers  # noqa: F401  (reexportado para compatibilidade)
from app.models import Client

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


def narrate(db: Session, client: Client, run_id: int | None, question: str, facts: dict[str, Any]
            ) -> dict[str, Any] | None:
    """{"answer", "relevant_ids", "model", "cost_usd"}; {"error"} se a IA falhou; None se desligada."""
    facts_text = json.dumps(facts, ensure_ascii=False, default=str)
    result = runner.run_structured(
        db, purpose=PURPOSE, client_id=client.id, analysis_run_id=run_id, system=SYSTEM_PROMPT,
        user_text=f"Pergunta do gestor: {question}\n\nFatos (JSON):\n{facts_text}", schema=OUTPUT_SCHEMA,
        guard_numbers_against=facts_text + " " + question,
    )
    if result is None:
        return None
    if not result.ok:
        return {"error": result.error}
    try:
        answer = str(result.data["answer"]).strip()
        ids = [int(i) for i in result.data["relevant_recommendation_ids"]]
    except (KeyError, TypeError, ValueError):
        return {"error": "IA não usada: resposta em formato inválido."}
    if not answer:
        return {"error": "Resposta da IA descartada: resposta vazia."}
    known = {r["id"] for r in facts.get("recommendations", [])}
    return {"answer": answer, "relevant_ids": [i for i in ids if i in known], "model": result.model,
            "cost_usd": result.cost_usd}
