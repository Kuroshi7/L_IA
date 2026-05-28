import logging
import threading
import time
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

# logging precisa ser configurado ANTES dos imports que dependem do agent/LLM,
# senão handlers do uvicorn sobrescrevem o nosso formato.
from logging_config import setup_logging

setup_logging()

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from agent import prewarm
from cardapio import get_cardapio_semana, get_pratos_do_dia
from channels import telegram as tg_channel
from chat import processar_mensagem
from models import MensagemRequest, MensagemResponse
from prompts import MENSAGEM_INICIAL
from sessions import resetar

log = logging.getLogger("api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("LIFESPAN start | disparando prewarm em background")
    threading.Thread(target=prewarm, daemon=True).start()
    yield
    log.info("LIFESPAN stop")


app = FastAPI(title="Lia Chat API", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    """Mede o tempo total do handler HTTP — da entrada do FastAPI até a resposta
    pronta pra ser escrita no socket. Comparar com `REQ END` (que loga só o
    processamento dentro de processar_mensagem) revela quanto tempo é gasto em
    Pydantic/uvicorn/middleware após o LLM terminar."""
    t0 = time.perf_counter()
    response = await call_next(request)
    dur_ms = (time.perf_counter() - t0) * 1000
    if request.url.path == "/chat" and request.method == "POST":
        log.info(f"HTTP RESP   | POST /chat | status={response.status_code} | total_handler_ms={dur_ms:.0f}")
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:5273",
        "http://localhost:3000",
        "http://localhost",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def raiz():
    return {"status": "ok", "servico": "Apélia Chat API"}


@app.get("/cardapio/hoje")
def cardapio_hoje():
    pratos = get_pratos_do_dia("hoje")
    return {"pratos": pratos, "total": len(pratos)}


@app.get("/cardapio/semana")
def cardapio_semana():
    return {"dias": get_cardapio_semana()}


@app.get("/chat/saudacao")
def saudacao():
    return {"mensagem": MENSAGEM_INICIAL}


@app.post("/chat", response_model=MensagemResponse)
def chat(request: MensagemRequest):
    try:
        resultado = processar_mensagem(request.session_id, request.mensagem)
    except Exception as e:
        # log.exception inclui o stack trace completo nos logs do container
        log.exception(f"/chat falhou | session={request.session_id[:12]} | {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao processar mensagem: {e}")

    return MensagemResponse(
        session_id=request.session_id,
        resposta=resultado["resposta"],
        fora_de_escopo=resultado["fora_de_escopo"],
    )


@app.post("/webhook/telegram")
async def webhook_telegram(
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
):
    """Webhook do Telegram (https://core.telegram.org/bots/api#setwebhook).

    Boas práticas que seguimos aqui:
      - Validação do header `X-Telegram-Bot-Api-Secret-Token` (se configurado no .env).
        Sem isso, qualquer um que descobrir a URL pode injetar updates falsos.
      - Resposta 200 imediata + processamento em BackgroundTask. O Telegram considera
        que falhamos se demorarmos demais e fica retentando, o que duplica respostas.
    """
    expected = tg_channel.webhook_secret()
    if expected and x_telegram_bot_api_secret_token != expected:
        log.warning("TG webhook | secret token inválido — request rejeitado")
        raise HTTPException(status_code=403, detail="Invalid secret token")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Body precisa ser JSON")

    try:
        update = tg_channel.TelegramUpdate.model_validate(payload)
    except Exception as e:
        log.warning(f"TG webhook | update inválido | {type(e).__name__}: {e}")
        # Devolve 200 mesmo assim — não queremos que o Telegram retente um payload
        # que nunca vai bater nosso schema.
        return {"ok": True, "ignored": True}

    background_tasks.add_task(tg_channel.handle_update, update)
    return {"ok": True}


@app.delete("/chat/{session_id}")
def limpar(session_id: str):
    removido = resetar(session_id)
    # Re-aquece o KV cache do Ollama em background. Quando o usuário clica
    # "Nova Conversa", normalmente leva alguns segundos pensando o que
    # perguntar — esses segundos cobrem o re-warm. A próxima 1ª mensagem
    # volta a aproveitar o prefixo system+tools (LLM #1 ~3-6s em vez de ~30s).
    threading.Thread(target=prewarm, daemon=True).start()
    log.info(f"DELETE /chat/{session_id[:12]} | removido={removido} | reprewarm disparado")
    return {"reset": removido}
