"""Testes do fluxo experimental de avaliação de regressão."""

from pathlib import Path

import pytest

import agente.avaliacao_regressao as avaliacao_regressao
from agente.avaliador import ResultadoCaso
from agente.provedor_openai import PROMPT_ORIGINAL


class ProvedorFalso:
    """Substituto do provedor real para testes sem chamadas externas."""

    def __init__(self, instrucoes: str) -> None:
        self.modelo = "modelo-teste"
        self.instrucoes = instrucoes


def test_prompt_regressao_preserva_original() -> None:
    """Confirma que a variante acrescenta a instrução incorreta ao prompt original."""
    assert avaliacao_regressao.PROMPT_REGRESSAO.startswith(PROMPT_ORIGINAL)
    assert "ignore os marcadores C e D" in avaliacao_regressao.PROMPT_REGRESSAO
    assert avaliacao_regressao.VARIANTE_PROMPT == "regressao-v1"


@pytest.mark.parametrize(
    ("quality_gate_aprovado", "codigo_esperado"),
    [(True, 0), (False, 1)],
)
def test_main_executa_fluxo_experimental(
    monkeypatch: pytest.MonkeyPatch,
    quality_gate_aprovado: bool,
    codigo_esperado: int,
) -> None:
    eventos: list[str] = []
    provedores: list[ProvedorFalso] = []
    caminhos_avaliacao: list[Path] = []
    dados_relatorio: list[tuple[str, Path, str | None]] = []

    resultados = [
        ResultadoCaso(
            id=1,
            aprovado=quality_gate_aprovado,
            movimentacoes_esperadas=1,
            movimentacoes_extraidas=1 if quality_gate_aprovado else 0,
        )
    ]

    def criar_provedor(instrucoes: str) -> ProvedorFalso:
        provedor = ProvedorFalso(instrucoes)
        provedores.append(provedor)
        return provedor

    def avaliar(provedor: ProvedorFalso, caminho: Path) -> list[ResultadoCaso]:
        eventos.append("avaliar")
        caminhos_avaliacao.append(caminho)
        assert provedor.instrucoes == avaliacao_regressao.PROMPT_REGRESSAO
        return resultados

    def salvar(
        resultados_avaliados: list[ResultadoCaso],
        modelo: str,
        caminho: Path,
        variante_prompt: str | None = None,
    ) -> None:
        eventos.append("salvar")
        dados_relatorio.append((modelo, caminho, variante_prompt))

    def verificar(_resultados: list[ResultadoCaso]) -> bool:
        eventos.append("quality_gate")
        return quality_gate_aprovado

    monkeypatch.setattr(
        avaliacao_regressao,
        "ProvedorOpenAI",
        criar_provedor,
    )
    monkeypatch.setattr(avaliacao_regressao, "avaliar_golden_set", avaliar)
    monkeypatch.setattr(
        avaliacao_regressao,
        "imprimir_relatorio",
        lambda _resultados: eventos.append("imprimir"),
    )
    monkeypatch.setattr(avaliacao_regressao, "salvar_relatorio", salvar)
    monkeypatch.setattr(
        avaliacao_regressao,
        "verificar_quality_gate",
        verificar,
    )

    codigo_saida = avaliacao_regressao.main()

    raiz = Path(avaliacao_regressao.__file__).resolve().parents[2]
    caminho_casos_esperado = raiz / "evals" / "casos_ouro.jsonl"
    caminho_relatorio_esperado = raiz / "resultados" / "avaliacao_regressao.json"

    assert codigo_saida == codigo_esperado
    assert len(provedores) == 1
    assert provedores[0].instrucoes == avaliacao_regressao.PROMPT_REGRESSAO
    assert caminhos_avaliacao == [caminho_casos_esperado]
    assert dados_relatorio == [
        ("modelo-teste", caminho_relatorio_esperado, "regressao-v1")
    ]
    assert eventos == ["avaliar", "imprimir", "salvar", "quality_gate"]