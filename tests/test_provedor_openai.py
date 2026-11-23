"""Testes do provedor de extração estruturada."""

from types import SimpleNamespace
from typing import cast

import pytest
from openai import OpenAI
from pydantic import ValidationError

from agente.modelos import ResultadoExtracao
from agente.provedor_openai import ProvedorOpenAI


class RespostasFalsas:
    """Simula o endpoint de respostas da OpenAI."""

    def parse(self, **_kwargs: object) -> SimpleNamespace:
        return SimpleNamespace(output_parsed=None)


class ClienteFalso:
    """Simula o cliente da OpenAI sem chamadas externas."""

    responses = RespostasFalsas()


def test_rejeita_resposta_sem_extracao_estruturada() -> None:
    cliente = cast(OpenAI, ClienteFalso())
    provedor = ProvedorOpenAI(cliente=cliente)

    with pytest.raises(
        ValueError,
        match="A OpenAI não retornou uma extração estruturada.",
    ):
        provedor.extrair("Extrato bancário fictício.")


class RespostasComErro:
    """Simula uma falha durante a chamada ao endpoint da OpenAI."""

    def parse(self, **_kwargs: object) -> SimpleNamespace:
        raise RuntimeError("Falha simulada no provedor.")


class ClienteComErro:
    """Simula um cliente cuja chamada ao endpoint falha."""

    responses = RespostasComErro()


def test_propaga_excecao_ocorrida_na_chamada_ao_provedor() -> None:
    cliente = cast(OpenAI, ClienteComErro())
    provedor = ProvedorOpenAI(cliente=cliente)

    with pytest.raises(RuntimeError, match="Falha simulada no provedor."):
        provedor.extrair("Extrato bancário fictício.")


class RespostasComErroValidacao:
    """Simula uma falha de validação durante o processamento da resposta."""

    def parse(self, **_kwargs: object) -> SimpleNamespace:
        ResultadoExtracao.model_validate(
            {
                "itens": [
                    {
                        "descricao": "PIX RECEBIDO",
                    }
                ]
            }
        )
        return SimpleNamespace(output_parsed=None)


class ClienteComErroValidacao:
    """Simula um cliente que recebe dados estruturados inválidos."""

    responses = RespostasComErroValidacao()


def test_propaga_erro_de_validacao_pydantic() -> None:
    cliente = cast(OpenAI, ClienteComErroValidacao())
    provedor = ProvedorOpenAI(cliente=cliente)

    with pytest.raises(ValidationError):
        provedor.extrair("Extrato bancário fictício.")

class RespostasComErroConexao:
    """Simula uma falha de conexao com a API."""

    def parse(self, **_kwargs: object) -> SimpleNamespace:
        import httpx2
        from openai import APIConnectionError

        request = httpx2.Request(
            "POST",
            "https://api.openai.com/v1/responses",
        )

        raise APIConnectionError(
            message="Falha simulada de conexao.",
            request=request,
        )


class ClienteComErroConexao:
    """Simula um cliente com falha de conexao."""

    responses = RespostasComErroConexao()


def test_propaga_erro_de_conexao() -> None:
    from openai import APIConnectionError

    cliente = cast(OpenAI, ClienteComErroConexao())
    provedor = ProvedorOpenAI(cliente=cliente)

    with pytest.raises(
        APIConnectionError,
        match="Falha simulada de conexao.",
    ):
        provedor.extrair("Extrato bancario ficticio.")


class RespostasComTimeout:
    """Simula um timeout durante a chamada a API."""

    def parse(self, **_kwargs: object) -> SimpleNamespace:
        import httpx2
        from openai import APITimeoutError

        request = httpx2.Request(
            "POST",
            "https://api.openai.com/v1/responses",
        )

        raise APITimeoutError(request=request)


class ClienteComTimeout:
    """Simula um cliente cuja chamada excede o tempo limite."""

    responses = RespostasComTimeout()


def test_propaga_erro_de_timeout() -> None:
    from openai import APITimeoutError

    cliente = cast(OpenAI, ClienteComTimeout())
    provedor = ProvedorOpenAI(cliente=cliente)

    with pytest.raises(APITimeoutError):
        provedor.extrair("Extrato bancario ficticio.")