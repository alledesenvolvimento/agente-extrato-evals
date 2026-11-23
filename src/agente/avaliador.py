"""Avaliação das extrações em relação ao Golden Set."""

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import TypedDict, cast

from agente.modelos import ItemExtrato, ResultadoExtracao
from agente.provedor_openai import ProvedorOpenAI


class CasoOuro(TypedDict):
    """Estrutura de um caso do Golden Set."""

    id: int
    entrada: str
    esperado: dict[str, object]


@dataclass
class ResultadoCaso:
    """Resultado da avaliação de um caso individual."""

    id: int
    aprovado: bool
    movimentacoes_esperadas: int
    movimentacoes_extraidas: int
    erro: str | None = None
    divergencias: list[dict[str, object]] = field(default_factory=list)


LIMITE_APROVACAO = 90.0


def verificar_quality_gate(resultados: list[ResultadoCaso]) -> bool:
    """Verifica se a taxa de aprova??o atingiu o limite de qualidade."""
    total = len(resultados)

    if total == 0:
        return False

    aprovados = sum(resultado.aprovado for resultado in resultados)
    taxa_aprovacao = aprovados / total * 100

    return taxa_aprovacao >= LIMITE_APROVACAO


def normalizar_descricao(descricao: str) -> str:
    """Padroniza espaços e diferenças entre maiúsculas e minúsculas."""
    return " ".join(descricao.casefold().split())


def chave_item(item: ItemExtrato) -> tuple[str, Decimal, str, str, int]:
    """Cria uma representação comparável de uma movimentação."""
    return (
        normalizar_descricao(item.descricao),
        Decimal(str(item.valor)).quantize(Decimal("0.01")),
        item.data.isoformat(),
        item.fonte.documento,
        item.fonte.pagina,
    )


def comparar_resultados(
    esperado: ResultadoExtracao,
    obtido: ResultadoExtracao,
) -> bool:
    """Compara duas extrações sem depender da ordem das movimentações."""
    itens_esperados = Counter(chave_item(item) for item in esperado.itens)
    itens_obtidos = Counter(chave_item(item) for item in obtido.itens)

    return itens_esperados == itens_obtidos



def diagnosticar_divergencias(
    esperado: ResultadoExtracao,
    obtido: ResultadoExtracao,
) -> list[dict[str, object]]:
    """Identifica campos divergentes e movimentacoes ausentes ou extras."""
    campos_esperados = [
        "descricao",
        "valor",
        "data",
        "fonte.documento",
        "fonte.pagina",
    ]

    def extrair_campos(item: ItemExtrato) -> dict[str, object]:
        return {
            "descricao": item.descricao,
            "valor": item.valor,
            "data": item.data.isoformat(),
            "fonte.documento": item.fonte.documento,
            "fonte.pagina": item.fonte.pagina,
        }

    def campos_equivalentes(
        campo: str,
        valor_a: object,
        valor_b: object,
    ) -> bool:
        if campo == "descricao":
            return normalizar_descricao(str(valor_a)) == normalizar_descricao(
                str(valor_b)
            )

        if campo == "valor":
            valor_a_decimal = Decimal(str(valor_a)).quantize(Decimal("0.01"))
            valor_b_decimal = Decimal(str(valor_b)).quantize(Decimal("0.01"))
            return valor_a_decimal == valor_b_decimal

        return valor_a == valor_b

    itens_esperados = list(esperado.itens)
    itens_obtidos = list(obtido.itens)

    # Remove primeiro as movimentacoes que ja sao identicas.
    restantes_obtidos: list[ItemExtrato] = []

    for item_obtido in itens_obtidos:
        chave = chave_item(item_obtido)

        indice = next(
            (
                indice
                for indice, item_esperado in enumerate(itens_esperados)
                if chave_item(item_esperado) == chave
            ),
            None,
        )

        if indice is None:
            restantes_obtidos.append(item_obtido)
        else:
            itens_esperados.pop(indice)

    divergencias: list[dict[str, object]] = []

    # Ordena os itens para que o diagnostico nao dependa da ordem original.
    itens_esperados.sort(key=chave_item)
    restantes_obtidos.sort(key=chave_item)

    # Procura os pares com maior quantidade de campos coincidentes.
    while itens_esperados and restantes_obtidos:
        melhor_par: tuple[int, int, int] | None = None

        for indice_esperado, item_esperado in enumerate(itens_esperados):
            campos_a = extrair_campos(item_esperado)

            for indice_obtido, item_obtido in enumerate(restantes_obtidos):
                campos_b = extrair_campos(item_obtido)

                coincidencias = sum(
                    campos_equivalentes(campo, campos_a[campo], campos_b[campo])
                    for campo in campos_esperados
                )

                candidato = (
                    -coincidencias,
                    indice_esperado,
                    indice_obtido,
                )

                if melhor_par is None or candidato < melhor_par:
                    melhor_par = candidato

        if melhor_par is None or melhor_par[0] == 0:
            break

        _, indice_esperado, indice_obtido = melhor_par

        campos_a = extrair_campos(itens_esperados.pop(indice_esperado))
        campos_b = extrair_campos(restantes_obtidos.pop(indice_obtido))

        for campo in campos_esperados:
            if not campos_equivalentes(campo, campos_a[campo], campos_b[campo]):
                divergencias.append(
                    {
                        "tipo": "campo_divergente",
                        "campo": campo,
                        "esperado": campos_a[campo],
                        "obtido": campos_b[campo],
                    }
                )

    for item in itens_esperados:
        divergencias.append(
            {
                "tipo": "movimentacao_ausente",
                "esperado": extrair_campos(item),
            }
        )

    for item in restantes_obtidos:
        divergencias.append(
            {
                "tipo": "movimentacao_extra",
                "obtido": extrair_campos(item),
            }
        )

    return divergencias

def carregar_casos(caminho: Path) -> list[CasoOuro]:
    """Carrega os casos do Golden Set a partir de um arquivo JSONL."""
    linhas = caminho.read_text(encoding="utf-8").splitlines()

    return [
        cast(CasoOuro, json.loads(linha))
        for linha in linhas
        if linha.strip()
    ]


def avaliar_golden_set(
    provedor: ProvedorOpenAI,
    caminho: Path,
) -> list[ResultadoCaso]:
    """Executa sequencialmente os casos e compara as extrações."""
    casos = carregar_casos(caminho)
    resultados: list[ResultadoCaso] = []

    for indice, caso in enumerate(casos, start=1):
        esperado = ResultadoExtracao.model_validate(caso["esperado"])

        print(f"Avaliando caso {indice} de {len(casos)}...")

        try:
            obtido = provedor.extrair(caso["entrada"])
        except Exception as erro:
            resultados.append(
                ResultadoCaso(
                    id=caso["id"],
                    aprovado=False,
                    movimentacoes_esperadas=len(esperado.itens),
                    movimentacoes_extraidas=0,
                    erro=f"{type(erro).__name__}: {erro}",
                )
            )
            continue

        try:
            aprovado = comparar_resultados(esperado, obtido)
            divergencias = (
                [] if aprovado else diagnosticar_divergencias(esperado, obtido)
            )
        except Exception as erro:
            resultados.append(
                ResultadoCaso(
                    id=caso["id"],
                    aprovado=False,
                    movimentacoes_esperadas=len(esperado.itens),
                    movimentacoes_extraidas=len(obtido.itens),
                    erro=f"{type(erro).__name__}: {erro}",
                )
            )
            continue

        resultados.append(
            ResultadoCaso(
                id=caso["id"],
                aprovado=aprovado,
                movimentacoes_esperadas=len(esperado.itens),
                movimentacoes_extraidas=len(obtido.itens),
                erro=None if aprovado else "Resultado diferente do esperado.",
                divergencias=divergencias,
            )
        )

    return resultados


def imprimir_relatorio(resultados: list[ResultadoCaso]) -> None:
    """Exibe o resumo da avaliação e os casos que falharam."""
    total = len(resultados)
    aprovados = sum(resultado.aprovado for resultado in resultados)
    reprovados = total - aprovados
    taxa = (aprovados / total * 100) if total else 0.0

    movimentacoes_esperadas = sum(
        resultado.movimentacoes_esperadas for resultado in resultados
    )
    movimentacoes_extraidas = sum(
        resultado.movimentacoes_extraidas for resultado in resultados
    )

    print("\n========== RELATÓRIO DE AVALIAÇÃO ==========")
    print(f"Total de casos: {total}")
    print(f"Aprovados: {aprovados}")
    print(f"Reprovados: {reprovados}")
    print(f"Taxa de aprovação: {taxa:.2f}%")
    print(f"Movimentações esperadas: {movimentacoes_esperadas}")
    print(f"Movimentações extraídas: {movimentacoes_extraidas}")

    if reprovados:
        print("\nCasos reprovados:")
        for resultado in resultados:
            if not resultado.aprovado:
                print(
                    f"- Caso {resultado.id}: {resultado.erro} "
                    f"(esperadas: {resultado.movimentacoes_esperadas}; "
                    f"extraídas: {resultado.movimentacoes_extraidas})"
                )

    print("============================================")


def salvar_relatorio(
    resultados: list[ResultadoCaso],
    modelo: str,
    caminho: Path,
    variante_prompt: str | None = None,
) -> None:
    """Salva os resultados da avaliação em um arquivo JSON."""
    total = len(resultados)
    aprovados = sum(resultado.aprovado for resultado in resultados)
    reprovados = total - aprovados

    movimentacoes_esperadas = sum(
        resultado.movimentacoes_esperadas for resultado in resultados
    )
    movimentacoes_extraidas = sum(
        resultado.movimentacoes_extraidas for resultado in resultados
    )

    dados: dict[str, object] = {
        "data_execucao": datetime.now().astimezone().isoformat(
            timespec="seconds"
        ),
        "modelo": modelo,
        "variante_prompt": variante_prompt,
        "resumo": {
            "total_casos": total,
            "aprovados": aprovados,
            "reprovados": reprovados,
            "taxa_aprovacao_percentual": (
                round(aprovados / total * 100, 2) if total else 0.0
            ),
            "movimentacoes_esperadas": movimentacoes_esperadas,
            "movimentacoes_extraidas": movimentacoes_extraidas,
        },
        "casos": [
            {
                "id": resultado.id,
                "status": "aprovado" if resultado.aprovado else "reprovado",
                "movimentacoes_esperadas": resultado.movimentacoes_esperadas,
                "movimentacoes_extraidas": resultado.movimentacoes_extraidas,
                "erro": resultado.erro,
                "divergencias": resultado.divergencias,
            }
            for resultado in resultados
        ],
    }

    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\nRelatório salvo em: {caminho}")


def main() -> int:
    """Executa a avaliacao e aplica o Quality Gate."""
    raiz = Path(__file__).resolve().parents[2]
    caminho_casos = raiz / "evals" / "casos_ouro.jsonl"
    caminho_relatorio = raiz / "resultados" / "avaliacao_golden_set.json"

    provedor = ProvedorOpenAI()
    resultados = avaliar_golden_set(provedor, caminho_casos)

    imprimir_relatorio(resultados)
    salvar_relatorio(resultados, provedor.modelo, caminho_relatorio)

    if verificar_quality_gate(resultados):
        print(f"QUALITY GATE APROVADO (minimo: {LIMITE_APROVACAO:.2f}%).")
        return 0

    print(f"QUALITY GATE REPROVADO (minimo: {LIMITE_APROVACAO:.2f}%).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
