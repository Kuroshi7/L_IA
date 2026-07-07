"""Orquestração de uma mensagem: guardrail → agente (com contexto de unidade) → resposta.

A memória de curto prazo (histórico) é fornecida pelo serviço Go a cada requisição;
este serviço é stateless quanto a sessão.
"""

import logging
import time

from langchain_core.messages import AIMessage, HumanMessage

from app.agent.agent import executor
from app.agent.callbacks import LiaTimingCallback
from app.agent.context import RequestContext, reset_context, set_context
from app.agent.guardrail import is_in_scope
from app.agent.prompts import RESPOSTA_FORA_DE_ESCOPO

log = logging.getLogger("chat")


def _to_messages(historico: list[dict]) -> list:
    msgs = []
    for h in historico or []:
        papel = h.get("papel")
        conteudo = h.get("conteudo", "")
        if papel == "assistant":
            msgs.append(AIMessage(content=conteudo))
        else:
            msgs.append(HumanMessage(content=conteudo))
    return msgs


NOTA_PRIMEIRA_DO_DIA = (
    "[NOTA DO SISTEMA — regra contratual: esta é a PRIMEIRA conversa do usuário hoje. "
    "Se ele pedir o cardápio, uma recomendação ou qualquer escolha de prato, você DEVE "
    "apresentar o cardápio COMPLETO do dia (chame listar_pratos_do_dia e liste todos os "
    "pratos) ANTES da recomendação, mesmo que ele não tenha pedido o cardápio.]"
)


def processar_mensagem(
    session_id: str,
    mensagem: str,
    unidade_id: int,
    usuario_id: int | None = None,
    historico: list[dict] | None = None,
    primeira_do_dia: bool = False,
) -> dict:
    t0 = time.perf_counter()
    historico = historico or []
    log.info(
        "REQ START | session=%s | unidade=%s | msg=%r",
        session_id[:12], unidade_id, mensagem[:120],
    )

    in_scope = is_in_scope(mensagem, tem_historico=len(historico) > 0)
    if not in_scope:
        log.info("REQ END | fora de escopo")
        return {"resposta": RESPOSTA_FORA_DE_ESCOPO, "fora_de_escopo": True}

    conteudo = mensagem
    if primeira_do_dia:
        # A nota vai junto da mensagem só nesta invocação; o Go persiste a mensagem
        # crua, então o histórico das próximas rodadas não carrega a nota.
        conteudo = f"{mensagem}\n\n{NOTA_PRIMEIRA_DO_DIA}"
    messages = _to_messages(historico) + [HumanMessage(content=conteudo)]
    callback = LiaTimingCallback(session_id=session_id)

    token = set_context(RequestContext(unidade_id=unidade_id, usuario_id=usuario_id))
    try:
        resultado = executor.invoke({"messages": messages}, config={"callbacks": [callback]})
    finally:
        reset_context(token)

    final = resultado.get("messages", [])
    resposta_raw = getattr(final[-1], "content", "") if final else ""
    resposta = (resposta_raw or "").strip() or "Desculpe, não consegui processar sua pergunta. Pode reformular?"

    log.info(
        "REQ END | total=%.2fs | llm_calls=%s | resp_chars=%d",
        time.perf_counter() - t0, callback.llm_calls, len(resposta),
    )
    return {"resposta": resposta, "fora_de_escopo": False}
