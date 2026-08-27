"""O prazo do turno vale também para as chamadas de modelo.

Regressão de um buraco real: o deadline só era checado dentro do decorator das
tools, então um turno que não chamasse tool nenhuma nunca era verificado — e,
mesmo chamando, o turno ainda gastava uma inferência inteira depois do tempo
acabar, prendendo o worker para o próximo da fila.
"""

import time

import pytest

from app.agent.motor.observacao import PrazoEsgotado, encerrar_turno, iniciar_turno
from app.agent.motor.prazo import PrazoDoTurno


def _chamar(prazo):
    """Roda o middleware como o agente rodaria, com um handler que só marca que
    chegou até o modelo."""
    chamou = []
    token = iniciar_turno(prazo=prazo)
    try:
        PrazoDoTurno().wrap_model_call(object(), lambda _req: chamou.append(1))
    finally:
        encerrar_turno(token)
    return chamou


def test_dentro_do_prazo_a_chamada_acontece():
    assert _chamar(prazo=time.monotonic() + 30) == [1]


def test_prazo_estourado_barra_a_chamada_de_modelo():
    with pytest.raises(PrazoEsgotado):
        _chamar(prazo=time.monotonic() - 0.01)


def test_turno_sem_prazo_nao_e_afetado():
    """Eval e testes rodam sem deadline; o middleware não pode inventar um."""
    assert _chamar(prazo=None) == [1]


def test_fora_de_turno_nao_quebra():
    """Sem estado de turno (uso direto do agente), o middleware é transparente."""
    chamou = []
    PrazoDoTurno().wrap_model_call(object(), lambda _req: chamou.append(1))
    assert chamou == [1]
