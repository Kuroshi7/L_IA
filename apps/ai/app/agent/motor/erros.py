"""Classificação de falha do modelo — para o motor saber se insistir ajuda.

Sem isto, todo erro vira a mesma frase: *"tive um problema, tente de novo em
instantes"*. Para rate limit isso é verdade. Para chave errada, modelo
inexistente ou crédito acabado, é mentira — o usuário repete para sempre e o
sistema nunca melhora sozinho. Foi o que aconteceu no teste de 24/08/2026: seis
mensagens pedindo para tentar de novo enquanto o worker falava com um endpoint
que não existia.

Classificamos por **status HTTP e nome da exceção**, de propósito. Importar o
SDK de cada provedor para usar `isinstance` acoplaria o motor à lista de
provedores suportados — exatamente o que `provedores.py` existe para evitar. O
protocolo HTTP é o que todos têm em comum.

O motor decide `retentavel`; **a frase é do domínio** (`PerfilDeDominio`). O
`codigo` não vai para o usuário: serve para log e métrica distinguirem "modelo
respondeu mal" de "modelo não respondeu" — modos de falha que a calibração do
juiz mostrou serem diferentes e que o contador de indisponibilidade não separa.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class ClasseDeErro(str, Enum):
    AUTENTICACAO = "AUTENTICACAO"   # chave inválida ou sem permissão
    CONFIGURACAO = "CONFIGURACAO"   # modelo inexistente, parâmetro inválido, URL errada
    COTA = "COTA"                   # crédito acabou ou teto do período estourou
    LIMITE = "LIMITE"               # rate limit de curto prazo — passa sozinho
    CONTEXTO = "CONTEXTO"           # entrada maior que a janela do modelo
    INDISPONIVEL = "INDISPONIVEL"   # timeout, queda de rede, 5xx do provedor
    LOOP = "LOOP"                   # agente estourou o limite de passos
    INTERNO = "INTERNO"             # não reconhecido


@dataclass(frozen=True)
class ErroClassificado:
    classe: ClasseDeErro
    retentavel: bool
    codigo: str
    detalhe: str

    @property
    def permanente(self) -> bool:
        return not self.retentavel


# Um 429 pode ser de dois tipos, e a diferença importa para o usuário:
# "muitas requisições agora" passa em segundos; "acabou sua cota do dia/mês"
# não passa hoje. O OpenRouter devolve os dois com o mesmo status — o que separa
# é o texto. Ver docs/custos-provedores.md.
_COTA_NO_TEXTO = re.compile(
    r"per[- ]day|per[- ]month|daily|monthly|quota|credit|budget|"
    r"depleted|insufficient|exceeded your|billing",
    re.I,
)
_CONTEXTO_NO_TEXTO = re.compile(
    r"context[ _-]?(window|length)|too many tokens|maximum context|"
    r"reduce the length|input is too long",
    re.I,
)


def _status(exc: BaseException) -> int | None:
    """Status HTTP da exceção, venha ele de onde vier.

    SDKs diferentes guardam em lugares diferentes: o cliente da OpenAI expõe
    `status_code`; wrappers de httpx guardam em `response.status_code`.
    """
    for obj, attr in ((exc, "status_code"), (exc, "http_status"),
                      (getattr(exc, "response", None), "status_code")):
        valor = getattr(obj, attr, None)
        if isinstance(valor, int):
            return valor
    return None


def _cadeia(exc: BaseException) -> list[BaseException]:
    """A exceção e suas causas. Clientes embrulham o erro real várias vezes."""
    vistos: list[BaseException] = []
    atual: BaseException | None = exc
    while atual is not None and len(vistos) < 10 and atual not in vistos:
        vistos.append(atual)
        atual = atual.__cause__ or atual.__context__
    return vistos


def classificar(exc: BaseException) -> ErroClassificado:
    """Classe da falha, se insistir adianta, e um código para log.

    A ordem importa: casos específicos antes dos genéricos, senão um 400 de
    contexto estourado vira "requisição inválida" e a métrica mente.
    """
    cadeia = _cadeia(exc)
    texto = " | ".join(str(e) for e in cadeia)[:2000]
    nomes = " ".join(type(e).__name__ for e in cadeia)
    status = next((s for s in (_status(e) for e in cadeia) if s is not None), None)
    detalhe = str(exc)[:300]

    def _r(classe: ClasseDeErro, retentavel: bool) -> ErroClassificado:
        codigo = f"{classe.value}:{status}" if status else f"{classe.value}:{type(exc).__name__}"
        return ErroClassificado(classe=classe, retentavel=retentavel,
                                codigo=codigo, detalhe=detalhe)

    # Loop de tools: nosso, não do provedor. Insistir repete o mesmo loop.
    if "GraphRecursion" in nomes or "RecursionError" in nomes:
        return _r(ClasseDeErro.LOOP, False)

    # Contexto estourado chega como 400 em quase todo provedor — precisa vir
    # antes da regra genérica de 400.
    if "ContextWindow" in nomes or _CONTEXTO_NO_TEXTO.search(texto):
        return _r(ClasseDeErro.CONTEXTO, False)

    if status in (401, 403) or "Authentication" in nomes or "PermissionDenied" in nomes:
        return _r(ClasseDeErro.AUTENTICACAO, False)

    if status == 402 or "BudgetExceeded" in nomes:
        return _r(ClasseDeErro.COTA, False)

    if status == 429 or "RateLimit" in nomes:
        # "1000 requisições por dia" e "20 por minuto" chegam com o mesmo 429.
        # Só o primeiro é permanente dentro do horizonte do usuário.
        return _r(ClasseDeErro.COTA, False) if _COTA_NO_TEXTO.search(texto) \
            else _r(ClasseDeErro.LIMITE, True)

    if status in (400, 404, 422) or "NotFound" in nomes or "BadRequest" in nomes \
            or "UnprocessableEntity" in nomes:
        return _r(ClasseDeErro.CONFIGURACAO, False)

    # "Connect" e não "Connection": o httpx levanta `ConnectError` e
    # `ConnectTimeout`, que não contêm "Connection". O teste com o
    # `ConnectionError` embutido do Python passava e o caso real não —
    # encontrado rodando o preflight contra um host inexistente.
    if (status is not None and status >= 500) or "Timeout" in nomes \
            or "Connect" in nomes or "ServiceUnavailable" in nomes \
            or "APIError" in nomes:
        return _r(ClasseDeErro.INDISPONIVEL, True)

    # Desconhecido: tratamos como retentável para não bloquear o usuário por um
    # erro que talvez seja transitório, mas o código sai como INTERNO para a
    # métrica mostrar que existe algo não mapeado.
    return _r(ClasseDeErro.INTERNO, True)
