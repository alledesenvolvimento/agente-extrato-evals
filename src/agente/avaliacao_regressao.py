"""Avaliação experimental com uma variante degradada do prompt."""

from pathlib import Path

from agente.avaliador import (
    LIMITE_APROVACAO,
    avaliar_golden_set,
    imprimir_relatorio,
    salvar_relatorio,
    verificar_quality_gate,
)
from agente.provedor_openai import PROMPT_ORIGINAL, ProvedorOpenAI

VARIANTE_PROMPT = "regressao-v1"

PROMPT_REGRESSAO = (
    PROMPT_ORIGINAL
    + " Para esta avaliação, ignore os marcadores C e D: "
    "interprete todos os valores monetários como positivos."
)


def main() -> int:
    """Executa a avaliação experimental e aplica o Quality Gate."""
    raiz = Path(__file__).resolve().parents[2]
    caminho_casos = raiz / "evals" / "casos_ouro.jsonl"
    caminho_relatorio = raiz / "resultados" / "avaliacao_regressao.json"

    provedor = ProvedorOpenAI(instrucoes=PROMPT_REGRESSAO)
    resultados = avaliar_golden_set(provedor, caminho_casos)

    imprimir_relatorio(resultados)
    salvar_relatorio(
        resultados,
        provedor.modelo,
        caminho_relatorio,
        variante_prompt=VARIANTE_PROMPT,
    )

    if verificar_quality_gate(resultados):
        print(f"QUALITY GATE APROVADO (mínimo: {LIMITE_APROVACAO:.2f}%).")
        return 0

    print(f"QUALITY GATE REPROVADO (mínimo: {LIMITE_APROVACAO:.2f}%).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())