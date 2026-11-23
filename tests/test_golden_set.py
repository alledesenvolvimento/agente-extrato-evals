"""Garante que o golden set é válido: cada caso tem a saída esperada no formato tipado."""

import json
from pathlib import Path

from agente.modelos import ResultadoExtracao

CAMINHO = Path(__file__).resolve().parent.parent / "evals" / "casos_ouro.jsonl"


def carregar_casos() -> list[dict[str, object]]:
    linhas = CAMINHO.read_text(encoding="utf-8").splitlines()
    return [json.loads(linha) for linha in linhas if linha.strip()]


def test_golden_set_tem_20_casos() -> None:
    assert len(carregar_casos()) == 20


def test_ids_unicos() -> None:
    ids = [caso["id"] for caso in carregar_casos()]
    assert len(ids) == len(set(ids))


def test_esperado_valida_no_modelo_tipado() -> None:
    for caso in carregar_casos():
        ResultadoExtracao.model_validate(caso["esperado"])


def test_cada_caso_tem_entrada_nao_vazia() -> None:
    for caso in carregar_casos():
        assert isinstance(caso["entrada"], str)
        assert caso["entrada"].strip()
