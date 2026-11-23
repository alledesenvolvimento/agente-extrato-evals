"""Camada modular de observabilidade com suporte opcional ao Langfuse."""

import logging
import os
from typing import Any, Protocol
from uuid import uuid4

from dotenv import load_dotenv
from langfuse import Langfuse

from agente.provedores import MetadadosExtracao

logger = logging.getLogger(__name__)


class ObservadorExecucao(Protocol):
    """Contrato para registro operacional de execuções de extração."""

    execucao_id: str

    def registrar_caso(
        self,
        *,
        caso_id: int,
        entrada: str,
        aprovado: bool,
        movimentacoes_esperadas: int,
        movimentacoes_extraidas: int,
        latencia_ms: float,
        erro: str | None = None,
        metadados: MetadadosExtracao | None = None,
    ) -> None:
        """Registra o resultado e metadados operacionais de um caso."""
        ...

    def finalizar(self, resumo: dict[str, object]) -> None:
        """Registra o resumo final da execução e descarrega buffers."""
        ...


class ObservadorNulo:
    """Implementação no-op usada quando o Langfuse não está configurado."""

    def __init__(self, execucao_id: str | None = None) -> None:
        self.execucao_id = execucao_id or str(uuid4())

    def registrar_caso(
        self,
        *,
        caso_id: int,
        entrada: str,
        aprovado: bool,
        movimentacoes_esperadas: int,
        movimentacoes_extraidas: int,
        latencia_ms: float,
        erro: str | None = None,
        metadados: MetadadosExtracao | None = None,
    ) -> None:
        """Não executa nenhuma ação."""

    def finalizar(self, resumo: dict[str, object]) -> None:
        """Não executa nenhuma ação."""


class ObservadorLangfuse:
    """Registra execuções e gerações no Langfuse SDK v5+ sem acoplar o avaliador."""

    def __init__(
        self,
        *,
        cliente: Any | None = None,
        execucao_id: str | None = None,
    ) -> None:
        load_dotenv()
        self.execucao_id = execucao_id or str(uuid4())
        self._cliente: Any | None = cliente

        if self._cliente is None and langfuse_configurado():
            self._cliente = Langfuse()

    @property
    def ativo(self) -> bool:
        """Indica se há um cliente Langfuse pronto para envio de eventos."""
        return self._cliente is not None

    def registrar_caso(
        self,
        *,
        caso_id: int,
        entrada: str,
        aprovado: bool,
        movimentacoes_esperadas: int,
        movimentacoes_extraidas: int,
        latencia_ms: float,
        erro: str | None = None,
        metadados: MetadadosExtracao | None = None,
    ) -> None:
        """Registra uma geração no Langfuse diferenciando custo real e estimado."""
        if self._cliente is None:
            return

        usage_details = _montar_usage_details(metadados)
        cost_details, origem_custo = _montar_cost_details(metadados)

        metadata_evento: dict[str, object] = {
            "execucao_id": self.execucao_id,
            "caso_id": caso_id,
            "provedor": metadados.provedor if metadados else "desconhecido",
            "latencia_ms": (
                metadados.latencia_ms if metadados else round(latencia_ms, 2)
            ),
            "origem_custo": origem_custo,
        }
        if metadados and metadados.custo_real_usd is not None:
            metadata_evento["custo_real_usd"] = metadados.custo_real_usd
        if metadados and metadados.custo_estimado_usd is not None:
            metadata_evento["custo_estimado_usd"] = metadados.custo_estimado_usd
        if erro is not None:
            metadata_evento["erro"] = erro

        kwargs: dict[str, Any] = {
            "as_type": "generation",
            "name": f"extracao-caso-{caso_id}",
            "input": {
                "caso_id": caso_id,
                "tamanho_entrada_chars": len(entrada),
            },
            "output": {
                "aprovado": aprovado,
                "movimentacoes_esperadas": movimentacoes_esperadas,
                "movimentacoes_extraidas": movimentacoes_extraidas,
            },
            "metadata": metadata_evento,
            "level": "ERROR" if erro else "DEFAULT",
        }

        if erro is not None:
            kwargs["status_message"] = erro
        if metadados is not None:
            kwargs["model"] = metadados.modelo
            kwargs["version"] = metadados.versao_prompt
        if usage_details is not None:
            kwargs["usage_details"] = usage_details
        if cost_details is not None:
            kwargs["cost_details"] = cost_details

        try:
            with self._cliente.start_as_current_observation(**kwargs):
                pass
        except Exception as exc:
            logger.warning(
                "Falha ao enviar evento de observabilidade ao Langfuse: %s",
                type(exc).__name__,
            )

    def finalizar(self, resumo: dict[str, object]) -> None:
        """Registra o resumo da execução e força o flush do cliente Langfuse."""
        if self._cliente is None:
            return

        try:
            with self._cliente.start_as_current_observation(
                as_type="span",
                name="avaliacao-golden-set",
                metadata={"execucao_id": self.execucao_id, **resumo},
                output=resumo,
            ):
                pass
            self._cliente.flush()
        except Exception as exc:
            logger.warning(
                "Falha ao finalizar observabilidade no Langfuse: %s",
                type(exc).__name__,
            )


def langfuse_configurado() -> bool:
    """Verifica se as credenciais mínimas do Langfuse estão presentes no ambiente."""
    return bool(
        os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
    )


def criar_observador(execucao_id: str | None = None) -> ObservadorExecucao:
    """Cria ObservadorLangfuse quando configurado, ou ObservadorNulo caso contrário."""
    load_dotenv()
    if langfuse_configurado():
        return ObservadorLangfuse(execucao_id=execucao_id)
    return ObservadorNulo(execucao_id=execucao_id)


def _montar_usage_details(
    metadados: MetadadosExtracao | None,
) -> dict[str, int] | None:
    if metadados is None:
        return None
    detalhes: dict[str, int] = {}
    if metadados.tokens_entrada is not None:
        detalhes["input"] = metadados.tokens_entrada
    if metadados.tokens_saida is not None:
        detalhes["output"] = metadados.tokens_saida
    return detalhes or None


def _montar_cost_details(
    metadados: MetadadosExtracao | None,
) -> tuple[dict[str, float] | None, str]:
    if metadados is None:
        return None, "indisponivel"
    if metadados.custo_real_usd is not None:
        return {"total": metadados.custo_real_usd}, "real"
    if metadados.custo_estimado_usd is not None:
        return {"total": metadados.custo_estimado_usd}, "estimado"
    return None, "indisponivel"
