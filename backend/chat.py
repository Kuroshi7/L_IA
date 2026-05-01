"""Orquestração: guardrail → agent → memória."""

from langchain_core.messages import HumanMessage

from agent import executor
from guardrail import is_in_scope
from prompts import RESPOSTA_FORA_DE_ESCOPO
from sessions import adicionar_turno, get_historico_janela


def processar_mensagem(session_id: str, mensagem: str) -> dict:
    historico = get_historico_janela(session_id)
    tem_historico = len(historico) > 0

    if not is_in_scope(mensagem, tem_historico=tem_historico):
        return {"resposta": RESPOSTA_FORA_DE_ESCOPO, "fora_de_escopo": True}

    messages = list(historico) + [HumanMessage(content=mensagem)]
    resultado = executor.invoke({"messages": messages})
    final = resultado.get("messages", [])
    resposta_raw = getattr(final[-1], "content", "") if final else ""
    resposta = (resposta_raw or "").strip() or "Desculpe, não consegui processar sua pergunta. Pode reformular?"

    adicionar_turno(session_id, mensagem, resposta)

    return {"resposta": resposta, "fora_de_escopo": False}
