"""FastAPI do serviço de IA.

Na arquitetura v2, o fluxo principal de chat é assíncrono via RabbitMQ
(app.workers.chat_worker). Esta API expõe:
  - GET  /health  → healthcheck
  - POST /infer    → inferência síncrona (útil para testes sem a fila)
  - POST /webhook/telegram → canal Telegram (dormente até reintegração; usa unidade padrão)
"""

import logging

from app.logging_config import setup_logging

setup_logging()

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request

from app.api.models import InferRequest, InferResponse

log = logging.getLogger("api")

app = FastAPI(title="Menu-AI — Serviço de IA", version="2.0.0")


@app.get("/health")
def health():
    return {"status": "ok", "servico": "menu-ai ai"}


@app.post("/infer", response_model=InferResponse)
def infer(req: InferRequest):
    from app.agent.orchestrator import processar_mensagem

    try:
        resultado = processar_mensagem(
            session_id=req.session_id,
            mensagem=req.mensagem,
            unidade_id=req.unidade_id,
            usuario_id=req.usuario_id,
            historico=[t.model_dump() for t in req.historico],
        )
    except Exception as e:
        log.exception("/infer falhou | %s: %s", type(e).__name__, e)
        raise HTTPException(status_code=500, detail=f"Erro ao processar: {e}")
    return InferResponse(**resultado)


@app.post("/webhook/telegram")
async def webhook_telegram(
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    from app.channels import telegram as tg

    expected = tg.webhook_secret()
    if expected and x_telegram_bot_api_secret_token != expected:
        raise HTTPException(status_code=403, detail="Invalid secret token")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Body precisa ser JSON")

    try:
        update = tg.TelegramUpdate.model_validate(payload)
    except Exception as e:
        log.warning("TG webhook | update inválido | %s: %s", type(e).__name__, e)
        return {"ok": True, "ignored": True}

    background_tasks.add_task(tg.handle_update, update)
    return {"ok": True}
