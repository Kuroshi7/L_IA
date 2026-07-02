"""Adapter Telegram → pipeline da Lia.

Fluxo (modo webhook):
  Telegram → POST /webhook/telegram → handle_update() → processar_mensagem()
                                                     → send_message() de volta
Para desenvolvimento local sem URL pública: `python -m app.channels.telegram_polling`.

Convenções:
  - session_id namespacado: "tg:{chat_id}" — separa do canal web e reaproveita
    `sessions._sessoes` sem colisão.
  - Unidade: escolhida pelo usuário via teclado inline (/start ou /unidade) —
    mesma regra do front (sem "unit resolver"); fica em RAM por chat, com
    TELEGRAM_DEFAULT_UNIDADE_ID como fallback.
  - Usuário: /vincular <id do perfil criado no site> associa o chat ao usuário
    (persistido no Go via telegram_chat_id) → perfil, meta calórica e pontos
    passam a funcionar no Telegram.
  - Comandos: /start, /unidade, /vincular, /reset, /ajuda.
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
from app.clients import go_api
from app.memory import session_store

log = logging.getLogger("telegram")

TELEGRAM_API_BASE = "https://api.telegram.org"
SESSION_PREFIX = "tg"

# Fallback quando o usuário ainda não escolheu unidade e a listagem falhou.
TELEGRAM_DEFAULT_UNIDADE_ID = int(os.getenv("TELEGRAM_DEFAULT_UNIDADE_ID", "1"))

# Unidade escolhida por chat (RAM — 1 instância de ai-api; ver README/arquitetura).
_unidade_por_chat: dict[int, int] = {}


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


class TelegramCallbackQuery(BaseModel):
    id: str
    from_: TelegramUser | None = Field(default=None, alias="from")
    message: TelegramMessage | None = None
    data: str | None = None

    model_config = {"populate_by_name": True}


class TelegramUpdate(BaseModel):
    update_id: int
    message: TelegramMessage | None = None
    edited_message: TelegramMessage | None = None
    callback_query: TelegramCallbackQuery | None = None


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


async def send_message(chat_id: int, text: str, reply_markup: dict | None = None) -> None:
    if len(text) > MAX_TG_MESSAGE:
        text = text[: MAX_TG_MESSAGE - 1] + "…"
    payload: dict = {"chat_id": chat_id, "text": text}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    await _post("sendMessage", payload)


async def send_typing(chat_id: int) -> None:
    """Mostra "digitando..." no Telegram por ~5s — dá feedback enquanto o LLM pensa."""
    await _post("sendChatAction", {"chat_id": chat_id, "action": "typing"})


async def answer_callback(callback_id: str, text: str = "") -> None:
    await _post("answerCallbackQuery", {"callback_query_id": callback_id, "text": text})


# ---------------------------------------------------------------------------
# Unidade e usuário do chat
# ---------------------------------------------------------------------------
async def _enviar_seletor_unidade(chat_id: int, prefixo: str = "") -> None:
    """Teclado inline com as unidades ativas (mesma regra do front: escolha explícita)."""
    try:
        unidades = await asyncio.to_thread(go_api.get_unidades)
    except Exception:
        unidades = []
    if not unidades:
        _unidade_por_chat.setdefault(chat_id, TELEGRAM_DEFAULT_UNIDADE_ID)
        await send_message(chat_id, (prefixo + "\n\n" if prefixo else "")
                           + "Não consegui listar as unidades agora — vou usar a unidade padrão. "
                             "Use /unidade mais tarde para trocar.")
        return
    keyboard = {
        "inline_keyboard": [
            [{"text": f"🏢 {u['nome']}", "callback_data": f"unidade:{u['id']}"}]
            for u in unidades
        ]
    }
    texto = (prefixo + "\n\n" if prefixo else "") + "Em qual unidade você vai comer hoje?"
    await send_message(chat_id, texto, reply_markup=keyboard)


def _resolver_usuario(chat_id: int) -> int | None:
    """Usuário vinculado ao chat (persistido no Go). None = anônimo."""
    try:
        u = go_api.get_usuario_por_telegram(chat_id)
        if u and u.get("usuario", {}).get("id"):
            return int(u["usuario"]["id"])
    except Exception as e:
        log.warning(f"TG resolver usuário falhou | chat={chat_id} | {type(e).__name__}: {e}")
    return None


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------
AJUDA = (
    "Comandos:\n"
    "/unidade — escolher/trocar a unidade do refeitório\n"
    "/vincular <id> — vincular seu perfil criado no site (perfil, meta e pontos)\n"
    "/reset — recomeçar a conversa\n"
    "/ajuda — esta mensagem\n\n"
    "Fora isso, é só conversar: peça o cardápio, recomendações, ou conte o que "
    "você comeu (e o que sobrou) para ganhar pontos. 🍽️"
)


async def _cmd_vincular(chat_id: int, args: str) -> None:
    arg = args.strip()
    if not arg.isdigit():
        await send_message(chat_id,
                           "Use: /vincular <número do seu perfil>.\n"
                           "Você encontra o número na tela de cadastro do site.")
        return
    try:
        await asyncio.to_thread(go_api.vincular_telegram, int(arg), chat_id)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            await send_message(chat_id, f"Não encontrei um perfil com o número {arg}. Confira no site.")
        else:
            await send_message(chat_id, "Não consegui vincular agora. Tenta de novo daqui a pouco?")
        return
    except Exception:
        await send_message(chat_id, "Não consegui vincular agora. Tenta de novo daqui a pouco?")
        return
    await send_message(chat_id,
                       "Perfil vinculado! ✅ Agora as recomendações consideram suas restrições "
                       "e meta calórica, e você acumula pontos registrando o consumo por aqui.")


# ---------------------------------------------------------------------------
# Dispatcher principal
# ---------------------------------------------------------------------------
async def handle_update(update: TelegramUpdate) -> None:
    """Processa um update do Telegram. Pensado para rodar como BackgroundTask:
    o endpoint webhook já devolveu 200 e essa função pode levar o tempo do LLM."""
    if update.callback_query is not None:
        await _handle_callback(update.callback_query)
        return

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
        await _enviar_seletor_unidade(chat_id, prefixo=MENSAGEM_INICIAL)
        return

    if text.startswith("/unidade"):
        await _enviar_seletor_unidade(chat_id)
        return

    if text.startswith("/vincular"):
        await _cmd_vincular(chat_id, text.removeprefix("/vincular"))
        return

    if text.startswith("/ajuda") or text.startswith("/help"):
        await send_message(chat_id, AJUDA)
        return

    if text.startswith("/reset"):
        removido = session_store.resetar(session_id)
        log.info(f"TG /reset | chat={chat_id} | removido={removido}")
        await send_message(chat_id, "Conversa zerada. Pode mandar a próxima pergunta. 👇")
        return

    # Sem unidade escolhida ainda → pede a escolha antes de conversar.
    unidade_id = _unidade_por_chat.get(chat_id)
    if unidade_id is None:
        await _enviar_seletor_unidade(chat_id, prefixo="Antes de começar, preciso saber onde você está.")
        return

    # Mensagem normal — typing + processa no threadpool (processar_mensagem é sync)
    log.info(f"TG msg | chat={chat_id} | user=@{user_label} | text={text[:80]!r}")
    await send_typing(chat_id)

    usuario_id = await asyncio.to_thread(_resolver_usuario, chat_id)
    historico = _historico_dicts(session_id)
    try:
        resultado = await asyncio.to_thread(
            processar_mensagem, session_id, text, unidade_id, usuario_id, historico
        )
    except Exception as e:
        log.exception(f"TG erro no pipeline | chat={chat_id} | {type(e).__name__}: {e}")
        await send_message(chat_id, "Tive um problema técnico aqui. Pode tentar de novo daqui a pouco?")
        return

    session_store.adicionar_turno(session_id, text, resultado["resposta"])
    await send_message(chat_id, resultado["resposta"])


async def _handle_callback(cb: TelegramCallbackQuery) -> None:
    """Trata cliques nos teclados inline (hoje: escolha de unidade)."""
    data = (cb.data or "").strip()
    chat_id = cb.message.chat.id if cb.message else None
    if chat_id is None:
        await answer_callback(cb.id)
        return

    if data.startswith("unidade:") and data.split(":", 1)[1].isdigit():
        unidade_id = int(data.split(":", 1)[1])
        trocou = _unidade_por_chat.get(chat_id) not in (None, unidade_id)
        _unidade_por_chat[chat_id] = unidade_id
        if trocou:
            session_store.resetar(session_id_for(chat_id))  # contexto do cardápio muda junto
        await answer_callback(cb.id, "Unidade selecionada!")
        log.info(f"TG unidade | chat={chat_id} | unidade={unidade_id}")
        await send_message(chat_id,
                           "Unidade selecionada! ✅ Pode perguntar: \"o que tem hoje?\", "
                           "pedir recomendações, ou contar o que você comeu para pontuar.\n"
                           "Dica: /vincular <id> conecta seu perfil do site. /ajuda mostra tudo.")
        return

    await answer_callback(cb.id)
