"""Contexto por requisição compartilhado com as tools do agente.

A unidade é escolhida explicitamente pelo usuário (seletor no front) e trafega
até aqui — não há inferência de unidade. As tools leem `current_context()` para
saber de qual unidade (e usuário) buscar os dados na API Go.

Cada mensagem é processada em uma thread/processo dedicado, então o ContextVar
fica isolado por requisição.
"""

import contextvars
from dataclasses import dataclass


@dataclass
class RequestContext:
    unidade_id: int
    usuario_id: int | None = None

    # Origem confiável: carimbado pela API Go a partir do X-Admin-Token
    # validado, nunca por campo que o cliente escreve. Libera tools que leem
    # dado agregado da unidade — quem se declara admin sozinho escala privilégio.
    is_admin: bool = False


_ctx: contextvars.ContextVar[RequestContext | None] = contextvars.ContextVar(
    "request_context", default=None
)


def set_context(ctx: RequestContext) -> contextvars.Token:
    return _ctx.set(ctx)


def reset_context(token: contextvars.Token) -> None:
    _ctx.reset(token)


def current_context() -> RequestContext:
    ctx = _ctx.get()
    if ctx is None:
        raise RuntimeError("RequestContext não definido — defina set_context() antes de invocar o agente.")
    return ctx
