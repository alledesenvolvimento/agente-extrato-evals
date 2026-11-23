"""Integração com a API da OpenAI para extração de extratos."""

import time

from dotenv import load_dotenv
from openai import OpenAI

from agente.modelos import ResultadoExtracao
from agente.provedores import (
    PROMPT_ORIGINAL,
    VERSAO_PROMPT_ORIGINAL,
    MetadadosExtracao,
)

__all__ = ["PROMPT_ORIGINAL", "ProvedorOpenAI"]


class ProvedorOpenAI:
    """Responsável por solicitar extrações estruturadas à OpenAI."""

    nome_provedor = "openai"

    def __init__(
        self,
        modelo: str = "gpt-6.2-sol",
        cliente: OpenAI | None = None,
        instrucoes: str = PROMPT_ORIGINAL,
        versao_prompt: str = VERSAO_PROMPT_ORIGINAL,
    ) -> None:
        load_dotenv()
        self.modelo = modelo
        self.instrucoes = instrucoes
        self.versao_prompt = versao_prompt
        self.cliente = cliente or OpenAI()
        self.ultimos_metadados: MetadadosExtracao | None = None

    def extrair(self, texto: str) -> ResultadoExtracao:
        """Extrai movimentações do texto de um extrato bancário."""
        inicio = time.perf_counter()
        resposta = self.cliente.responses.parse(
            model=self.modelo,
            input=[
                {
                    "role": "system",
                    "content": self.instrucoes,
                },
                {
                    "role": "user",
                    "content": texto,
                },
            ],
            text_format=ResultadoExtracao,
        )
        latencia_ms = round((time.perf_counter() - inicio) * 1000, 2)

        uso = getattr(resposta, "usage", None)
        tokens_entrada = _extrair_int_opcional(uso, "input_tokens")
        tokens_saida = _extrair_int_opcional(uso, "output_tokens")

        self.ultimos_metadados = MetadadosExtracao(
            provedor=self.nome_provedor,
            modelo=self.modelo,
            versao_prompt=self.versao_prompt,
            latencia_ms=latencia_ms,
            tokens_entrada=tokens_entrada,
            tokens_saida=tokens_saida,
            custo_real_usd=None,
            custo_estimado_usd=None,
        )

        resultado = resposta.output_parsed

        if resultado is None:
            raise ValueError("A OpenAI não retornou uma extração estruturada.")

        return resultado


def _extrair_int_opcional(objeto: object, atributo: str) -> int | None:
    """Extrai um inteiro positivo/zero de um objeto de uso, se disponível."""
    if objeto is None:
        return None
    valor = getattr(objeto, atributo, None)
    if isinstance(valor, int) and not isinstance(valor, bool):
        return valor
    return None
