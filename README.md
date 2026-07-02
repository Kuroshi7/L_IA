# Menu-AI — Lia (v2)

Assistente de IA para refeitório self-service. O cliente escolhe uma **unidade**, conversa com a **Lia**,
vê o cardápio do dia completo e recebe recomendações personalizadas (restrições, preferências e meta calórica),
com porções em medidas caseiras. Depois da refeição, registra o que comeu (e o que sobrou) em linguagem
natural e **pontua** pela proximidade da meta (gamificação); o admin acompanha o **desperdício** por
unidade (índice de resto-ingesta) além de gerir unidades, alimentos, cardápios e usuários.

> O MVP validado está preservado na tag **`mvp-v1`**. Esta branch (`produto-v2`) é a reestruturação para produto.
> Regras de negócio: [`docs/regras-de-negocio.md`](docs/regras-de-negocio.md).

## Arquitetura (monorepo)

```
apps/
  api/   Go   — fonte da verdade (Postgres), API pública+interna+admin, sessões, idempotência,
                outbox/relay, gamificação (pontuação síncrona) e ETL de desperdício (worker)
  ai/    Py   — agente LLM (LangChain), tools que chamam a API Go, RAG (pgvector),
                worker RabbitMQ, canal Telegram (webhook + polling dev)
  web/   TS   — Vite + React: seletor de unidade → chat; cadastro/perfil; ranking;
                admin (unidades, alimentos, cardápio, usuários, desperdício)
packages/contracts/   openapi.yaml — contrato da API pública+admin
deploy/docker-compose.yml   Postgres+pgvector, RabbitMQ, api, workers, ai, web, ollama
docs/regras-de-negocio.md   referência permanente das regras
```

### Fluxo do chat
1. Front: usuário escolhe a **unidade** (a `unidade_id` acompanha toda a sessão — sem "unit resolver").
2. `POST /chat` na **API Go** (resolve sessão, idempotência) → publica em **RabbitMQ** (`chat.requests`, RPC).
3. **Worker Python** consome, roda o agente: guardrail → tools (cardápio/perfil via **API interna do Go**) + **RAG** (medidas caseiras/nutrição) → resposta.
4. Go correlaciona a resposta (RPC reply) e responde ao front; sessão persistida no Postgres.
5. Efeitos assíncronos via **Outbox → RabbitMQ → consumer idempotente** (inbox).

## Como rodar (Docker)

Requer Docker + Docker Compose.

```bash
cp .env.example .env            # ajuste se quiser (LLM_PROVIDER, chaves, portas)
cd deploy
docker compose up -d --build    # sobe postgres, rabbitmq, api, workers, ai, web, ollama
docker compose run --rm api-seed     # popula 2 unidades, cardápio do dia, medidas, guias
docker compose run --rm ai-indexer   # (opcional) indexa os guias no pgvector p/ RAG
```

- Front: http://localhost:5273
- API Go: http://localhost:8080/health
- RabbitMQ UI: http://localhost:15672 (guest/guest)

Para usar Claude em vez do Ollama: `LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` no `.env`
(o RAG ainda usa embeddings; mantenha o Ollama com `nomic-embed-text` ou troque `EMBED_PROVIDER`).

Escalar concorrência de IA: `docker compose up -d --scale ai-worker=3`.

## Desenvolvimento local (sem Docker)

- **API Go** (`apps/api`): `go build ./...`; precisa de Postgres+pgvector e RabbitMQ acessíveis (ver `.env`). `go run ./cmd/api`, `go run ./cmd/seed`, `go run ./cmd/worker`.
- **IA** (`apps/ai`): `pip install -r requirements.txt`; worker: `python -m app.workers.chat_worker`; API: `uvicorn app.api.main:app`.
- **Web** (`apps/web`): `npm install`; `npm run dev` (typecheck: `npm run typecheck`, build: `npm run build`).

## Endpoints principais (API Go)

Contrato completo em [`packages/contracts/openapi.yaml`](packages/contracts/openapi.yaml).

- `GET /unidades` · `GET /unidades/{id}/cardapio?data=hoje` · `GET /unidades/{id}/ranking`
- `POST /chat` (`{unidade_id, session_id?, usuario_id?, mensagem}`; header `Idempotency-Key` opcional) · `DELETE /chat/{sessionId}`
- Usuários: `POST/GET/PUT /usuarios[/{id}]` (devolve IMC + meta calórica) · `GET /usuarios/{id}/gamificacao`
- Admin (`X-Admin-Token`): unidades (CRUD + ativo), alimentos, cardápio-semana, `GET /admin/usuarios`,
  `GET /admin/unidades/{id}/desperdicio?de=&ate=` (índice de resto-ingesta, série diária, top alimentos)
- Internos (consumidos pela IA): cardápio dia/semana, perfil, gamificação, medidas caseiras,
  `POST /internal/consumo/registrar` (persiste, pontua e alimenta o desperdício), vínculo Telegram

## Telegram

O canal Telegram roda no serviço `ai-api` (`POST /webhook/telegram`). Configure `TELEGRAM_BOT_TOKEN`
(e opcionalmente `TELEGRAM_WEBHOOK_SECRET`) no `.env`:

- **Produção (webhook):** `python -m app.channels.telegram_polling set-webhook https://SEU_HOST/webhook/telegram`
- **Dev local (sem URL pública):** `python -m app.channels.telegram_polling`
- Comandos do bot: `/start` e `/unidade` (seletor de unidade via botões), `/vincular <id>` (conecta o
  perfil criado no site → personalização + pontos), `/reset`, `/ajuda`.
