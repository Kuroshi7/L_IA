"""Worker de chat: consome `chat.requests` (RabbitMQ), roda o agente e responde
via RPC (publica em props.reply_to com o mesmo correlation_id).

Concorrência de múltiplos usuários: cada processo trata uma mensagem por vez
(prefetch=1 por padrão); escale horizontalmente rodando várias réplicas do worker.

MEMÓRIA ENTRE TURNOS — ESTADO NO PROCESSO (dívida consciente). O que uma tool
descobriu não atravessa o turno pelo envelope: o histórico que chega aqui é só
texto de pessoa e de assistente. `motor/memoria.py` cobre o essencial disso
guardando, em memória do processo, quais consultas já voltaram sem resultado em
cada conversa. Consequência: com mais de uma réplica consumindo esta fila — ou
depois de um restart, ou pelo canal do Telegram, que roda noutro processo —
turnos da mesma conversa caem em processos diferentes e a memória não é
encontrada. O efeito é voltar ao comportamento anterior (o modelo pode repetir
uma consulta que já falhou), nunca uma resposta errada; por isso não vale
travar a escala horizontal por ela.

Durabilidade de verdade exige campo novo no envelope RPC e na persistência do
lado Go. Este arquivo é a costura por onde isso entraria: o que o Go mandasse
junto do histórico seria repassado a `processar_mensagem` e o que o turno
aprendesse voltaria na resposta, para o Go gravar. Enquanto isso não existe, os
tetos e o TTL ficam em `motor/memoria.py`, onde são testáveis sem fila.

Uso: python -m app.workers.chat_worker
"""

import json
import logging
import time

import pika

from app import config
from app.logging_config import setup_logging

log = logging.getLogger("worker")


def _expirada(props) -> bool:
    """True se a mensagem esperou na fila mais que REQUEST_MAX_AGE_SECONDS.

    O Go publica com `timestamp` e desiste após CHAT_TIMEOUT_SECONDS (o front já
    recebeu 502) — processar uma request velha só atrasa quem ainda está esperando
    (head-of-line blocking). O publisher também seta `expiration`, então o próprio
    RabbitMQ descarta a maioria; este é o cinto de segurança para brokers/mensagens
    antigas sem a propriedade."""
    ts = getattr(props, "timestamp", None)
    if not ts:
        return False
    return (time.time() - float(ts)) > config.REQUEST_MAX_AGE_SECONDS


def _on_message(ch, method, props, body):
    # import tardio: evita carregar o LLM antes de a fila estar pronta
    from app.agent.motor.turn import prazo_a_partir_de
    from app.agent.orchestrator import processar_mensagem

    if _expirada(props):
        log.warning(
            "mensagem expirada descartada | age>%ss | corr=%s",
            config.REQUEST_MAX_AGE_SECONDS, props.correlation_id,
        )
        ch.basic_ack(delivery_tag=method.delivery_tag)
        return

    try:
        req = json.loads(body)
        result = processar_mensagem(
            session_id=req.get("session_id", ""),
            mensagem=req.get("mensagem", ""),
            unidade_id=int(req.get("unidade_id") or 0),
            usuario_id=req.get("usuario_id"),
            historico=req.get("historico"),
            primeira_do_dia=bool(req.get("primeira_do_dia")),
            is_admin=bool(req.get("admin")),
            # Mesmo orçamento que o `_expirada` acima usa para DESCARTAR: a
            # diferença é que aquele só age antes de começar, e um turno pode
            # encadear várias chamadas de modelo e estourar o tempo no meio.
            deadline=prazo_a_partir_de(
                getattr(props, "timestamp", None), config.REQUEST_MAX_AGE_SECONDS
            ),
        )
        resp = {"resposta": result["resposta"], "fora_de_escopo": result["fora_de_escopo"]}
        if result.get("confianca"):
            resp["confianca"] = result["confianca"]
    except Exception as e:  # nunca derruba o worker; devolve erro estruturado
        log.exception("falha ao processar mensagem")
        resp = {"resposta": "", "fora_de_escopo": False, "erro": f"{type(e).__name__}: {e}"}

    if props.reply_to:
        ch.basic_publish(
            exchange="",
            routing_key=props.reply_to,
            properties=pika.BasicProperties(
                correlation_id=props.correlation_id,
                content_type="application/json",
            ),
            body=json.dumps(resp).encode("utf-8"),
        )
    ch.basic_ack(delivery_tag=method.delivery_tag)


def main():
    setup_logging()

    # Preflight ANTES de tocar na fila: alcança o provedor e faz tool calling?
    # Falhar aqui é barulhento e óbvio; falhar depois é silencioso e o usuário
    # paga. Em 24/08/2026 o worker subiu com provedor inalcançável e respondeu
    # "tente de novo" a cada mensagem, sem nada no log de partida.
    if config.PREFLIGHT_OBRIGATORIO:
        from app.agent.motor import preflight, provedores
        preflight.exigir(
            lambda: provedores.construir(
                temperatura=0, max_tokens=preflight.MAX_TOKENS_SONDA
            )
        )
    else:
        log.warning("PREFLIGHT desligado por configuração — não use assim em produção")

    # aquece o modelo (Ollama) antes de aceitar mensagens — evita cold start no 1º usuário
    from app.agent.orchestrator import prewarm
    prewarm()

    params = pika.URLParameters(config.RABBITMQ_URL)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.queue_declare(queue=config.CHAT_REQUESTS_QUEUE, durable=True)
    ch.basic_qos(prefetch_count=config.PREFETCH)
    ch.basic_consume(queue=config.CHAT_REQUESTS_QUEUE, on_message_callback=_on_message)

    log.info("worker de chat iniciado | fila=%s | prefetch=%s", config.CHAT_REQUESTS_QUEUE, config.PREFETCH)
    try:
        ch.start_consuming()
    except KeyboardInterrupt:
        ch.stop_consuming()
    finally:
        conn.close()


if __name__ == "__main__":
    main()
