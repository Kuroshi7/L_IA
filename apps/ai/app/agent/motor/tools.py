"""O que o motor faz com as tools do domínio antes de entregá-las ao modelo.

**Tool que estoura não pode derrubar o turno.** Medido em 24/08/2026: uma tool
que levanta exceção aborta o grafo inteiro, o usuário recebe a mensagem genérica
de erro e o modelo nunca soube que a busca falhou. Ele tinha alternativa —
dizer "não consegui obter esse dado agora, mas posso ajudar de outro jeito"
— e não teve chance de usá-la.

A correção é devolver a falha *para dentro* da conversa, como observação que o
modelo lê e à qual pode reagir. Dois níveis:

- `ErroDeTool`: o domínio sabe o que aconteceu e escreve a frase que o modelo
  deve ler. É o caso bom — a falha vira informação útil.
- Qualquer outra exceção: o domínio não previu. O modelo recebe um aviso
  genérico e o erro real vai para o log.

**Deliberadamente diferente do Onyx:** eles interpolam `str(e)` na mensagem que
o modelo lê. Não fazemos isso. Exceção de banco carrega host, usuário e às vezes
a query; o modelo é instruído a explicar o que houve ao usuário, e detalhe de
infraestrutura não pode chegar à tela de ninguém. O erro real fica no log,
onde o operador vê e o usuário não.

Agnóstico de produto: o motor não sabe o que as tools fazem, só que podem falhar.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Sequence

log = logging.getLogger(__name__)

# Exceções que atravessam a blindagem intactas: são controle de fluxo do motor,
# não falha de tool.
from app.agent.motor.observacao import PrazoEsgotado

_CONTROLE: tuple[type[BaseException], ...] = (PrazoEsgotado, KeyboardInterrupt, SystemExit)

# Sem detalhe técnico de propósito — ver o cabeçalho. O modelo tem contexto
# suficiente para explicar a situação ao usuário sem saber por que falhou.
AVISO_GENERICO = (
    "A consulta falhou por um problema técnico. Não invente o dado: "
    "diga que não conseguiu obter essa informação agora e ofereça outro caminho."
)


class ErroDeTool(Exception):
    """Falha que o domínio previu e sabe explicar ao modelo.

    A mensagem é escrita para o MODELO ler, não para o usuário — ela entra no
    contexto como resultado da tool. Deve dizer o que falhou e o que fazer, sem
    detalhe de infraestrutura.
    """

    def __init__(self, mensagem_para_o_modelo: str, *, causa: BaseException | None = None):
        super().__init__(mensagem_para_o_modelo)
        self.mensagem_para_o_modelo = mensagem_para_o_modelo
        self.causa = causa


def blindar(ferramenta):
    """Devolve a tool com a falha convertida em texto que o modelo lê.

    Preserva o objeto original e troca só a função executada, para não depender
    de como o framework de tools está implementado por baixo.
    """
    for atributo in ("func", "coroutine", "_run"):
        original = getattr(ferramenta, atributo, None)
        if original is None or not callable(original):
            continue

        @functools.wraps(original)
        def _protegida(*args, __original=original, __nome=getattr(ferramenta, "name", "?"), **kwargs):
            try:
                return __original(*args, **kwargs)
            except _CONTROLE:
                # Sinal do motor (ex.: prazo do turno esgotado), não falha da
                # tool. Engolir isto transformaria "pare agora" em "responda
                # que deu erro" — e o turno seguiria consumindo tempo que já
                # acabou. Ver motor/observacao.py.
                raise
            except ErroDeTool as e:
                log.warning("TOOL FALHOU (prevista) | tool=%s | %s", __nome, e.mensagem_para_o_modelo)
                return e.mensagem_para_o_modelo
            except Exception as e:
                # O erro real fica aqui; o modelo recebe só o aviso genérico.
                log.exception("TOOL FALHOU (não prevista) | tool=%s | %s", __nome, type(e).__name__)
                return AVISO_GENERICO

        try:
            setattr(ferramenta, atributo, _protegida)
        except Exception:  # objeto imutável — nada a fazer, segue sem blindagem
            log.warning("não foi possível blindar a tool %s", getattr(ferramenta, "name", "?"))
        return ferramenta
    return ferramenta


def blindar_todas(ferramentas: Sequence):
    return [blindar(f) for f in ferramentas]
