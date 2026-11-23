"""Testes da camada modular de observabilidade com Langfuse."""

import json
from contextlib import nullcontext
from pathlib import Path
from typing import Any

import pytest

from agente.avaliador import avaliar_golden_set
from agente.modelos import ResultadoExtracao
from agente.observabilidade import (
    ObservadorLangfuse,
    ObservadorNulo,
    criar_observador,
)
from agente.provedores import MetadadosExtracao


class ClienteLangfuseFalso:
    """Simula o cliente Langfuse SDK v5+ sem chamadas de rede."""

    def __init__(self, *, falhar: bool = False) -> None:
        self.falhar = falhar
        self.observacoes: list[dict[str, Any]] = []
        self.flushes = 0

    def start_as_current_observation(self, **kwargs: Any) -> Any:
        if self.falhar:
            raise RuntimeError("Falha simulada no Langfuse.")
        self.observacoes.append(kwargs)
        return nullcontext()

    def flush(self) -> None:
        if self.falhar:
            raise RuntimeError("Falha simulada no flush.")
        self.flushes += 1


def test_criar_observador_retorna_nulo_sem_credenciais(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)

    observador = criar_observador()

    assert isinstance(observador, ObservadorNulo)
    observador.registrar_caso(
        caso_id=1,
        entrada="texto",
        aprovado=True,
        movimentacoes_esperadas=1,
        movimentacoes_extraidas=1,
        latencia_ms=12.5,
    )
    observador.finalizar({"total_casos": 1})


def test_observador_langfuse_registra_geracao_com_custo_estimado() -> None:
    cliente = ClienteLangfuseFalso()
    observador = ObservadorLangfuse(cliente=cliente, execucao_id="exec-123")
    metadados = MetadadosExtracao(
        provedor="bedrock",
        modelo="anthropic.claude-3-5-sonnet-20241022-v2:0",
        versao_prompt="original-v1",
        latencia_ms=42.3,
        tokens_entrada=100,
        tokens_saida=50,
        custo_real_usd=None,
        custo_estimado_usd=0.00105,
    )

    observador.registrar_caso(
        caso_id=7,
        entrada="PIX RECEBIDO 150,00",
        aprovado=True,
        movimentacoes_esperadas=1,
        movimentacoes_extraidas=1,
        latencia_ms=42.3,
        metadados=metadados,
    )
    observador.finalizar({"total_casos": 1, "aprovados": 1})

    assert len(cliente.observacoes) == 2
    geracao = cliente.observacoes[0]
    assert geracao["as_type"] == "generation"
    assert geracao["model"] == "anthropic.claude-3-5-sonnet-20241022-v2:0"
    assert geracao["version"] == "original-v1"
    assert geracao["usage_details"] == {"input": 100, "output": 50}
    assert geracao["cost_details"] == {"total": 0.00105}
    assert geracao["metadata"]["execucao_id"] == "exec-123"
    assert geracao["metadata"]["provedor"] == "bedrock"
    assert geracao["metadata"]["origem_custo"] == "estimado"
    assert geracao["level"] == "DEFAULT"

    span_final = cliente.observacoes[1]
    assert span_final["as_type"] == "span"
    assert span_final["name"] == "avaliacao-golden-set"
    assert cliente.flushes == 1


def test_observador_langfuse_nao_inventa_tokens_ou_custo_quando_indisponiveis() -> None:
    cliente = ClienteLangfuseFalso()
    observador = ObservadorLangfuse(cliente=cliente, execucao_id="exec-456")
    metadados = MetadadosExtracao(
        provedor="openai",
        modelo="gpt-6.2-sol",
        versao_prompt="original-v1",
        latencia_ms=15.0,
    )

    observador.registrar_caso(
        caso_id=2,
        entrada="extrato",
        aprovado=False,
        movimentacoes_esperadas=1,
        movimentacoes_extraidas=0,
        latencia_ms=15.0,
        erro="APITimeoutError: timeout",
        metadados=metadados,
    )

    geracao = cliente.observacoes[0]
    assert "usage_details" not in geracao
    assert "cost_details" not in geracao
    assert geracao["metadata"]["origem_custo"] == "indisponivel"
    assert geracao["level"] == "ERROR"
    assert geracao["status_message"] == "APITimeoutError: timeout"


def test_observador_langfuse_nao_interrompe_fluxo_quando_sdk_falha() -> None:
    cliente = ClienteLangfuseFalso(falhar=True)
    observador = ObservadorLangfuse(cliente=cliente)

    observador.registrar_caso(
        caso_id=1,
        entrada="extrato",
        aprovado=True,
        movimentacoes_esperadas=1,
        movimentacoes_extraidas=1,
        latencia_ms=10.0,
    )
    observador.finalizar({"total_casos": 1})


def test_avaliar_golden_set_integra_observador_sem_acoplar_comparador(
    tmp_path: Path,
) -> None:
    item_esperado = {
        "descricao": "PIX RECEBIDO",
        "valor": 150.0,
        "data": "2026-01-05",
        "fonte": {"documento": "extrato.pdf", "pagina": 1},
    }
    caso = {
        "id": 1,
        "entrada": "Extrato ficticio",
        "esperado": {"itens": [item_esperado]},
    }
    caminho = tmp_path / "casos.jsonl"
    caminho.write_text(json.dumps(caso), encoding="utf-8")

    class ProvedorComMetadados:
        modelo = "modelo-simulado"
        ultimos_metadados = MetadadosExtracao(
            provedor="openai",
            modelo="modelo-simulado",
            versao_prompt="original-v1",
            latencia_ms=5.0,
            tokens_entrada=20,
            tokens_saida=10,
        )

        def extrair(self, _texto: str) -> ResultadoExtracao:
            return ResultadoExtracao.model_validate({"itens": [item_esperado]})

    cliente = ClienteLangfuseFalso()
    observador = ObservadorLangfuse(cliente=cliente, execucao_id="exec-int")

    resultados = avaliar_golden_set(
        ProvedorComMetadados(),
        caminho,
        observador=observador,
    )

    assert len(resultados) == 1
    assert resultados[0].aprovado is True
    assert len(cliente.observacoes) == 2
    assert cliente.flushes == 1
