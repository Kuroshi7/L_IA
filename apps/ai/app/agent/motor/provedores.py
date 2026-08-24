"""Construção do modelo, num lugar só.

Antes disto o mesmo `if provider == ...` vivia em três arquivos — o agente, o
classificador de escopo e o juiz do eval. Três cópias significam que acrescentar
um provider é acrescentar três oportunidades de divergir, e foi por isso que
esta função existe antes do terceiro provider entrar.

Cada chamador passa os SEUS parâmetros (temperatura, teto de saída), porque o
papel é dele; o que se centraliza aqui é só a escolha e a construção do cliente.
"""

import logging
import os

from app import config

log = logging.getLogger("agent")


def _openai_compativel(base_url: str, chave: str, modelo: str, temperatura: float, max_tokens: int):
    """Qualquer endpoint que fale o protocolo da OpenAI — OpenRouter, vLLM,
    LiteLLM, Together. O que muda é a URL, a chave e o nome do modelo."""
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=modelo,
        base_url=base_url,
        api_key=chave,
        temperature=temperatura,
        max_tokens=max_tokens,
        timeout=config.LLM_TIMEOUT_SECONDS,
        max_retries=config.LLM_MAX_RETRIES,
    )


def construir(temperatura: float, max_tokens: int, num_ctx: int | None = None,
              provider: str | None = None):
    """Modelo do provider pedido, ou do configurado em `LLM_PROVIDER`.

    O parâmetro existe para quem precisa de um modelo INDEPENDENTE do que o
    agente usa — hoje, o juiz do eval: modelo julgando saída da própria
    família tende a erro correlacionado, e trocar o provider do agente não
    pode arrastar o juiz junto.

    `num_ctx` só existe para o Ollama, que precisa da janela declarada no
    cliente; os demais a inferem do modelo.
    """
    provider = provider or config.LLM_PROVIDER

    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if not os.getenv("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "LLM_PROVIDER=anthropic mas ANTHROPIC_API_KEY não está definida. "
                "Defina no .env ou troque LLM_PROVIDER."
            )
        log.info("LLM provider=anthropic | model=%s", config.ANTHROPIC_MODEL)
        return ChatAnthropic(
            model=config.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            temperature=temperatura,
            timeout=config.LLM_TIMEOUT_SECONDS,
            max_retries=config.LLM_MAX_RETRIES,
        )

    if provider == "openrouter":
        if not config.OPENROUTER_API_KEY:
            raise RuntimeError(
                "LLM_PROVIDER=openrouter mas OPENROUTER_API_KEY não está definida."
            )
        log.info("LLM provider=openrouter | model=%s", config.OPENROUTER_MODEL)
        return _openai_compativel(
            config.OPENROUTER_BASE_URL, config.OPENROUTER_API_KEY,
            config.OPENROUTER_MODEL, temperatura, max_tokens,
        )

    # default: ollama
    from langchain_ollama import ChatOllama

    log.info("LLM provider=ollama | model=%s | base=%s", config.OLLAMA_MODEL, config.OLLAMA_BASE_URL)
    return ChatOllama(
        model=config.OLLAMA_MODEL,
        base_url=config.OLLAMA_BASE_URL,
        temperature=temperatura,
        keep_alive="30m",
        num_predict=max_tokens,
        num_ctx=num_ctx or config.OLLAMA_NUM_CTX,
        client_kwargs={"timeout": config.LLM_TIMEOUT_SECONDS},
    )
