# Menu-AI — Lia (v2)

Assistente de IA para refeitório self-service. O cliente escolhe uma **unidade**, conversa com a **Lia**,
vê o cardápio do dia completo e recebe recomendações personalizadas (restrições, preferências e meta calórica),
com porções em medidas caseiras.

> O MVP validado está preservado na tag **`mvp-v1`**. Esta branch (`produto-v2`) é a reestruturação para produto.
> Regras de negócio: [`docs/regras-de-negocio.md`](docs/regras-de-negocio.md).

## Arquitetura (monorepo)

```
apps/
  api/   Go   — fonte da verdade (Postgres), API pública+interna, sessões, idempotência, outbox/relay
  ai/    Py   — agente LLM (LangChain), tools que chamam a API Go, RAG (pgvector), worker RabbitMQ
  web/   TS   — Vite + React: seletor de unidade → chat por unidade; scaffolds de cadastro/admin
packages/contracts/   contratos compartilhados (futuro)
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

- `GET /unidades` · `GET /unidades/{id}/cardapio?data=hoje`
- `POST /chat` (`{unidade_id, session_id?, mensagem}`; header `Idempotency-Key` opcional) · `DELETE /chat/{sessionId}`
- Internos (consumidos pela IA): `GET /internal/cardapio/{unidade}/{data}`, `GET /internal/usuario/{id}/perfil`, `GET /internal/medidas-caseiras`
