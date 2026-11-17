"""Preços por milhão de tokens (US$), API da Anthropic. Fonte: tabela oficial de modelos (nov/2026).

Só modelos desta tabela podem ser escolhidos: sem preço conhecido, não há como respeitar o limite de gasto.
"""
from decimal import Decimal

PRICES: dict[str, tuple[Decimal, Decimal]] = {
    # modelo: (entrada, saída) em US$ por 1 milhão de tokens
    "claude-opus-5-5": (Decimal("4.00"), Decimal("20.00")),
    "claude-sonnet-5-5": (Decimal("2.00"), Decimal("10.00")),
    "claude-haiku-5-5": (Decimal("0.10"), Decimal("0.50")),
    # possíveis modelos de reserva (fallback) usados pela própria API quando o principal recusa
    "claude-opus-5": (Decimal("5.00"), Decimal("25.00")),
    "claude-opus-4-8": (Decimal("5.00"), Decimal("25.00")),
    "claude-sonnet-5": (Decimal("2.00"), Decimal("10.00")),
}
SELECTABLE = ("claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-5-5")
LABELS = {"claude-opus-5-5": "Claude Opus 5.5 (recomendado)", "claude-sonnet-5-5": "Claude Sonnet 5.5",
          "claude-haiku-5-5": "Claude Haiku 5.5 (mais barato)"}
MILLION = Decimal(1_000_000)


def cost(model: str, input_tokens: int, output_tokens: int) -> Decimal:
    """Custo de uma chamada. Para um modelo desconhecido usa o preço mais alto da tabela (conservador)."""
    price_in, price_out = PRICES.get(model, max(PRICES.values(), key=lambda p: p[1]))
    return (price_in * input_tokens + price_out * output_tokens) / MILLION


def worst_case(model: str, input_tokens_estimate: int, max_tokens: int) -> Decimal:
    """Pior custo possível: entrada estimada + todo o max_tokens de saída, no modelo mais caro entre o
    escolhido e as reservas que a API pode usar."""
    top_out = max(p[1] for p in PRICES.values())
    top_in = max(p[0] for p in PRICES.values())
    price_in, price_out = PRICES[model]
    return (max(price_in, top_in) * input_tokens_estimate + max(price_out, top_out) * max_tokens) / MILLION
