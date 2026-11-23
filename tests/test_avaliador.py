"""Testes das funções de comparação e persistência do avaliador."""

import json
from datetime import date
from pathlib import Path

from agente.avaliador import (
    ResultadoCaso,
    comparar_resultados,
    salvar_relatorio,
)
from agente.modelos import Fonte, ItemExtrato, ResultadoExtracao


def criar_item(
    descricao: str = "PIX RECEBIDO",
    valor: float = 150.00,
) -> ItemExtrato:
    """Cria uma movimentação fictícia para os testes."""
    return ItemExtrato(
        descricao=descricao,
        valor=valor,
        data=date(2026, 1, 5),
        fonte=Fonte(documento="extrato.pdf", pagina=1),
    )


def test_compara_resultados_iguais() -> None:
    esperado = ResultadoExtracao(itens=[criar_item()])
    obtido = ResultadoExtracao(itens=[criar_item()])

    assert comparar_resultados(esperado, obtido)


def test_ignora_diferencas_de_maiusculas_e_espacos() -> None:
    esperado = ResultadoExtracao(itens=[criar_item("PIX RECEBIDO")])
    obtido = ResultadoExtracao(itens=[criar_item("  Pix   Recebido  ")])

    assert comparar_resultados(esperado, obtido)


def test_ignora_ordem_das_movimentacoes() -> None:
    esperado = ResultadoExtracao(
        itens=[
            criar_item("PIX RECEBIDO", 150.00),
            criar_item("PAGAMENTO ENERGIA", -230.45),
        ]
    )
    obtido = ResultadoExtracao(
        itens=[
            criar_item("PAGAMENTO ENERGIA", -230.45),
            criar_item("PIX RECEBIDO", 150.00),
        ]
    )

    assert comparar_resultados(esperado, obtido)


def test_reprova_valor_diferente() -> None:
    esperado = ResultadoExtracao(itens=[criar_item(valor=150.00)])
    obtido = ResultadoExtracao(itens=[criar_item(valor=150.01)])

    assert not comparar_resultados(esperado, obtido)


def test_aprova_duas_listas_vazias() -> None:
    esperado = ResultadoExtracao(itens=[])
    obtido = ResultadoExtracao(itens=[])

    assert comparar_resultados(esperado, obtido)


def test_reprova_lista_vazia_quando_ha_item_esperado() -> None:
    esperado = ResultadoExtracao(itens=[criar_item()])
    obtido = ResultadoExtracao(itens=[])

    assert not comparar_resultados(esperado, obtido)


def test_salva_relatorio_json(tmp_path: Path) -> None:
    caminho = tmp_path / "resultados" / "avaliacao.json"
    resultados = [
        ResultadoCaso(
            id=1,
            aprovado=True,
            movimentacoes_esperadas=1,
            movimentacoes_extraidas=1,
        )
    ]

    salvar_relatorio(resultados, "modelo-teste", caminho)

    assert caminho.exists()

    dados = json.loads(caminho.read_text(encoding="utf-8"))

    assert dados["modelo"] == "modelo-teste"
    assert dados["resumo"]["total_casos"] == 1
    assert dados["resumo"]["aprovados"] == 1
    assert dados["resumo"]["reprovados"] == 0
    assert dados["resumo"]["taxa_aprovacao_percentual"] == 100.0
    assert dados["casos"][0]["status"] == "aprovado"
    assert dados["data_execucao"]


def test_salva_relatorio_com_caso_reprovado(tmp_path: Path) -> None:
    caminho = tmp_path / "avaliacao.json"
    resultados = [
        ResultadoCaso(
            id=2,
            aprovado=False,
            movimentacoes_esperadas=2,
            movimentacoes_extraidas=1,
            erro="Resultado diferente do esperado.",
        )
    ]

    salvar_relatorio(resultados, "modelo-teste", caminho)

    dados = json.loads(caminho.read_text(encoding="utf-8"))

    assert dados["resumo"]["reprovados"] == 1
    assert dados["resumo"]["taxa_aprovacao_percentual"] == 0.0
    assert dados["casos"][0]["erro"] == "Resultado diferente do esperado."
