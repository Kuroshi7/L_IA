"""Tool-calling agent (LangChain 1.x).

Suporta dois providers de LLM, selecionados pela env `LLM_PROVIDER`:
  - "ollama" (default): roda local com llama3.2 — gratuito, sem internet, mais lento (~30s/turno em CPU).
  - "anthropic": Claude API — pago (~R$ 0,03–0,08/turno em Haiku, menos com o prompt
    caching abaixo), rápido (~3s/turno), requer `ANTHROPIC_API_KEY`.

Dois executores pré-construídos compartilham o mesmo LLM:
  - `executor`: turno normal.
  - `executor_primeira_do_dia`: com a nota da regra contratual (cardápio completo
    antes da recomendação) como bloco EXTRA do system prompt — autoridade de
    sistema de verdade, não texto colado na mensagem do usuário (spoofável).

No provider anthropic o bloco base do system leva `cache_control`: o prefixo
estável (tools + persona ≈ 2.4k tokens) é reaproveitado entre chamadas e turnos,
e a nota extra fica FORA do bloco cacheado, então os dois executores compartilham
o mesmo cache.
"""

import logging
import os
import time

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage

from app import config
from app.agent.prompts import NOTA_PRIMEIRA_DO_DIA, SYSTEM_AGENT
from app.agent.tools import TOOLS

log = logging.getLogger("agent")

LLM_PROVIDER = config.LLM_PROVIDER
OLLAMA_BASE_URL = config.OLLAMA_BASE_URL
OLLAMA_MODEL = config.OLLAMA_MODEL
ANTHROPIC_MODEL = config.ANTHROPIC_MODEL


def _build_llm():
    if LLM_PROVIDER == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "LLM_PROVIDER=anthropic mas ANTHROPIC_API_KEY não está definida. "
                "Defina no .env ou troque LLM_PROVIDER=ollama."
            )
        from langchain_anthropic import ChatAnthropic

        log.info(f"LLM provider=anthropic | model={ANTHROPIC_MODEL}")
        return ChatAnthropic(
            model=ANTHROPIC_MODEL,
            max_tokens=config.LLM_MAX_TOKENS,
            temperature=0.3,
            timeout=config.LLM_TIMEOUT_SECONDS,
            max_retries=config.LLM_MAX_RETRIES,
        )

    # default: ollama
    from langchain_ollama import ChatOllama

    log.info(f"LLM provider=ollama | model={OLLAMA_MODEL} | base={OLLAMA_BASE_URL}")
    return ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0.3,
        keep_alive="30m",
        num_predict=config.LLM_MAX_TOKENS,
        num_ctx=config.OLLAMA_NUM_CTX,
        client_kwargs={"timeout": config.LLM_TIMEOUT_SECONDS},
    )


def _system_prompt(com_nota: bool):
    """System prompt no formato do provider. Anthropic usa blocos com cache_control
    (o bloco base é idêntico com e sem nota — mesmo prefixo de cache); Ollama usa
    string simples."""
    if LLM_PROVIDER == "anthropic":
        blocos = [{"type": "text", "text": SYSTEM_AGENT, "cache_control": {"type": "ephemeral"}}]
        if com_nota:
            blocos.append({"type": "text", "text": NOTA_PRIMEIRA_DO_DIA})
        return SystemMessage(content=blocos)
    texto = f"{SYSTEM_AGENT}\n\n{NOTA_PRIMEIRA_DO_DIA}" if com_nota else SYSTEM_AGENT
    return SystemMessage(content=texto)


_llm = _build_llm()

executor = create_agent(
    model=_llm,
    tools=TOOLS,
    system_prompt=_system_prompt(com_nota=False),
)

executor_primeira_do_dia = create_agent(
    model=_llm,
    tools=TOOLS,
    system_prompt=_system_prompt(com_nota=True),
)


def prewarm() -> None:
    """Pré-aquecimento — só faz sentido pro Ollama local (cold start de modelo).
    Em providers de API (Anthropic) não há cold start, então pulamos."""
    if LLM_PROVIDER == "anthropic":
        log.info("PREWARM skipped | provider=anthropic (sem cold start)")
        return

    t0 = time.perf_counter()
    try:
        llm_com_tools = _llm.bind_tools(TOOLS)
        llm_com_tools.invoke([
            SystemMessage(content=SYSTEM_AGENT),
            HumanMessage(content="oi"),
        ])
        log.info(f"PREWARM done | dur={time.perf_counter()-t0:.2f}s")
    except Exception as e:
        log.warning(f"PREWARM failed | {type(e).__name__}: {e}")
