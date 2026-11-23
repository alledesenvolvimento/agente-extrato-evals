"""Integração com a API da OpenAI para extração de extratos."""

from dotenv import load_dotenv
from openai import OpenAI

from agente.modelos import ResultadoExtracao

PROMPT_ORIGINAL = (
    "Extraia as movimentações bancárias do texto fornecido. "
    "Não invente informações. Preserve a descrição, a data "
    "e o valor. Valores positivos representam créditos e "
    "valores negativos representam débitos. Informe o "
    "documento e a página de origem de cada movimentação."
)


class ProvedorOpenAI:
    """Responsável por solicitar extrações estruturadas à OpenAI."""

    def __init__(
        self,
        modelo: str = "gpt-6.2-sol",
        cliente: OpenAI | None = None,
        instrucoes: str = PROMPT_ORIGINAL,
    ) -> None:
        load_dotenv()
        self.modelo = modelo
        self.instrucoes = instrucoes
        self.cliente = cliente or OpenAI()

    def extrair(self, texto: str) -> ResultadoExtracao:
        """Extrai movimentações do texto de um extrato bancário."""

        resposta = self.cliente.responses.parse(
            model=self.modelo,
            input=[
                {
                    "role": "system",
                    "content": self.instrucoes,
                },
                {
                    "role": "user",
                    "content": texto,
                },
            ],
            text_format=ResultadoExtracao,
        )

        resultado = resposta.output_parsed

        if resultado is None:
            raise ValueError("A OpenAI não retornou uma extração estruturada.")

        return resultado
