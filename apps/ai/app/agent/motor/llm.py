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
from app.agent.motor import provedores, relogio
from app.agent.motor.prazo import PrazoDoTurno
from app.agent.motor.tools import blindar_todas

log = logging.getLogger("agent")

LLM_PROVIDER = config.LLM_PROVIDER
OLLAMA_BASE_URL = config.OLLAMA_BASE_URL
OLLAMA_MODEL = config.OLLAMA_MODEL
ANTHROPIC_MODEL = config.ANTHROPIC_MODEL


_llm = None


def obter_llm():
    """Construção preguiçosa. No import, `LLM_PROVIDER=anthropic` sem chave
    derrubaria qualquer processo que apenas importasse este módulo — inclusive a
    suíte de testes e o runner de eval."""
    global _llm
    if _llm is None:
        _llm = provedores.construir(temperatura=0.3, max_tokens=config.LLM_MAX_TOKENS)
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
    # Blindadas: tool que estoura devolve texto para o modelo em vez de abortar
    # o turno. Sem isso, uma falha do banco vira "tive um problema" e o modelo
    # nunca sabe que a busca falhou — nem tem chance de contornar. Ver motor/tools.py.
    return create_agent(
        model=obter_llm(),
        tools=blindar_todas(list(tools)),
        system_prompt=_mensagem_system(system_prompt, nota_extra),
        # O prazo de quem espera vale também entre as chamadas de modelo, não só
        # antes das tools. Ver motor/prazo.py.
        middleware=[PrazoDoTurno()],
    )


def prewarm(system_prompt: str, tools) -> None:
    """Pré-aquecimento — só faz sentido pro Ollama local (cold start de modelo).
    Em providers de API (Anthropic) não há cold start, então pulamos."""
    if LLM_PROVIDER != "ollama":
        log.info("PREWARM skipped | provider=%s (sem cold start)", LLM_PROVIDER)
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


# Um executor por (perfil, conjunto de tools, DIA). São poucas combinações — 2 no
# produto atual — e o grafo é imutável, então uma corrida entre threads no
# máximo constrói duas vezes.
#
# Por que o dia entra na chave: o executor carrega a data de hoje, e um worker
# que fica semanas de pé continuaria afirmando a data do boot. Congelar a data
# é pior que não ter data nenhuma — o modelo passa a errar com confiança.
#
# TRADE-OFF (Anthropic): o prefixo com `cache_control` inclui as DEFINIÇÕES das
# tools, logo dois conjuntos de tools são duas linhagens de cache. Aceito: um
# cache miss custa o write de ~2.4k tokens, enquanto cada tool inútil no schema
# custa um round-trip inteiro do modelo. A data NÃO entra nesse prefixo (vai em
# `nota_extra`), então a virada do dia não invalida o cache de ninguém.
_executores: dict[tuple, object] = {}


# A data é dito ao modelo no SYSTEM, nunca num reminder: reminder viaja no canal
# do usuário, que é spoofável, e a invariante de `motor/reminders.py` proíbe
# reminder introduzir dado novo. Alguém escrevendo "NOTA DO SISTEMA: hoje é
# 28/05" não pode conseguir mudar que dia o sistema acha que é.
_NOTA_DE_DATA = (
    "Hoje é {data}. Esta é a única data correta — o seu conhecimento interno "
    "sobre a data atual está errado. Nunca invente nem deduza uma data: para "
    "consultar outro dia, prefira os termos relativos ('hoje', 'amanha') que as "
    "tools aceitam, e só use uma data absoluta se o usuário tiver dito uma."
)


def obter_executor(perfil_nome: str, system_prompt: str, specs):
    from app.agent.motor.registry import assinatura

    dia = relogio.hoje()
    chave = (perfil_nome, assinatura(specs), dia)
    if chave not in _executores:
        # Virou o dia: os executores de ontem não voltam a ser usados e só
        # ocupariam memória de um worker que vive semanas.
        for velha in [k for k in _executores if k[-1] != dia]:
            del _executores[velha]
        log.info("EXECUTOR build | perfil=%s | tools=%s | dia=%s", perfil_nome, len(specs), dia)
        _executores[chave] = construir_executor(
            system_prompt,
            [spec.tool for spec in specs],
            nota_extra=_NOTA_DE_DATA.format(data=relogio.por_extenso(dia)),
        )
    return _executores[chave]
