"""Validação controlada do Quality Gate para execução em CI sem chamadas externas."""

import tempfile
from pathlib import Path

from agente.avaliador import (
    LIMITE_APROVACAO,
    avaliar_golden_set,
    carregar_casos,
    imprimir_relatorio,
    salvar_relatorio,
    verificar_quality_gate,
)
from agente.modelos import ResultadoExtracao


class ProvedorControladoCI:
    """Provedor determinístico baseado nos casos do Golden Set para validação de CI."""

    modelo = "simulado-ci"

    def __init__(self, caminho_casos: Path) -> None:
        casos = carregar_casos(caminho_casos)
        self._respostas: dict[str, ResultadoExtracao] = {
            caso["entrada"]: ResultadoExtracao.model_validate(caso["esperado"])
            for caso in casos
        }

    def extrair(self, texto: str) -> ResultadoExtracao:
        """Retorna a extração esperada para o caso informado."""
        if texto not in self._respostas:
            raise KeyError("Caso não encontrado no conjunto controlado de CI.")
        return self._respostas[texto]


def main() -> int:
    """Executa o fluxo completo de avaliação e Quality Gate em diretório temporário."""
    raiz = Path(__file__).resolve().parents[2]
    caminho_casos = raiz / "evals" / "casos_ouro.jsonl"

    provedor = ProvedorControladoCI(caminho_casos)
    resultados = avaliar_golden_set(provedor, caminho_casos)

    imprimir_relatorio(resultados)

    with tempfile.TemporaryDirectory() as tmp_dir:
        caminho_relatorio = Path(tmp_dir) / "avaliacao_ci.json"
        salvar_relatorio(
            resultados,
            provedor.modelo,
            caminho_relatorio,
            variante_prompt="ci-controlado",
        )

    if verificar_quality_gate(resultados):
        print(f"QUALITY GATE APROVADO (mínimo: {LIMITE_APROVACAO:.2f}%).")
        return 0

    print(f"QUALITY GATE REPROVADO (mínimo: {LIMITE_APROVACAO:.2f}%).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
