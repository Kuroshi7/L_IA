"""Memória de conversa por session_id, em RAM. Janela das últimas N mensagens."""

from langchain_core.chat_history import InMemoryChatMessageHistory
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

WINDOW_SIZE = 6  # 3 turnos (user + ai) — limita prefill em CPU; Lia "esquece" >3 turnos

_sessoes: dict[str, InMemoryChatMessageHistory] = {}


def get_ou_criar(session_id: str) -> InMemoryChatMessageHistory:
    if session_id not in _sessoes:
        _sessoes[session_id] = InMemoryChatMessageHistory()
    return _sessoes[session_id]


def get_historico_janela(session_id: str) -> list[BaseMessage]:
    if session_id not in _sessoes:
        return []
    msgs = _sessoes[session_id].messages
    return msgs[-WINDOW_SIZE:] if len(msgs) > WINDOW_SIZE else msgs


def adicionar_turno(session_id: str, user_msg: str, ai_msg: str) -> None:
    hist = get_ou_criar(session_id)
    hist.add_message(HumanMessage(content=user_msg))
    hist.add_message(AIMessage(content=ai_msg))


def resetar(session_id: str) -> bool:
    return _sessoes.pop(session_id, None) is not None
