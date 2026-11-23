"""Testes do Quality Gate da avaliação."""

from agente.avaliador import ResultadoCaso, verificar_quality_gate


def criar_resultados(total: int, aprovados: int) -> list[ResultadoCaso]:
    """Cria resultados fictícios para testar o limite de aprovação."""
    return [
        ResultadoCaso(
            id=indice,
            aprovado=indice <= aprovados,
            movimentacoes_esperadas=1,
            movimentacoes_extraidas=1,
        )
        for indice in range(1, total + 1)
    ]


def test_aprova_quando_taxa_supera_limite() -> None:
    resultados = criar_resultados(total=20, aprovados=20)

    assert verificar_quality_gate(resultados)


def test_aprova_quando_taxa_atinge_exatamente_90_porcento() -> None:
    resultados = criar_resultados(total=20, aprovados=18)

    assert verificar_quality_gate(resultados)


def test_reprova_quando_taxa_fica_abaixo_de_90_porcento() -> None:
    resultados = criar_resultados(total=20, aprovados=17)

    assert not verificar_quality_gate(resultados)


def test_reprova_quando_nao_existem_resultados() -> None:
    assert not verificar_quality_gate([])
