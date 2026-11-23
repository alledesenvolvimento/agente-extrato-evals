"""Testes da funcao principal e do fluxo do Quality Gate."""

import pytest

import agente.avaliador as avaliador
from agente.avaliador import ResultadoCaso


class ProvedorFalso:
    """Substituto do provedor real para testes sem chamadas externas."""

    modelo = "modelo-teste"


def preparar_main(
    monkeypatch: pytest.MonkeyPatch,
    resultados: list[ResultadoCaso],
    eventos: list[str],
    aprovado: bool,
) -> None:
    """Substitui dependencias externas e registra a ordem das operacoes."""
    monkeypatch.setattr(avaliador, "ProvedorOpenAI", ProvedorFalso)
    monkeypatch.setattr(
        avaliador,
        "avaliar_golden_set",
        lambda provedor, caminho: resultados,
    )
    monkeypatch.setattr(
        avaliador,
        "imprimir_relatorio",
        lambda resultados_avaliados: eventos.append("imprimir"),
    )
    monkeypatch.setattr(
        avaliador,
        "salvar_relatorio",
        lambda resultados_avaliados, modelo, caminho: eventos.append("salvar"),
    )

    def verificar_resultados(_resultados_avaliados: list[ResultadoCaso]) -> bool:
        eventos.append("quality_gate")
        return aprovado

    monkeypatch.setattr(
        avaliador,
        "verificar_quality_gate",
        verificar_resultados,
    )


def criar_resultados(aprovado: bool) -> list[ResultadoCaso]:
    """Cria um resultado ficticio para o teste."""
    return [
        ResultadoCaso(
            id=1,
            aprovado=aprovado,
            movimentacoes_esperadas=1,
            movimentacoes_extraidas=1 if aprovado else 0,
        )
    ]


def test_main_retorna_zero_quando_quality_gate_aprova(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eventos: list[str] = []
    preparar_main(monkeypatch, criar_resultados(True), eventos, True)

    codigo_saida = avaliador.main()

    assert codigo_saida == 0
    assert eventos == ["imprimir", "salvar", "quality_gate"]


def test_main_retorna_um_quando_quality_gate_reprova(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eventos: list[str] = []
    preparar_main(monkeypatch, criar_resultados(False), eventos, False)

    codigo_saida = avaliador.main()

    assert codigo_saida == 1
    assert eventos == ["imprimir", "salvar", "quality_gate"]


def test_main_seleciona_provedor_via_cli_e_salva_em_saida_customizada(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    from pathlib import Path

    assert isinstance(tmp_path, Path)
    provedores_criados: list[tuple[str | None, str | None]] = []

    def criar_provedor_falso(
        nome_provedor: str | None = None,
        *,
        modelo: str | None = None,
        **_kwargs: object,
    ) -> ProvedorFalso:
        provedores_criados.append((nome_provedor, modelo))
        return ProvedorFalso()

    monkeypatch.setattr(avaliador, "criar_provedor", criar_provedor_falso)
    monkeypatch.setattr(
        avaliador,
        "avaliar_golden_set",
        lambda _provedor, _caminho, **_kw: criar_resultados(True),
    )
    caminho_saida = tmp_path / "relatorio_bedrock.json"

    codigo_saida = avaliador.main(
        [
            "--provedor",
            "bedrock",
            "--modelo",
            "anthropic.claude-3-5-haiku-20241022-v1:0",
            "--saida",
            str(caminho_saida),
        ]
    )

    assert codigo_saida == 0
    assert provedores_criados == [
        ("bedrock", "anthropic.claude-3-5-haiku-20241022-v1:0")
    ]
    assert caminho_saida.exists()
