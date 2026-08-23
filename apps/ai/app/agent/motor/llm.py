"""Construção do modelo e do executor de tools (LangChain 1.x).

Suporta dois providers, selecionados pela env `LLM_PROVIDER`:
  - "ollama" (default): roda local com llama3.2 — gratuito, sem internet, mais
    lento (~30s/turno em CPU).
  - "anthropic": Claude API — pago (~R$ 0,03–0,08/turno em Haiku, menos com o
    prompt caching abaixo), rápido (~3s/turno), requer `ANTHROPIC_API_KEY`.

Este módulo é do MOTOR: ele não sabe qual é o assunto da conversa. Prompt e tools
chegam por parâmetro, vindos do `PerfilDeDominio`.

No provider anthropic o bloco base do system leva `cache_control`: o prefixo
estável (tools + persona) é reaproveitado entre chamadas e turnos. A nota extra
fica FORA do bloco cacheado, então executores com e sem nota compartilham o mesmo
prefixo de cache.
"""

import logging
import os
import time

from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage

from app import config

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


_llm = None


def obter_llm():
    """Construção preguiçosa. No import, `LLM_PROVIDER=anthropic` sem chave
    derrubaria qualquer processo que apenas importasse este módulo — inclusive a
    suíte de testes e o runner de eval."""
    global _llm
    if _llm is None:
        _llm = _build_llm()
    return _llm


def _mensagem_system(system_prompt: str, nota_extra: str | None):
    """System prompt no formato do provider. Anthropic usa blocos com
    `cache_control` (o bloco base é idêntico com e sem nota — mesmo prefixo de
    cache); Ollama usa string simples."""
    if LLM_PROVIDER == "anthropic":
        blocos = [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]
        if nota_extra:
            blocos.append({"type": "text", "text": nota_extra})
        return SystemMessage(content=blocos)
    texto = f"{system_prompt}\n\n{nota_extra}" if nota_extra else system_prompt
    return SystemMessage(content=texto)


def construir_executor(system_prompt: str, tools, nota_extra: str | None = None):
    """Monta um agente de tool-calling com o prompt e as tools do domínio."""
    return create_agent(
        model=obter_llm(),
        tools=list(tools),
        system_prompt=_mensagem_system(system_prompt, nota_extra),
    )


def prewarm(system_prompt: str, tools) -> None:
    """Pré-aquecimento — só faz sentido pro Ollama local (cold start de modelo).
    Em providers de API (Anthropic) não há cold start, então pulamos."""
    if LLM_PROVIDER == "anthropic":
        log.info("PREWARM skipped | provider=anthropic (sem cold start)")
        return

    t0 = time.perf_counter()
    try:
        llm_com_tools = obter_llm().bind_tools(list(tools))
        llm_com_tools.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content="oi"),
        ])
        log.info(f"PREWARM done | dur={time.perf_counter()-t0:.2f}s")
    except Exception as e:
        log.warning(f"PREWARM failed | {type(e).__name__}: {e}")


# Um executor por (perfil, conjunto de tools). São poucas combinações — 2 no
# produto atual — e o grafo é imutável, então uma corrida entre threads no
# máximo constrói duas vezes.
#
# TRADE-OFF (Anthropic): o prefixo com `cache_control` inclui as DEFINIÇÕES das
# tools, logo dois conjuntos de tools são duas linhagens de cache. Aceito: um
# cache miss custa o write de ~2.4k tokens, enquanto cada tool inútil no schema
# custa um round-trip inteiro do modelo.
_executores: dict[tuple, object] = {}


def obter_executor(perfil_nome: str, system_prompt: str, specs):
    from app.agent.motor.registry import assinatura

    chave = (perfil_nome, assinatura(specs))
    if chave not in _executores:
        log.info("EXECUTOR build | perfil=%s | tools=%s", perfil_nome, len(specs))
        _executores[chave] = construir_executor(system_prompt, [spec.tool for spec in specs])
    return _executores[chave]
