"""Orquestração de uma mensagem: guardrail → agente (com contexto de unidade) → resposta.

A memória de curto prazo (histórico) é fornecida pelo serviço Go a cada requisição;
este serviço é stateless quanto a sessão.
"""

import logging
import time

from langchain_core.messages import AIMessage, HumanMessage

from app import config
from app.agent.agent import executor, executor_primeira_do_dia
from app.agent.callbacks import LiaTimingCallback
from app.agent.context import RequestContext, reset_context, set_context
from app.agent.guardrail import is_in_scope
from app.agent.prompts import RESPOSTA_FORA_DE_ESCOPO
from app.agent.validators import verificar_resposta

log = logging.getLogger("chat")

RESPOSTA_ERRO_TRANSIENTE = (
    "Desculpe, tive um problema para consultar as informações agora. "
    "Pode tentar de novo em instantes?"
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

    # A nota da regra contratual entra como bloco de SYSTEM (executor dedicado),
    # nunca misturada à mensagem do usuário — autoridade de prompt correta e
    # imune a spoofing pelo texto do usuário.
    agente = executor_primeira_do_dia if primeira_do_dia else executor
    messages = _to_messages(historico) + [HumanMessage(content=mensagem)]
    callback = LiaTimingCallback(session_id=session_id)

    token = set_context(RequestContext(unidade_id=unidade_id, usuario_id=usuario_id))
    try:
        resultado = agente.invoke(
            {"messages": messages},
            config={
                "callbacks": [callback],
                "recursion_limit": config.AGENT_RECURSION_LIMIT,
            },
        )
    except Exception as e:
        # GraphRecursionError (loop de tools) ou erro terminal do LLM após os
        # retries do client. Resposta amigável; o erro completo fica no log.
        log.exception("agente falhou | session=%s", session_id[:12])
        return {
            "resposta": RESPOSTA_ERRO_TRANSIENTE,
            "fora_de_escopo": False,
            "erro_interno": f"{type(e).__name__}",
        }
    finally:
        reset_context(token)

    final = resultado.get("messages", [])
    resposta_raw = getattr(final[-1], "content", "") if final else ""
    resposta = _texto(resposta_raw).strip() or "Desculpe, não consegui processar sua pergunta. Pode reformular?"

    # Pós-validação (log-only): sinaliza resposta que recomenda sem ter consultado
    # o cardápio — o indicador mais barato de prato inventado.
    verificar_resposta(resposta, tools_chamadas=callback.tools_chamadas, session_id=session_id)

    log.info(
        "REQ END | total=%.2fs | llm_calls=%s | resp_chars=%d",
        time.perf_counter() - t0, callback.llm_calls, len(resposta),
    )
    return {"resposta": resposta, "fora_de_escopo": False}


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


def _texto(conteudo) -> str:
    """Content pode ser string ou lista de blocos (Anthropic)."""
    if isinstance(conteudo, str):
        return conteudo
    if isinstance(conteudo, list):
        partes = []
        for bloco in conteudo:
            if isinstance(bloco, str):
                partes.append(bloco)
            elif isinstance(bloco, dict) and bloco.get("type") == "text":
                partes.append(bloco.get("text", ""))
        return "".join(partes)
    return str(conteudo or "")
