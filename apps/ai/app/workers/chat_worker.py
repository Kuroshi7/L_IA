"""Worker de chat: consome `chat.requests` (RabbitMQ), roda o agente e responde
via RPC (publica em props.reply_to com o mesmo correlation_id).

Concorrência de múltiplos usuários: cada processo trata uma mensagem por vez
(prefetch=1 por padrão); escale horizontalmente rodando várias réplicas do worker.

Uso: python -m app.workers.chat_worker
"""

import json
import logging

import pika

from app import config
from app.logging_config import setup_logging

log = logging.getLogger("worker")


def _on_message(ch, method, props, body):
    # import tardio: evita carregar o LLM antes de a fila estar pronta
    from app.agent.orchestrator import processar_mensagem

    try:
        req = json.loads(body)
        result = processar_mensagem(
            session_id=req.get("session_id", ""),
            mensagem=req.get("mensagem", ""),
            unidade_id=int(req.get("unidade_id") or 0),
            usuario_id=req.get("usuario_id"),
            historico=req.get("historico"),
        )
        resp = {"resposta": result["resposta"], "fora_de_escopo": result["fora_de_escopo"]}
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
