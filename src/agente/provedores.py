"""Contratos comuns, metadados e fábrica de provedores de extração."""

import os
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from agente.modelos import ResultadoExtracao

PROMPT_ORIGINAL = (
    "Extraia as movimentações bancárias do texto fornecido. "
    "Não invente informações. Preserve a descrição, a data "
    "e o valor. Valores positivos representam créditos e "
    "valores negativos representam débitos. Informe o "
    "documento e a página de origem de cada movimentação."
)

VERSAO_PROMPT_ORIGINAL = "original-v1"


@dataclass(frozen=True)
class MetadadosExtracao:
    """Metadados operacionais coletados durante uma extração."""

    provedor: str
    modelo: str
    versao_prompt: str
    latencia_ms: float
    tokens_entrada: int | None = None
    tokens_saida: int | None = None
    custo_real_usd: float | None = None
    custo_estimado_usd: float | None = None


@runtime_checkable
class ProvedorExtracao(Protocol):
    """Interface comum para provedores de extração estruturada."""

    modelo: str

    def extrair(self, texto: str) -> ResultadoExtracao:
        """Extrai movimentações bancárias de um texto."""
        ...


def obter_metadados_provedor(provedor: object) -> MetadadosExtracao | None:
    """Retorna os metadados da última extração, se o provedor os expuser."""
    metadados = getattr(provedor, "ultimos_metadados", None)
    if isinstance(metadados, MetadadosExtracao):
        return metadados
    return None


def criar_provedor(
    nome_provedor: str | None = None,
    *,
    modelo: str | None = None,
    instrucoes: str = PROMPT_ORIGINAL,
    versao_prompt: str = VERSAO_PROMPT_ORIGINAL,
) -> ProvedorExtracao:
    """Instancia o provedor configurado (OpenAI ou AWS Bedrock)."""
    from agente.provedor_bedrock import ProvedorBedrock
    from agente.provedor_openai import ProvedorOpenAI

    selecionado = (
        nome_provedor or os.getenv("AGENTE_PROVEDOR") or "openai"
    ).strip().casefold()

    if selecionado == "openai":
        if modelo is not None:
            return ProvedorOpenAI(
                modelo=modelo,
                instrucoes=instrucoes,
                versao_prompt=versao_prompt,
            )
        return ProvedorOpenAI(
            instrucoes=instrucoes,
            versao_prompt=versao_prompt,
        )

    if selecionado == "bedrock":
        if modelo is not None:
            return ProvedorBedrock(
                modelo=modelo,
                instrucoes=instrucoes,
                versao_prompt=versao_prompt,
            )
        return ProvedorBedrock(
            instrucoes=instrucoes,
            versao_prompt=versao_prompt,
        )

    raise ValueError(
        f"Provedor desconhecido: '{selecionado}'. Valores aceitos: 'openai', 'bedrock'."
    )
