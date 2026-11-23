"""Integração com AWS Bedrock (Converse API) para extração de extratos."""

import json
import logging
import os
import time
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

from agente.modelos import ResultadoExtracao
from agente.provedores import (
    PROMPT_ORIGINAL,
    VERSAO_PROMPT_ORIGINAL,
    MetadadosExtracao,
)

logger = logging.getLogger(__name__)

MODELO_BEDROCK_PADRAO = "anthropic.claude-3-5-sonnet-20241022-v2:0"
REGIAO_BEDROCK_PADRAO = "us-east-1"
NOME_FERRAMENTA_EXTRACAO = "registrar_extracao"

# Tabela explícita de referência (USD por 1M de tokens) apenas para estimativa.
# Modelos fora da tabela mantêm custo_estimado_usd=None sem inventar valores.
_PRECOS_USD_POR_MILHAO_TOKENS: dict[str, tuple[float, float]] = {
    "anthropic.claude-3-5-sonnet-20241022-v2:0": (3.00, 15.00),
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0": (3.00, 15.00),
    "anthropic.claude-3-5-haiku-20241022-v1:0": (0.80, 4.00),
    "us.anthropic.claude-3-5-haiku-20241022-v1:0": (0.80, 4.00),
}


class ProvedorBedrock:
    """Responsável por solicitar extrações estruturadas ao AWS Bedrock."""

    nome_provedor = "bedrock"

    def __init__(
        self,
        modelo: str | None = None,
        regiao: str | None = None,
        cliente: Any | None = None,
        instrucoes: str = PROMPT_ORIGINAL,
        versao_prompt: str = VERSAO_PROMPT_ORIGINAL,
        timeout_segundos: float = 30.0,
    ) -> None:
        load_dotenv()
        self.modelo = (
            modelo
            or os.getenv("AWS_BEDROCK_MODEL_ID")
            or MODELO_BEDROCK_PADRAO
        )
        self.regiao = (
            regiao
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or REGIAO_BEDROCK_PADRAO
        )
        self.instrucoes = instrucoes
        self.versao_prompt = versao_prompt
        self.timeout_segundos = timeout_segundos
        self.ultimos_metadados: MetadadosExtracao | None = None

        if cliente is not None:
            self.cliente = cliente
        else:
            config = Config(
                connect_timeout=timeout_segundos,
                read_timeout=timeout_segundos,
                retries={"max_attempts": 2, "mode": "standard"},
            )
            self.cliente = boto3.client(
                "bedrock-runtime",
                region_name=self.regiao,
                config=config,
            )

    def extrair(self, texto: str) -> ResultadoExtracao:
        """Extrai movimentações do texto usando Bedrock Converse API com tool use."""
        schema = ResultadoExtracao.model_json_schema()
        inicio = time.perf_counter()

        try:
            resposta = self.cliente.converse(
                modelId=self.modelo,
                system=[{"text": self.instrucoes}],
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": texto}],
                    }
                ],
                toolConfig={
                    "tools": [
                        {
                            "toolSpec": {
                                "name": NOME_FERRAMENTA_EXTRACAO,
                                "description": (
                                    "Registra as movimentações bancárias extraídas "
                                    "no formato estruturado."
                                ),
                                "inputSchema": {"json": schema},
                            }
                        }
                    ],
                    "toolChoice": {"tool": {"name": NOME_FERRAMENTA_EXTRACAO}},
                },
            )
        except (ClientError, BotoCoreError) as erro:
            logger.error(
                "Erro ao chamar AWS Bedrock (modelo=%s, regiao=%s): %s",
                self.modelo,
                self.regiao,
                type(erro).__name__,
            )
            raise

        latencia_ms = round((time.perf_counter() - inicio) * 1000, 2)
        tokens_entrada, tokens_saida = _extrair_uso_bedrock(resposta)
        custo_estimado = _estimar_custo_usd(
            self.modelo,
            tokens_entrada,
            tokens_saida,
        )

        self.ultimos_metadados = MetadadosExtracao(
            provedor=self.nome_provedor,
            modelo=self.modelo,
            versao_prompt=self.versao_prompt,
            latencia_ms=latencia_ms,
            tokens_entrada=tokens_entrada,
            tokens_saida=tokens_saida,
            custo_real_usd=None,
            custo_estimado_usd=custo_estimado,
        )

        payload = _extrair_payload_resposta(resposta)
        return ResultadoExtracao.model_validate(payload)


def _extrair_uso_bedrock(resposta: dict[str, Any]) -> tuple[int | None, int | None]:
    """Extrai contagem de tokens retornada pelo Bedrock, se disponível."""
    uso = resposta.get("usage")
    if not isinstance(uso, dict):
        return None, None

    entrada = uso.get("inputTokens")
    saida = uso.get("outputTokens")
    tokens_entrada = (
        entrada if isinstance(entrada, int) and not isinstance(entrada, bool) else None
    )
    tokens_saida = (
        saida if isinstance(saida, int) and not isinstance(saida, bool) else None
    )
    return tokens_entrada, tokens_saida


def _estimar_custo_usd(
    modelo: str,
    tokens_entrada: int | None,
    tokens_saida: int | None,
) -> float | None:
    """Calcula custo estimado em USD apenas para modelos com tabela conhecida."""
    if tokens_entrada is None or tokens_saida is None:
        return None

    precos = _PRECOS_USD_POR_MILHAO_TOKENS.get(modelo)
    if precos is None:
        return None

    preco_entrada, preco_saida = precos
    custo = (tokens_entrada * preco_entrada + tokens_saida * preco_saida) / 1_000_000
    return round(custo, 8)


def _extrair_payload_resposta(resposta: dict[str, Any]) -> dict[str, Any]:
    """Extrai o dicionário estruturado da resposta do Bedrock (toolUse ou texto JSON)."""
    output = resposta.get("output")
    if not isinstance(output, dict):
        raise ValueError("Resposta do AWS Bedrock sem campo 'output'.")

    message = output.get("message")
    if not isinstance(message, dict):
        raise ValueError("Resposta do AWS Bedrock sem campo 'output.message'.")

    content = message.get("content")
    if not isinstance(content, list):
        raise ValueError("Resposta do AWS Bedrock sem blocos de conteúdo.")

    for bloco in content:
        if not isinstance(bloco, dict):
            continue
        tool_use = bloco.get("toolUse")
        if (
            isinstance(tool_use, dict)
            and tool_use.get("name") == NOME_FERRAMENTA_EXTRACAO
        ):
            entrada_tool = tool_use.get("input")
            if isinstance(entrada_tool, dict):
                return entrada_tool

    for bloco in content:
        if not isinstance(bloco, dict):
            continue
        texto = bloco.get("text")
        if isinstance(texto, str) and texto.strip():
            try:
                dados = json.loads(texto)
            except json.JSONDecodeError as erro:
                raise ValueError(
                    "O AWS Bedrock retornou texto inválido em vez de JSON estruturado."
                ) from erro
            if isinstance(dados, dict):
                return dados

    raise ValueError("O AWS Bedrock não retornou uma extração estruturada.")
