"""O único estado do motor que sobrevive ao fim de um turno.

Guarda, por conversa, quais consultas já voltaram SEM RESULTADO — e só isso.
Não o corpo do retorno.

Por que existe: o histórico que volta do serviço é só texto de pessoa e de
assistente. Nada do que as tools descobriram atravessa o turno, e o modelo
recomeça cada turno sem memória do que já tentou. Medido em 27/08/2026: o
usuário esclareceu o critério, o modelo refez EXATAMENTE a mesma consulta que
tinha falhado cinco vezes trinta segundos antes, e falhou de novo — para ele era
a primeira vez.

Por que só a chave, e não o retorno: persistir o retorno das tools incharia o
contexto e o custo de todo turno seguinte, para carregar sobretudo informação
que o modelo não vai usar. A chave (nome da tool + argumentos canônicos) é uma
tupla de duas strings e responde à única pergunta que importa entre turnos:
"esse caminho já morreu?".

Por que no processo, e não no banco: durar de verdade exigiria campo novo no
envelope entre os serviços e na persistência do lado Go — mudança fora desta
rodada. O custo de ficar no processo está registrado em `workers/chat_worker.py`
e degrada para o comportamento de hoje, nunca para resposta errada.
"""

import threading
import time
from collections import OrderedDict

# Chave de uma consulta: (nome da tool, argumentos canônicos).
Chave = tuple[str, str]

# Depois disso o registro deixa de valer. O conjunto consultável muda com o
# tempo — o que não existia às 11h pode existir às 15h —, então "não achei" de
# meia hora atrás não é evidência sobre agora. Quinze minutos é a ordem de
# grandeza de uma conversa contínua: cobre o turno seguinte, que é o caso real,
# sem transformar um "não achei" transitório em veredito do dia.
TTL_SEGUNDOS = 15 * 60

# Tetos de crescimento. O dicionário é indexado por um identificador que vem de
# fora (o envelope da requisição), num processo que fica de pé por dias: sem
# teto, isso é vazamento de memória com um nome bonito. Ao estourar, sai o mais
# antigo — quem insiste num caminho morto insiste AGORA, e é o registro recente
# que tem valor.
MAX_CHAVES_POR_CONVERSA = 32
MAX_CONVERSAS = 500

# Indireção proposital: permite ao teste andar com o relógio sem dormir 15
# minutos. Monotônico porque ajuste de relógio de parede (NTP, horário de verão)
# não pode ressuscitar nem matar um registro.
_relogio = time.monotonic

# `processar_mensagem` também é chamado de um threadpool (canal do Telegram),
# então o worker single-thread não é a única forma de execução. Sem o lock, dois
# turnos concorrentes corromperiam o OrderedDict — silenciosamente, e só sob
# carga.
_lock = threading.Lock()

# conversa -> (chave -> instante do registro). OrderedDict nos dois níveis:
# no externo é LRU de conversas, no interno é FIFO de chaves.
_becos: "OrderedDict[str, OrderedDict[Chave, float]]" = OrderedDict()


def _expirar(registros: "OrderedDict[Chave, float]") -> None:
    """Descarta em memória o que passou do TTL. Feito na leitura e na escrita
    porque não há processo de limpeza: sem varredura periódica, o único momento
    em que a memória é tocada é quando alguém fala com ela."""
    limite = _relogio() - TTL_SEGUNDOS
    for chave in [c for c, quando in registros.items() if quando < limite]:
        del registros[chave]


def lembrar(session_id: str) -> frozenset:
    """As consultas desta conversa que já voltaram sem resultado e ainda valem."""
    # Identificador vazio é caso real: a rota de inferência direta aceita string
    # vazia. Sem este no-op, todas essas chamadas cairiam num balde só e uma
    # pessoa herdaria os becos de outra — pior que não lembrar nada.
    if not session_id:
        return frozenset()
    with _lock:
        registros = _becos.get(session_id)
        if registros is None:
            return frozenset()
        _expirar(registros)
        if not registros:
            del _becos[session_id]
            return frozenset()
        _becos.move_to_end(session_id)
        return frozenset(registros)


def registrar(session_id: str, chaves) -> None:
    """Anota que estas consultas voltaram sem resultado nesta conversa."""
    if not session_id or not chaves:
        return
    with _lock:
        registros = _becos.get(session_id)
        if registros is None:
            registros = OrderedDict()
            _becos[session_id] = registros
        _becos.move_to_end(session_id)

        agora = _relogio()
        for chave in chaves:
            # Repor no fim renova o registro: repetir a consulta e falhar de novo
            # é confirmação, não motivo para envelhecer o que acabou de se provar.
            registros.pop(chave, None)
            registros[chave] = agora

        _expirar(registros)
        while len(registros) > MAX_CHAVES_POR_CONVERSA:
            registros.popitem(last=False)
        while len(_becos) > MAX_CONVERSAS:
            _becos.popitem(last=False)


def esquecer(session_id: str) -> None:
    """Invalidação explícita — a conversa recomeçou do zero."""
    if not session_id:
        return
    with _lock:
        _becos.pop(session_id, None)
