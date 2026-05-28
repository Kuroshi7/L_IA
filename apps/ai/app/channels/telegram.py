"""Adapter Telegram → pipeline da Lia.

Fluxo (modo webhook):
  Telegram → POST /webhook/telegram → handle_update() → processar_mensagem()
                                                     → send_message() de volta

Convenções:
  - session_id namespacado: "tg:{chat_id}" — separa do canal web e reaproveita
    `sessions._sessoes` sem colisão.
  - Comandos suportados: /start (saudação) e /reset (limpa sessão).
  - Mensagens não-texto (foto, áudio, sticker) são respondidas com aviso curto.
"""

import asyncio
import logging
import os

import httpx
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

from app.agent.orchestrator import processar_mensagem
from app.agent.prompts import MENSAGEM_INICIAL
from app.memory import session_store

log = logging.getLogger("telegram")

TELEGRAM_API_BASE = "https://api.telegram.org"
SESSION_PREFIX = "tg"

# Telegram não passa por seletor de unidade; até a reintegração v2, usa uma unidade padrão.
TELEGRAM_DEFAULT_UNIDADE_ID = int(os.getenv("TELEGRAM_DEFAULT_UNIDADE_ID", "1"))


def _historico_dicts(session_id: str) -> list[dict]:
    msgs: list[BaseMessage] = session_store.get_historico_janela(session_id)
    out = []
    for m in msgs:
        papel = "assistant" if m.__class__.__name__ == "AIMessage" else "user"
        out.append({"papel": papel, "conteudo": getattr(m, "content", "")})
    return out

# Limite de mensagem do Telegram (4096 chars). Deixo margem de segurança.
MAX_TG_MESSAGE = 4000


# ---------------------------------------------------------------------------
# Modelos do payload do Telegram (apenas os campos que usamos — Pydantic ignora o resto)
# ---------------------------------------------------------------------------
class TelegramChat(BaseModel):
    id: int


class TelegramUser(BaseModel):
    id: int
    is_bot: bool = False
    first_name: str | None = None
    username: str | None = None


class TelegramMessage(BaseModel):
    message_id: int
    chat: TelegramChat
    from_: TelegramUser | None = Field(default=None, alias="from")
    text: str | None = None

    model_config = {"populate_by_name": True}


class TelegramUpdate(BaseModel):
    update_id: int
    message: TelegramMessage | None = None
    edited_message: TelegramMessage | None = None


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
def _bot_token() -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN não está definida. "
            "Crie um bot via @BotFather e cole o token no .env."
        )
    return token


def webhook_secret() -> str | None:
    """Token compartilhado que o Telegram devolve em `X-Telegram-Bot-Api-Secret-Token`.
    Opcional, mas fortemente recomendado pra garantir que o request veio do Telegram."""
    return os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip() or None


def session_id_for(chat_id: int) -> str:
    return f"{SESSION_PREFIX}:{chat_id}"


# ---------------------------------------------------------------------------
# Saída — chamadas para a Bot API
# ---------------------------------------------------------------------------
async def _post(method: str, payload: dict) -> None:
    url = f"{TELEGRAM_API_BASE}/bot{_bot_token()}/{method}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                log.warning(f"TG API {method} falhou | status={resp.status_code} | body={resp.text[:200]}")
    except httpx.HTTPError as e:
        log.warning(f"TG API {method} erro de rede | {type(e).__name__}: {e}")


async def send_message(chat_id: int, text: str) -> None:
    if len(text) > MAX_TG_MESSAGE:
        text = text[: MAX_TG_MESSAGE - 1] + "…"
    await _post("sendMessage", {"chat_id": chat_id, "text": text})


async def send_typing(chat_id: int) -> None:
    """Mostra "digitando..." no Telegram por ~5s — dá feedback enquanto o LLM pensa."""
    await _post("sendChatAction", {"chat_id": chat_id, "action": "typing"})


# ---------------------------------------------------------------------------
# Dispatcher principal
# ---------------------------------------------------------------------------
async def handle_update(update: TelegramUpdate) -> None:
    """Processa um update do Telegram. Pensado para rodar como BackgroundTask:
    o endpoint webhook já devolveu 200 e essa função pode levar o tempo do LLM."""
    msg = update.message or update.edited_message
    if msg is None:
        log.debug(f"TG ignorado | update_id={update.update_id} | sem mensagem")
        return

    chat_id = msg.chat.id
    session_id = session_id_for(chat_id)
    text = (msg.text or "").strip()
    user_label = (msg.from_.username if msg.from_ else None) or "anon"

    if not text:
        await send_message(chat_id, "Por enquanto eu só entendo texto. Manda sua dúvida sobre o cardápio. 🙂")
        return

    # Comandos
    if text.startswith("/start"):
        log.info(f"TG /start | chat={chat_id} | user=@{user_label}")
        await send_message(chat_id, MENSAGEM_INICIAL)
        return

    if text.startswith("/reset"):
        removido = session_store.resetar(session_id)
        log.info(f"TG /reset | chat={chat_id} | removido={removido}")
        await send_message(chat_id, "Conversa zerada. Pode mandar a próxima pergunta. 👇")
        return

    # Mensagem normal — typing + processa no threadpool (processar_mensagem é sync)
    log.info(f"TG msg | chat={chat_id} | user=@{user_label} | text={text[:80]!r}")
    await send_typing(chat_id)

    historico = _historico_dicts(session_id)
    try:
        resultado = await asyncio.to_thread(
            processar_mensagem, session_id, text, TELEGRAM_DEFAULT_UNIDADE_ID, None, historico
        )
    except Exception as e:
        log.exception(f"TG erro no pipeline | chat={chat_id} | {type(e).__name__}: {e}")
        await send_message(chat_id, "Tive um problema técnico aqui. Pode tentar de novo daqui a pouco?")
        return

    session_store.adicionar_turno(session_id, text, resultado["resposta"])
    await send_message(chat_id, resultado["resposta"])
