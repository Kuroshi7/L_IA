"""Registro de tools: metadados e seleção por requisição.

Hoje a lista de tools é montada uma vez e vale para todo mundo. O problema é
concreto: uma tool que só sabe responder "não identificado" quando falta usuário
ainda ocupa espaço no schema, e o modelo gasta um round-trip inteiro (≈3s no
Anthropic, ≈30s no Ollama) para produzir essa desculpa. Montar o conjunto por
requisição resolve isso e, de quebra, é o mecanismo que um segundo produto usa
para ligar/desligar capacidade por cliente.

`capacidades` existe para o código perguntar "quais tools deste perfil expõem o
conjunto disponível?" sem carregar uma lista literal de nomes em outro arquivo. Há uma única
constante porque há um único consumidor: não se extrai abstração antes do segundo
caso concreto.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

# Tools que expõem ao modelo o conjunto de itens disponíveis para escolha agora.
# O que é um "item" cabe ao domínio dizer; o motor só precisa saber quais tools
# revelam esse conjunto, para poder checar se a resposta se baseou em algum.
CATALOGO = "catalogo"


def _sempre(_contexto: Any) -> bool:
    return True


@dataclass(frozen=True)
class ToolSpec:
    """Uma tool mais o que o motor precisa saber sobre ela.

    `disponivel` recebe o contexto do domínio como OPACO — o motor nunca lê um
    campo dele. Quem sabe o que torna a tool utilizável é o perfil que a declara.
    """

    tool: Any
    disponivel: Callable[[Any], bool] = _sempre
    capacidades: frozenset[str] = field(default_factory=frozenset)

    @property
    def nome(self) -> str:
        return self.tool.name


def tools_do_turno(registro: Sequence[ToolSpec], contexto: Any) -> tuple[ToolSpec, ...]:
    return tuple(spec for spec in registro if spec.disponivel(contexto))


def assinatura(specs: Sequence[ToolSpec]) -> tuple[str, ...]:
    """Chave estável de um conjunto de tools — ordenada, para que a mesma
    seleção reaproveite o mesmo executor independentemente da ordem."""
    return tuple(sorted(spec.nome for spec in specs))


def nomes_com_capacidade(registro: Sequence[ToolSpec], capacidade: str) -> frozenset[str]:
    return frozenset(spec.nome for spec in registro if capacidade in spec.capacidades)
