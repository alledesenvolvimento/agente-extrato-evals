"""Testes do provedor AWS Bedrock e da fábrica de provedores."""

from typing import Any

import pytest
from botocore.exceptions import BotoCoreError, ClientError, ReadTimeoutError
from pydantic import ValidationError

from agente.modelos import ResultadoExtracao
from agente.provedor_bedrock import MODELO_BEDROCK_PADRAO, ProvedorBedrock
from agente.provedor_openai import ProvedorOpenAI
from agente.provedores import criar_provedor


class ClienteBedrockSucessoTool:
    """Simula resposta válida do Bedrock via toolUse."""

    def __init__(self, *, com_uso: bool = True) -> None:
        self.com_uso = com_uso
        self.chamadas: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.chamadas.append(kwargs)
        resposta: dict[str, Any] = {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "toolUse": {
                                "toolUseId": "tool-1",
                                "name": "registrar_extracao",
                                "input": {
                                    "itens": [
                                        {
                                            "descricao": "PIX RECEBIDO",
                                            "valor": 150.0,
                                            "data": "2026-01-05",
                                            "fonte": {
                                                "documento": "extrato.pdf",
                                                "pagina": 1,
                                            },
                                        }
                                    ]
                                },
                            }
                        }
                    ],
                }
            }
        }
        if self.com_uso:
            resposta["usage"] = {"inputTokens": 120, "outputTokens": 45}
        return resposta


class ClienteBedrockTextoJSON:
    """Simula resposta válida do Bedrock em texto JSON."""

    def converse(self, **_kwargs: Any) -> dict[str, Any]:
        return {
            "output": {
                "message": {
                    "content": [
                        {
                            "text": (
                                '{"itens": [{"descricao": "TARIFA", "valor": -10.5, '
                                '"data": "2026-01-06", "fonte": '
                                '{"documento": "extrato.pdf", "pagina": 2}}]}'
                            )
                        }
                    ]
                }
            }
        }


class ClienteBedrockRespostaInvalida:
    """Simula resposta sem toolUse e sem JSON válido."""

    def __init__(self, resposta: dict[str, Any]) -> None:
        self.resposta = resposta

    def converse(self, **_kwargs: Any) -> dict[str, Any]:
        return self.resposta


class ClienteBedrockComErro:
    """Simula erro do SDK boto3/botocore."""

    def __init__(self, erro: Exception) -> None:
        self.erro = erro

    def converse(self, **_kwargs: Any) -> dict[str, Any]:
        raise self.erro


def test_bedrock_extrai_via_tool_use_e_registra_metadados() -> None:
    cliente = ClienteBedrockSucessoTool(com_uso=True)
    provedor = ProvedorBedrock(regiao="us-west-2", cliente=cliente)

    resultado = provedor.extrair("Extrato fictício.")

    assert isinstance(resultado, ResultadoExtracao)
    assert len(resultado.itens) == 1
    assert resultado.itens[0].descricao == "PIX RECEBIDO"
    assert resultado.itens[0].valor == 150.0

    assert len(cliente.chamadas) == 1
    assert cliente.chamadas[0]["modelId"] == MODELO_BEDROCK_PADRAO
    assert cliente.chamadas[0]["toolConfig"]["toolChoice"] == {
        "tool": {"name": "registrar_extracao"}
    }

    metadados = provedor.ultimos_metadados
    assert metadados is not None
    assert metadados.provedor == "bedrock"
    assert metadados.modelo == MODELO_BEDROCK_PADRAO
    assert metadados.tokens_entrada == 120
    assert metadados.tokens_saida == 45
    assert metadados.custo_real_usd is None
    assert metadados.custo_estimado_usd is not None
    assert metadados.latencia_ms >= 0.0


def test_bedrock_sem_tabela_preco_nao_inventa_custo() -> None:
    cliente = ClienteBedrockSucessoTool(com_uso=True)
    provedor = ProvedorBedrock(
        modelo="modelo-customizado-sem-tabela",
        cliente=cliente,
    )

    provedor.extrair("Extrato fictício.")

    assert provedor.ultimos_metadados is not None
    assert provedor.ultimos_metadados.custo_real_usd is None
    assert provedor.ultimos_metadados.custo_estimado_usd is None


def test_bedrock_extrai_fallback_texto_json() -> None:
    provedor = ProvedorBedrock(cliente=ClienteBedrockTextoJSON())

    resultado = provedor.extrair("Extrato fictício.")

    assert len(resultado.itens) == 1
    assert resultado.itens[0].valor == -10.5
    assert provedor.ultimos_metadados is not None
    assert provedor.ultimos_metadados.tokens_entrada is None
    assert provedor.ultimos_metadados.tokens_saida is None


def test_bedrock_rejeita_texto_nao_json() -> None:
    cliente = ClienteBedrockRespostaInvalida(
        {"output": {"message": {"content": [{"text": "resposta invalida"}]}}}
    )
    provedor = ProvedorBedrock(cliente=cliente)

    with pytest.raises(ValueError, match="texto inválido"):
        provedor.extrair("Extrato fictício.")


def test_bedrock_rejeita_resposta_vazia() -> None:
    cliente = ClienteBedrockRespostaInvalida({"output": {"message": {"content": []}}})
    provedor = ProvedorBedrock(cliente=cliente)

    with pytest.raises(ValueError, match="não retornou uma extração estruturada"):
        provedor.extrair("Extrato fictício.")


def test_bedrock_propaga_erro_validacao_pydantic() -> None:
    cliente = ClienteBedrockRespostaInvalida(
        {
            "output": {
                "message": {
                    "content": [
                        {
                            "toolUse": {
                                "name": "registrar_extracao",
                                "input": {"itens": [{"descricao": "INCOMPLETO"}]},
                            }
                        }
                    ]
                }
            }
        }
    )
    provedor = ProvedorBedrock(cliente=cliente)

    with pytest.raises(ValidationError):
        provedor.extrair("Extrato fictício.")


def test_bedrock_propaga_client_error() -> None:
    erro = ClientError(
        {"Error": {"Code": "AccessDeniedException", "Message": "Acesso negado."}},
        "Converse",
    )
    provedor = ProvedorBedrock(cliente=ClienteBedrockComErro(erro))

    with pytest.raises(ClientError):
        provedor.extrair("Extrato fictício.")


def test_bedrock_propaga_timeout_botocore() -> None:
    erro = ReadTimeoutError(endpoint_url="https://bedrock-runtime.us-east-1.amazonaws.com")
    provedor = ProvedorBedrock(cliente=ClienteBedrockComErro(erro))

    with pytest.raises(BotoCoreError):
        provedor.extrair("Extrato fictício.")


def test_bedrock_le_configuracao_de_ambiente(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AWS_BEDROCK_MODEL_ID", "anthropic.claude-3-5-haiku-20241022-v1:0")
    monkeypatch.setenv("AWS_REGION", "sa-east-1")

    provedor = ProvedorBedrock(cliente=ClienteBedrockSucessoTool())

    assert provedor.modelo == "anthropic.claude-3-5-haiku-20241022-v1:0"
    assert provedor.regiao == "sa-east-1"


def test_criar_provedor_alterna_entre_openai_e_bedrock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "chave-teste-ficticia")
    monkeypatch.setenv("AWS_REGION", "us-east-1")

    provedor_openai = criar_provedor("openai")
    provedor_bedrock = criar_provedor("bedrock")

    assert isinstance(provedor_openai, ProvedorOpenAI)
    assert isinstance(provedor_bedrock, ProvedorBedrock)

    with pytest.raises(ValueError, match="Provedor desconhecido"):
        criar_provedor("desconhecido")
