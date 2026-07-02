"""Modo polling do Telegram — para desenvolvimento local sem URL pública.

Uso:
    python -m app.channels.telegram_polling            # long-polling (getUpdates)
    python -m app.channels.telegram_polling set-webhook https://seu-dominio/webhook/telegram
    python -m app.channels.telegram_polling del-webhook

O polling e o webhook são mutuamente exclusivos na Bot API: este script remove o
webhook automaticamente antes de começar o polling. Em produção use o webhook
(endpoint já exposto em app.api.main) e registre-o com `set-webhook`.
"""

import asyncio
import logging
import sys

import httpx

from app.logging_config import setup_logging

setup_logging()

from app.channels import telegram as tg  # noqa: E402

log = logging.getLogger("telegram.polling")

POLL_TIMEOUT_S = 30  # long-poll do getUpdates


async def _api(client: httpx.AsyncClient, method: str, **params) -> dict:
    r = await client.post(f"{tg.TELEGRAM_API_BASE}/bot{tg._bot_token()}/{method}", json=params)
    r.raise_for_status()
    return r.json()


async def run_polling() -> None:
    async with httpx.AsyncClient(timeout=POLL_TIMEOUT_S + 10) as client:
        await _api(client, "deleteWebhook")
        me = await _api(client, "getMe")
        log.info("polling iniciado | bot=@%s", me["result"].get("username"))

        offset = 0
        while True:
            try:
                data = await _api(client, "getUpdates", offset=offset, timeout=POLL_TIMEOUT_S)
            except (httpx.HTTPError, asyncio.TimeoutError) as e:
                log.warning("getUpdates falhou (%s) — tentando de novo em 3s", type(e).__name__)
                await asyncio.sleep(3)
                continue

            for raw in data.get("result", []):
                offset = max(offset, raw["update_id"] + 1)
                try:
                    update = tg.TelegramUpdate.model_validate(raw)
                except Exception as e:
                    log.warning("update inválido | %s: %s", type(e).__name__, e)
                    continue
                # processa em paralelo — não bloqueia o próximo getUpdates
                asyncio.create_task(tg.handle_update(update))


async def set_webhook(url: str) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        params: dict = {"url": url}
        secret = tg.webhook_secret()
        if secret:
            params["secret_token"] = secret
        resp = await _api(client, "setWebhook", **params)
        log.info("setWebhook → %s | %s", url, resp)


async def delete_webhook() -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await _api(client, "deleteWebhook")
        log.info("deleteWebhook | %s", resp)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "set-webhook":
        if len(args) < 2:
            print("uso: python -m app.channels.telegram_polling set-webhook <url>")
            sys.exit(1)
        asyncio.run(set_webhook(args[1]))
    elif args and args[0] == "del-webhook":
        asyncio.run(delete_webhook())
    else:
        try:
            asyncio.run(run_polling())
        except KeyboardInterrupt:
            pass
