"""Orquestração: guardrail → agent → memória, com logging por etapa."""

import logging
import time

from langchain_core.messages import HumanMessage

from agent import executor
from agent_callbacks import LiaTimingCallback
from guardrail import is_in_scope
from prompts import RESPOSTA_FORA_DE_ESCOPO
from sessions import adicionar_turno, get_historico_janela

log = logging.getLogger("chat")


def processar_mensagem(session_id: str, mensagem: str) -> dict:
    t0 = time.perf_counter()
    log.info(f"REQ START   | session={session_id[:12]} | msg={mensagem[:120]!r}")

    historico = get_historico_janela(session_id)
    tem_historico = len(historico) > 0

    t_g = time.perf_counter()
    in_scope = is_in_scope(mensagem, tem_historico=tem_historico)
    log.info(
        f"+{time.perf_counter()-t0:6.2f}s | GUARDRAIL  | in_scope={in_scope} "
        f"| historico_len={len(historico)} | dur={time.perf_counter()-t_g:.3f}s"
    )

    if not in_scope:
        log.info(f"+{time.perf_counter()-t0:6.2f}s | REQ END    | refused (out of scope)")
        return {"resposta": RESPOSTA_FORA_DE_ESCOPO, "fora_de_escopo": True}

    messages = list(historico) + [HumanMessage(content=mensagem)]
    callback = LiaTimingCallback(session_id=session_id)

    log.info(f"+{time.perf_counter()-t0:6.2f}s | AGENT START")
    try:
        resultado = executor.invoke(
            {"messages": messages},
            config={"callbacks": [callback]},
        )
    except Exception as e:
        log.exception(
            f"+{time.perf_counter()-t0:6.2f}s | AGENT ERROR | {type(e).__name__}: {e}"
        )
        raise

    final = resultado.get("messages", [])
    resposta_raw = getattr(final[-1], "content", "") if final else ""
    resposta = (resposta_raw or "").strip() or "Desculpe, não consegui processar sua pergunta. Pode reformular?"

    adicionar_turno(session_id, mensagem, resposta)
    log.info(
        f"+{time.perf_counter()-t0:6.2f}s | REQ END    | total={time.perf_counter()-t0:.2f}s "
        f"| llm_calls={callback.llm_calls} | resp_chars={len(resposta)}"
    )

    return {"resposta": resposta, "fora_de_escopo": False}
