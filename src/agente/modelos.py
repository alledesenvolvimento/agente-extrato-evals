"""Modelos tipados da extração de extrato (saída rastreável até a página de origem)."""

from datetime import date

from pydantic import BaseModel, Field


class Fonte(BaseModel):
    documento: str
    pagina: int = Field(ge=1)


class ItemExtrato(BaseModel):
    descricao: str
    valor: float  # positivo = crédito (C), negativo = débito (D)
    data: date
    fonte: Fonte


class ResultadoExtracao(BaseModel):
    itens: list[ItemExtrato]
