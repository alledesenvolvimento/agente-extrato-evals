"""Testes das funções de comparação e persistência do avaliador."""

import json
from datetime import date
from pathlib import Path
from typing import cast

from agente.avaliador import (
    ResultadoCaso,
    avaliar_golden_set,
    comparar_resultados,
    salvar_relatorio,
)
from agente.modelos import Fonte, ItemExtrato, ResultadoExtracao
from agente.provedor_openai import ProvedorOpenAI


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
    assert dados["variante_prompt"] is None
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


def test_salva_relatorio_com_variante_prompt(tmp_path: Path) -> None:
    caminho = tmp_path / "avaliacao_regressao.json"
    resultados = [
        ResultadoCaso(
            id=1,
            aprovado=False,
            movimentacoes_esperadas=1,
            movimentacoes_extraidas=1,
            erro="Resultado diferente do esperado.",
        )
    ]

    salvar_relatorio(
        resultados,
        "modelo-teste",
        caminho,
        variante_prompt="regressao-v1",
    )

    dados = json.loads(caminho.read_text(encoding="utf-8"))

    assert dados["modelo"] == "modelo-teste"
    assert dados["variante_prompt"] == "regressao-v1"
    assert dados["resumo"]["reprovados"] == 1

class ProvedorSequencialFalso:
    """Simula uma falha no primeiro caso e sucesso no segundo."""

    def __init__(self, resultado: ResultadoExtracao) -> None:
        self.resultado = resultado
        self.chamadas = 0

    def extrair(self, _texto: str) -> ResultadoExtracao:
        self.chamadas += 1

        if self.chamadas == 1:
            raise RuntimeError("Falha simulada na extração.")

        return self.resultado


def test_registra_falha_e_continua_avaliando_proximos_casos(
    tmp_path: Path,
) -> None:
    item_esperado = {
        "descricao": "PIX RECEBIDO",
        "valor": 150.00,
        "data": "2026-01-05",
        "fonte": {
            "documento": "extrato.pdf",
            "pagina": 1,
        },
    }

    casos = [
        {
            "id": 1,
            "entrada": "Extrato fictício do primeiro caso.",
            "esperado": {"itens": [item_esperado]},
        },
        {
            "id": 2,
            "entrada": "Extrato fictício do segundo caso.",
            "esperado": {"itens": [item_esperado]},
        },
    ]

    caminho = tmp_path / "casos_ouro.jsonl"
    caminho.write_text(
        "\n".join(json.dumps(caso) for caso in casos),
        encoding="utf-8",
    )

    resultado_esperado = ResultadoExtracao.model_validate(
        {"itens": [item_esperado]}
    )
    provedor = ProvedorSequencialFalso(resultado_esperado)

    resultados = avaliar_golden_set(cast(ProvedorOpenAI, provedor), caminho)

    assert len(resultados) == 2

    assert resultados[0].id == 1
    assert not resultados[0].aprovado
    assert resultados[0].movimentacoes_esperadas == 1
    assert resultados[0].movimentacoes_extraidas == 0
    assert resultados[0].erro == (
        "RuntimeError: Falha simulada na extração."
    )

    assert resultados[1].id == 2
    assert resultados[1].aprovado
    assert resultados[1].movimentacoes_esperadas == 1
    assert resultados[1].movimentacoes_extraidas == 1
    assert resultados[1].erro is None

    assert provedor.chamadas == 2

class ProvedorComErroSequencial:
    """Simula uma falha inicial e sucesso na chamada seguinte."""

    def __init__(
        self,
        resultado: ResultadoExtracao,
        erro: Exception,
    ) -> None:
        self.resultado = resultado
        self.erro = erro
        self.chamadas = 0

    def extrair(self, _texto: str) -> ResultadoExtracao:
        self.chamadas += 1

        if self.chamadas == 1:
            raise self.erro

        return self.resultado


def executar_avaliacao_com_falha(
    tmp_path: Path,
    erro: Exception,
) -> tuple[list[ResultadoCaso], ProvedorComErroSequencial]:
    """Executa dois casos: o primeiro falha e o segundo deve passar."""

    item_esperado = {
        "descricao": "PIX RECEBIDO",
        "valor": 150.00,
        "data": "2026-01-05",
        "fonte": {
            "documento": "extrato.pdf",
            "pagina": 1,
        },
    }

    casos = [
        {
            "id": 1,
            "entrada": "Extrato ficticio do primeiro caso.",
            "esperado": {"itens": [item_esperado]},
        },
        {
            "id": 2,
            "entrada": "Extrato ficticio do segundo caso.",
            "esperado": {"itens": [item_esperado]},
        },
    ]

    caminho = tmp_path / "casos_ouro.jsonl"
    caminho.write_text(
        "\n".join(json.dumps(caso) for caso in casos),
        encoding="utf-8",
    )

    resultado_esperado = ResultadoExtracao.model_validate(
        {"itens": [item_esperado]}
    )

    provedor = ProvedorComErroSequencial(resultado_esperado, erro)
    resultados = avaliar_golden_set(cast(ProvedorOpenAI, provedor), caminho)

    return resultados, provedor


def test_avaliador_registra_falha_de_conexao_e_continua(
    tmp_path: Path,
) -> None:
    import httpx2
    from openai import APIConnectionError

    request = httpx2.Request(
        "POST",
        "https://api.openai.com/v1/responses",
    )
    erro = APIConnectionError(
        message="Falha simulada de conexao.",
        request=request,
    )

    resultados, provedor = executar_avaliacao_com_falha(tmp_path, erro)

    assert len(resultados) == 2
    assert resultados[0].aprovado is False
    assert resultados[0].movimentacoes_esperadas == 1
    assert resultados[0].movimentacoes_extraidas == 0
    assert resultados[0].erro == f"APIConnectionError: {erro}"

    assert resultados[1].aprovado is True
    assert resultados[1].movimentacoes_extraidas == 1
    assert resultados[1].erro is None
    assert provedor.chamadas == 2


def test_avaliador_registra_timeout_e_continua(
    tmp_path: Path,
) -> None:
    import httpx2
    from openai import APITimeoutError

    request = httpx2.Request(
        "POST",
        "https://api.openai.com/v1/responses",
    )
    erro = APITimeoutError(request=request)

    resultados, provedor = executar_avaliacao_com_falha(tmp_path, erro)

    assert len(resultados) == 2
    assert resultados[0].aprovado is False
    assert resultados[0].movimentacoes_esperadas == 1
    assert resultados[0].movimentacoes_extraidas == 0
    assert resultados[0].erro == f"APITimeoutError: {erro}"

    assert resultados[1].aprovado is True
    assert resultados[1].movimentacoes_extraidas == 1
    assert resultados[1].erro is None
    assert provedor.chamadas == 2

class ProvedorSempreSucesso:
    """Simula um provedor que extrai corretamente todos os casos."""

    def __init__(self, resultado: ResultadoExtracao) -> None:
        self.resultado = resultado
        self.chamadas = 0

    def extrair(self, _texto: str) -> ResultadoExtracao:
        self.chamadas += 1
        return self.resultado


def test_registra_falha_na_comparacao_e_continua(
    tmp_path: Path,
) -> None:
    from unittest.mock import patch


    item_esperado = {
        "descricao": "PIX RECEBIDO",
        "valor": 150.00,
        "data": "2026-01-05",
        "fonte": {
            "documento": "extrato.pdf",
            "pagina": 1,
        },
    }

    casos = [
        {
            "id": 1,
            "entrada": "Extrato ficticio do primeiro caso.",
            "esperado": {"itens": [item_esperado]},
        },
        {
            "id": 2,
            "entrada": "Extrato ficticio do segundo caso.",
            "esperado": {"itens": [item_esperado]},
        },
    ]

    caminho = tmp_path / "casos_ouro.jsonl"
    caminho.write_text(
        "\n".join(json.dumps(caso) for caso in casos),
        encoding="utf-8",
    )

    resultado_esperado = ResultadoExtracao.model_validate(
        {"itens": [item_esperado]}
    )
    provedor = ProvedorSempreSucesso(resultado_esperado)

    erro_simulado = RuntimeError(
        "Falha simulada durante a comparacao."
    )

    with patch(
        "agente.avaliador.comparar_resultados",
        side_effect=[erro_simulado, True],
    ):
        resultados = avaliar_golden_set(
            cast(ProvedorOpenAI, provedor),
            caminho,
        )

    assert len(resultados) == 2

    assert resultados[0].id == 1
    assert resultados[0].aprovado is False
    assert resultados[0].movimentacoes_esperadas == 1
    assert resultados[0].movimentacoes_extraidas == 1
    assert resultados[0].erro == (
        "RuntimeError: Falha simulada durante a comparacao."
    )

    assert resultados[1].id == 2
    assert resultados[1].aprovado is True
    assert resultados[1].movimentacoes_esperadas == 1
    assert resultados[1].movimentacoes_extraidas == 1
    assert resultados[1].erro is None

    assert provedor.chamadas == 2

def test_diagnostica_valor_divergente() -> None:
    from agente.avaliador import diagnosticar_divergencias

    esperado = ResultadoExtracao(itens=[criar_item(valor=150.00)])
    obtido = ResultadoExtracao(itens=[criar_item(valor=150.01)])

    divergencias = diagnosticar_divergencias(esperado, obtido)

    assert divergencias == [
        {
            "tipo": "campo_divergente",
            "campo": "valor",
            "esperado": 150.00,
            "obtido": 150.01,
        }
    ]

def test_diagnostica_movimentacao_ausente() -> None:
    from agente.avaliador import diagnosticar_divergencias

    esperado = ResultadoExtracao(
        itens=[
            criar_item(descricao="PIX RECEBIDO", valor=150.00),
            criar_item(descricao="PAGAMENTO BOLETO", valor=-80.00),
        ]
    )
    obtido = ResultadoExtracao(
        itens=[
            criar_item(descricao="PIX RECEBIDO", valor=150.00),
        ]
    )

    divergencias = diagnosticar_divergencias(esperado, obtido)

    assert divergencias == [
        {
            "tipo": "movimentacao_ausente",
            "esperado": {
                "descricao": "PAGAMENTO BOLETO",
                "valor": -80.00,
                "data": "2026-01-05",
                "fonte.documento": "extrato.pdf",
                "fonte.pagina": 1,
            },
        }
    ]

def test_diagnostica_movimentacao_extra() -> None:
    from agente.avaliador import diagnosticar_divergencias

    esperado = ResultadoExtracao(
        itens=[
            criar_item(descricao="PIX RECEBIDO", valor=150.00),
        ]
    )
    obtido = ResultadoExtracao(
        itens=[
            criar_item(descricao="PIX RECEBIDO", valor=150.00),
            criar_item(descricao="COMPRA CARTAO", valor=-45.90),
        ]
    )

    divergencias = diagnosticar_divergencias(esperado, obtido)

    assert divergencias == [
        {
            "tipo": "movimentacao_extra",
            "obtido": {
                "descricao": "COMPRA CARTAO",
                "valor": -45.90,
                "data": "2026-01-05",
                "fonte.documento": "extrato.pdf",
                "fonte.pagina": 1,
            },
        }
    ]

def test_salva_relatorio_com_divergencias(tmp_path: Path) -> None:
    caminho = tmp_path / "avaliacao.json"

    divergencias = [
        {
            "tipo": "campo_divergente",
            "campo": "valor",
            "esperado": 150.00,
            "obtido": 150.01,
        }
    ]

    resultados = [
        ResultadoCaso(
            id=1,
            aprovado=False,
            movimentacoes_esperadas=1,
            movimentacoes_extraidas=1,
            erro="Resultado diferente do esperado.",
            divergencias=divergencias,
        ),
        ResultadoCaso(
            id=2,
            aprovado=True,
            movimentacoes_esperadas=1,
            movimentacoes_extraidas=1,
        ),
    ]

    salvar_relatorio(resultados, "modelo-teste", caminho)

    dados = json.loads(caminho.read_text(encoding="utf-8"))

    assert dados["casos"][0]["divergencias"] == divergencias
    assert dados["casos"][1]["divergencias"] == []

def test_avaliacao_integrada_salva_divergencias_no_json(
    tmp_path: Path,
) -> None:
    item_esperado = {
        "descricao": "PIX RECEBIDO",
        "valor": 150.00,
        "data": "2026-01-05",
        "fonte": {
            "documento": "extrato.pdf",
            "pagina": 1,
        },
    }

    casos = [
        {
            "id": 1,
            "entrada": "Extrato ficticio para teste integrado.",
            "esperado": {"itens": [item_esperado]},
        }
    ]

    caminho_casos = tmp_path / "casos_ouro.jsonl"
    caminho_casos.write_text(
        "\n".join(json.dumps(caso) for caso in casos),
        encoding="utf-8",
    )

    resultado_obtido = ResultadoExtracao(
        itens=[criar_item(valor=150.01)]
    )
    provedor = ProvedorSempreSucesso(resultado_obtido)

    resultados = avaliar_golden_set(
        cast(ProvedorOpenAI, provedor),
        caminho_casos,
    )

    assert len(resultados) == 1
    assert resultados[0].aprovado is False
    assert resultados[0].erro == "Resultado diferente do esperado."
    assert resultados[0].divergencias == [
        {
            "tipo": "campo_divergente",
            "campo": "valor",
            "esperado": 150.00,
            "obtido": 150.01,
        }
    ]

    caminho_relatorio = tmp_path / "avaliacao.json"
    salvar_relatorio(resultados, "modelo-teste", caminho_relatorio)

    dados = json.loads(caminho_relatorio.read_text(encoding="utf-8"))

    assert dados["casos"][0]["status"] == "reprovado"
    assert dados["casos"][0]["divergencias"] == resultados[0].divergencias
    assert dados["resumo"]["reprovados"] == 1
    assert provedor.chamadas == 1

def test_diagnostica_multiplas_movimentacoes_fora_de_ordem() -> None:
    from agente.avaliador import diagnosticar_divergencias

    esperado = ResultadoExtracao(
        itens=[
            criar_item("PIX RECEBIDO", 150.00),
            criar_item("PAGAMENTO BOLETO", -80.00),
            criar_item("COMPRA CARTAO", -45.90),
        ]
    )

    obtido = ResultadoExtracao(
        itens=[
            criar_item("COMPRA CARTAO", -45.90),
            criar_item("PIX RECEBIDO", 150.01),
            criar_item("PAGAMENTO BOLETO", -80.00),
        ]
    )

    divergencias = diagnosticar_divergencias(esperado, obtido)

    assert divergencias == [
        {
            "tipo": "campo_divergente",
            "campo": "valor",
            "esperado": 150.00,
            "obtido": 150.01,
        }
    ]

def test_diagnostica_movimentacoes_duplicadas() -> None:
    from agente.avaliador import diagnosticar_divergencias

    esperado = ResultadoExtracao(
        itens=[
            criar_item("PIX RECEBIDO", 150.00),
            criar_item("PIX RECEBIDO", 150.00),
        ]
    )

    obtido = ResultadoExtracao(
        itens=[
            criar_item("PIX RECEBIDO", 150.01),
            criar_item("PIX RECEBIDO", 150.00),
        ]
    )

    divergencias = diagnosticar_divergencias(esperado, obtido)

    assert divergencias == [
        {
            "tipo": "campo_divergente",
            "campo": "valor",
            "esperado": 150.00,
            "obtido": 150.01,
        }
    ]

def test_diagnostica_descricao_normalizada_com_valor_divergente() -> None:
    from agente.avaliador import diagnosticar_divergencias

    esperado = ResultadoExtracao(
        itens=[criar_item("PIX RECEBIDO", 150.00)]
    )

    obtido = ResultadoExtracao(
        itens=[criar_item(" Pix   Recebido ", 150.01)]
    )

    divergencias = diagnosticar_divergencias(esperado, obtido)

    assert divergencias == [
        {
            "tipo": "campo_divergente",
            "campo": "valor",
            "esperado": 150.00,
            "obtido": 150.01,
        }
    ]


def test_duas_avaliacoes_consecutivas_sao_independentes(
    tmp_path: Path,
) -> None:
    item_esperado = {
        "descricao": "PIX RECEBIDO",
        "valor": 150.00,
        "data": "2026-01-05",
        "fonte": {
            "documento": "extrato.pdf",
            "pagina": 1,
        },
    }

    caso = {
        "id": 1,
        "entrada": "Extrato ficticio para teste de isolamento.",
        "esperado": {"itens": [item_esperado]},
    }

    caminho_casos = tmp_path / "casos_ouro.jsonl"
    caminho_casos.write_text(
        json.dumps(caso),
        encoding="utf-8",
    )

    resultado_obtido = ResultadoExtracao.model_validate({"itens": [item_esperado]})
    provedor = ProvedorSempreSucesso(resultado_obtido)

    primeira_execucao = avaliar_golden_set(
        cast(ProvedorOpenAI, provedor),
        caminho_casos,
    )

    segunda_execucao = avaliar_golden_set(
        cast(ProvedorOpenAI, provedor),
        caminho_casos,
    )

    assert primeira_execucao is not segunda_execucao
    assert len(primeira_execucao) == 1
    assert len(segunda_execucao) == 1
    assert primeira_execucao[0].aprovado is True
    assert segunda_execucao[0].aprovado is True

    primeira_execucao.append(
        ResultadoCaso(
            id=99,
            aprovado=False,
            movimentacoes_esperadas=1,
            movimentacoes_extraidas=0,
        )
    )

    assert len(primeira_execucao) == 2
    assert len(segunda_execucao) == 1
    assert segunda_execucao[0].id == 1
    assert provedor.chamadas == 2


def test_salva_relatorios_de_avaliacoes_independentes(
    tmp_path: Path,
) -> None:
    caminho_original = tmp_path / "avaliacao_golden_set.json"
    caminho_regressao = tmp_path / "avaliacao_regressao.json"

    resultados_original = [
        ResultadoCaso(
            id=1,
            aprovado=True,
            movimentacoes_esperadas=1,
            movimentacoes_extraidas=1,
        )
    ]

    resultados_regressao = [
        ResultadoCaso(
            id=1,
            aprovado=False,
            movimentacoes_esperadas=1,
            movimentacoes_extraidas=0,
            erro="Falha experimental simulada.",
        )
    ]

    salvar_relatorio(
        resultados_original,
        "modelo-original",
        caminho_original,
    )

    salvar_relatorio(
        resultados_regressao,
        "modelo-regressao",
        caminho_regressao,
        variante_prompt="regressao-v1",
    )

    assert caminho_original.exists()
    assert caminho_regressao.exists()

    dados_original = json.loads(caminho_original.read_text(encoding="utf-8"))
    dados_regressao = json.loads(caminho_regressao.read_text(encoding="utf-8"))

    assert dados_original["modelo"] == "modelo-original"
    assert dados_original["resumo"]["aprovados"] == 1
    assert dados_original["resumo"]["reprovados"] == 0

    assert dados_regressao["modelo"] == "modelo-regressao"
    assert dados_regressao["variante_prompt"] == "regressao-v1"
    assert dados_regressao["resumo"]["aprovados"] == 0
    assert dados_regressao["resumo"]["reprovados"] == 1
    assert dados_regressao["casos"][0]["erro"] == ("Falha experimental simulada.")
