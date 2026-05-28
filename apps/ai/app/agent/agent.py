"""Tool-calling agent (LangChain 1.x).

Suporta dois providers de LLM, selecionados pela env `LLM_PROVIDER`:
  - "ollama" (default): roda local com llama3.2 — gratuito, sem internet, mais lento (~30s/turno em CPU).
  - "anthropic": Claude API — pago (~R$ 0,01/turno em Haiku), rápido (~3s/turno), requer `ANTHROPIC_API_KEY`.
"""

import logging
import os
import time

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage

from app import config
from app.agent.prompts import SYSTEM_AGENT
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
            max_tokens=512,
            temperature=0.3,
        )

    # default: ollama
    from langchain_ollama import ChatOllama

    log.info(f"LLM provider=ollama | model={OLLAMA_MODEL} | base={OLLAMA_BASE_URL}")
    return ChatOllama(
        model=OLLAMA_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0.3,
        keep_alive="30m",
        num_predict=512,
        num_ctx=2048,
    )


_llm = _build_llm()

executor = create_agent(
    model=_llm,
    tools=TOOLS,
    system_prompt=SYSTEM_AGENT,
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
