"""Turn Controller: monta o contexto de um turno, roda o agente, devolve o texto.

A decisão de caminho continua com o modelo, dentro do loop de tool-calling —
não há um segundo modelo roteando antes. O que este módulo faz é determinístico:
escolher as tools da requisição, posicionar as instruções e impor o prazo. Um
roteador por LLM aqui custaria mais uma inferência no caminho quente, e quem
espera desiste em 60s.

Nada aqui sabe qual é o assunto da conversa: prompt, tools e reminders chegam
pelo `PerfilDeDominio`.
"""

import logging
import time
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app import config
from app.agent.motor import reminders as rem
from app.agent.motor.callbacks import TimingCallback
from app.agent.motor.llm import obter_executor
from app.agent.motor.observacao import (
    ObservacoesDoTurno,
    PrazoEsgotado,
    cache_do_turno,
    encerrar_turno,
    iniciar_turno,
    observacoes_do_turno,
)
from app.agent.motor.registry import tools_do_turno

log = logging.getLogger("chat")

RESPOSTA_VAZIA = "Desculpe, não consegui processar sua pergunta. Pode reformular?"


@dataclass
class ResultadoDeTurno:
    resposta: str
    erro: str | None = None
    llm_calls: int = 0
    tools_chamadas: list[str] = field(default_factory=list)
    observacoes: ObservacoesDoTurno | None = None

    # Cache do turno, devolvido junto: é onde o domínio deixa o que precisa
    # sobreviver ao fim do turno (o ContextVar é resetado na saída).
    cache: dict = field(default_factory=dict)


def historico_para_mensagens(historico) -> list[BaseMessage]:
    msgs: list[BaseMessage] = []
    for h in historico or []:
        conteudo = h.get("conteudo", "")
        if h.get("papel") == "assistant":
            msgs.append(AIMessage(content=conteudo))
        else:
            msgs.append(HumanMessage(content=conteudo))
    return msgs


def montar_mensagens(historico, mensagem: str, reminders=()) -> list[BaseMessage]:
    """Histórico + mensagem atual, com os reminders no fim de tudo."""
    return historico_para_mensagens(historico) + [
        HumanMessage(content=rem.anexar(mensagem, reminders))
    ]


def texto_da_resposta(conteudo) -> str:
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


def executar_turno(
    perfil,
    mensagem: str,
    contexto,
    historico=None,
    gatilhos: rem.Gatilhos | None = None,
    prazo: float | None = None,
    session_id: str = "",
) -> ResultadoDeTurno:
    gatilhos = gatilhos or rem.Gatilhos()

    specs = tools_do_turno(perfil.registro, contexto)
    agente = obter_executor(perfil.nome, perfil.system_prompt, specs)
    mensagens = montar_mensagens(historico, mensagem, perfil.reminders(gatilhos))
    callback = TimingCallback(session_id=session_id)

    token = iniciar_turno(prazo=prazo)
    try:
        resultado = agente.invoke(
            {"messages": mensagens},
            config={"callbacks": [callback], "recursion_limit": config.AGENT_RECURSION_LIMIT},
        )
    except PrazoEsgotado:
        # Quem esperava já recebeu erro do serviço que chamou; terminar o turno
        # não entrega nada e ainda segura a fila.
        log.warning("REQ ABORT | prazo esgotado | session=%s", session_id[:12])
        return ResultadoDeTurno(
            resposta=perfil.resposta_erro_transiente,
            erro="PrazoEsgotado",
            llm_calls=callback.llm_calls,
            tools_chamadas=callback.tools_chamadas,
            observacoes=observacoes_do_turno(),
            cache=cache_do_turno() or {},
        )
    except Exception as e:
        # Loop de tools (recursion_limit) ou erro terminal do modelo após os
        # retries do client. Resposta amigável; o erro completo fica no log.
        log.exception("agente falhou | session=%s", session_id[:12])
        return ResultadoDeTurno(
            resposta=perfil.resposta_erro_transiente,
            erro=type(e).__name__,
            llm_calls=callback.llm_calls,
            tools_chamadas=callback.tools_chamadas,
            observacoes=observacoes_do_turno(),
            cache=cache_do_turno() or {},
        )
    else:
        final = resultado.get("messages", [])
        bruto = getattr(final[-1], "content", "") if final else ""
        return ResultadoDeTurno(
            resposta=texto_da_resposta(bruto).strip() or RESPOSTA_VAZIA,
            llm_calls=callback.llm_calls,
            tools_chamadas=callback.tools_chamadas,
            observacoes=observacoes_do_turno(),
            cache=cache_do_turno() or {},
        )
    finally:
        encerrar_turno(token)


def prazo_a_partir_de(timestamp: float | None, orcamento_segundos: float) -> float | None:
    """Converte o instante de publicação da mensagem no prazo monotônico local.

    O relógio de parede vem de outro processo (e possivelmente de outra máquina);
    o monotônico é local. A conversão passa pelo tempo JÁ DECORRIDO, que é o que
    as duas escalas têm em comum.
    """
    if not timestamp:
        return None
    decorrido = max(0.0, time.time() - float(timestamp))
    return time.monotonic() + max(0.0, orcamento_segundos - decorrido)
