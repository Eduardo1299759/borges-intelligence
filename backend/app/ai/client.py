"""Construção do cliente da Anthropic (SDK oficial). Isolado para os testes poderem substituí-lo."""
import anthropic

from app.core.config import get_settings


def build_client(api_key: str) -> anthropic.Anthropic:
    # Uma chamada de análise leva de segundos a ~1 minuto; 2 novas tentativas automáticas (padrão do SDK).
    # base_url só é definido em testes (BORGES_ANTHROPIC_BASE_URL); em uso normal vale o padrão do SDK.
    base_url = get_settings().anthropic_base_url or None
    return anthropic.Anthropic(api_key=api_key, timeout=180.0, max_retries=2, base_url=base_url)
