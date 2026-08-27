"""O prazo do turno, imposto também nas chamadas de modelo.

O deadline absoluto de quem espera já era propagado (o worker o calcula a partir
do timestamp da publicação) e já era checado — mas só dentro do decorator das
tools. Isso deixava dois buracos:

  1. Um turno que NÃO chama tool nenhuma nunca era verificado. Acontece sempre
     que o modelo decide responder direto, e é justamente quando ele demora mais.
  2. A verificação acontecia antes de uma tool, nunca antes de uma chamada de
     modelo — que é a etapa cara. Estourado o prazo, o turno ainda gastava uma
     inferência inteira produzindo texto que ninguém iria ler, e mantinha o
     worker ocupado (prefetch=1) para o próximo da fila.

O `config.py` já registrava a dívida: "o fix completo — propagar o deadline
absoluto do Go por requisição e abortar quando esgotar — está no follow-up".
A propagação existia; o abortar é o que falta, e é isto aqui.

Fica no motor porque não depende de assunto: qualquer produto conversacional tem
alguém do outro lado esperando.
"""

import logging
import time

from langchain.agents.middleware import AgentMiddleware

from app.agent.motor.observacao import PrazoEsgotado, estado_do_turno

log = logging.getLogger("agent")


class PrazoDoTurno(AgentMiddleware):
    """Recusa começar uma chamada de modelo que o prazo do turno não paga mais.

    Não interrompe uma chamada em andamento: cortar no meio exigiria cancelamento
    cooperativo do cliente HTTP de cada provider, e o ganho não justifica. O que
    esta barreira garante é que o turno não ENCADEIA mais inferências depois que
    o tempo acabou — que é de onde vinha o pior caso, já que um turno faz de 2 a 3
    chamadas em sequência e cada uma custa o mesmo que a primeira.
    """

    name = "prazo_do_turno"

    def wrap_model_call(self, request, handler):
        estado = estado_do_turno()
        if estado is not None and estado.prazo is not None:
            restante = estado.prazo - time.monotonic()
            if restante <= 0:
                log.warning("PRAZO esgotado antes de uma chamada de modelo — abortando o turno")
                raise PrazoEsgotado("modelo")
        return handler(request)
