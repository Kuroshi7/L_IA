"""Compatibilidade da pós-validação.

As regras vivem em `regras.py` e a execução, em `motor/validacao.py`. Este
módulo mantém a superfície antiga (`resposta_recomenda`, `verificar_resposta`)
para os chamadores e testes que já existiam — o retorno virou objeto, mas com
`__bool__`, então `assert verificar_resposta(...)` continua valendo.
"""

from app import config
from app.agent.dominio.refeitorio.regras import construir, resposta_recomenda  # noqa: F401
from app.agent.motor.validacao import Veredicto, verificar

# Conjunto histórico, mantido porque era importado como constante pública.
from app.agent.motor.registry import CATALOGO, nomes_com_capacidade


def _regras():
    from app.agent.dominio.refeitorio.perfil import PERFIL
    return PERFIL.regras


def verificar_resposta(
    resposta: str,
    tools_chamadas: list[str],
    session_id: str = "",
    observacoes=None,
) -> Veredicto:
    """Valida a resposta contra o que as tools realmente devolveram no turno.

    `observacoes` é opcional para os chamadores antigos seguirem válidos; sem
    ela, só as regras que dependem apenas das tools chamadas têm efeito.
    """
    return verificar(
        _regras(),
        resposta,
        tools_chamadas=tools_chamadas,
        observacoes=observacoes,
        session_id=session_id,
        bloqueantes=config.VALIDACAO_BLOQUEANTE,
    )


def TOOLS_DE_CARDAPIO() -> frozenset[str]:
    """Mantido como função para não importar o perfil no import do módulo."""
    from app.agent.dominio.refeitorio.perfil import REGISTRO
    return nomes_com_capacidade(REGISTRO, CATALOGO)
