"""Aplica as regras de validação do domínio sobre a resposta gerada.

O motor não sabe o que é uma resposta boa — ele só sabe rodar as regras que o
perfil declarou, registrar as violações num formato alarmável e dizer se alguma
delas deve barrar a resposta.

Cada regra é `(id, funcao)`. O `id` existe porque a linha de log
`VALIDACAO | regra=<id>` precisa dele para virar métrica; não por simetria.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

log = logging.getLogger("validators")


@dataclass(frozen=True)
class Achado:
    resposta: str
    tools_chamadas: tuple[str, ...]
    observacoes: object | None = None


@dataclass(frozen=True)
class Veredicto:
    ok: bool
    violacoes: tuple[tuple[str, str], ...] = ()   # (id da regra, detalhe)
    bloqueia: bool = False

    def __bool__(self) -> bool:
        # Mantém `assert verificar_resposta(...)` funcionando como antes de o
        # retorno virar objeto.
        return self.ok

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(rid for rid, _ in self.violacoes)


def verificar(
    regras: Sequence[tuple[str, Callable[[Achado], str | None]]],
    resposta: str,
    tools_chamadas: Sequence[str] = (),
    observacoes=None,
    session_id: str = "",
    bloqueantes: frozenset[str] = frozenset(),
) -> Veredicto:
    achado = Achado(resposta, tuple(tools_chamadas), observacoes)

    violacoes = []
    for rid, regra in regras:
        try:
            detalhe = regra(achado)
        except Exception as e:
            # Uma regra com bug não pode derrubar a resposta do usuário.
            log.warning("VALIDACAO | regra=%s | ERRO na própria regra | %s: %s", rid, type(e).__name__, e)
            continue
        if detalhe:
            violacoes.append((rid, detalhe))
            log.warning(
                "VALIDACAO | regra=%s | session=%s | detalhe=%s | tools=%s",
                rid, session_id[:12], detalhe, list(tools_chamadas),
            )

    return Veredicto(
        ok=not violacoes,
        violacoes=tuple(violacoes),
        bloqueia=any(rid in bloqueantes for rid, _ in violacoes),
    )
