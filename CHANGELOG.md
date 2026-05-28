# Changelog

Todas as mudanças relevantes do Menu-AI são registradas aqui.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e versionamento em [SemVer](https://semver.org/lang/pt-BR/).

> Convenção: a cada commit/versão, adicione as mudanças em `[Unreleased]`. Ao marcar
> uma versão (tag), mova as entradas para uma seção `[x.y.z] - AAAA-MM-DD`.

## [Unreleased] — produto-v2 (fundação)

Reestruturação do MVP para produto: monorepo de 3 serviços (Go + Python + Vite),
base sólida com persistência, filas, RAG e isolamento por unidade.

### Added
- **Monorepo**: `apps/api` (Go), `apps/ai` (Python), `apps/web` (Vite+React+TS), `packages/contracts`, `deploy/`.
- **Regras de negócio** versionadas em `docs/regras-de-negocio.md` (referência permanente).
- **API Go (fonte da verdade)**: Postgres + pgvector com migrações embutidas; endpoints
  públicos (`/unidades`, `/unidades/{id}/cardapio`, `/chat`, `/chat/{id}`, `/chat/saudacao`, `/health`)
  e internos (`/internal/cardapio`, `/internal/usuario/{id}/perfil`, `/internal/medidas-caseiras`).
- **Cálculos de domínio**: IMC e meta calórica (Mifflin-St Jeor).
- **Sessões e memória de curto prazo** persistidas no Postgres.
- **Idempotência** via header `Idempotency-Key` (replay de resposta cacheada).
- **Filas**: RabbitMQ com padrão **Outbox transacional** + relay e **consumidores idempotentes** (inbox);
  chat via **RPC sobre fila** (Go publica, worker Python consome e responde).
- **Workers**: worker Go de eventos de domínio; worker Python de chat (`app.workers.chat_worker`).
- **Agente de IA**: tools que buscam dados na **API interna do Go** (cardápio/perfil/medidas),
  filtradas pela **unidade** do contexto; adapter LLM Ollama/Anthropic.
- **RAG (pgvector)**: adapter de embeddings, chunking, retriever híbrido (vetor + full-text) e indexador (`app.rag.indexer`).
- **Front**: **seletor de unidade** → chat por unidade (sessão gerida pelo backend); scaffolds de `/cadastro` e `/admin`; client tipado.
- **Infra**: `deploy/docker-compose.yml` (postgres+pgvector, rabbitmq, api, workers, ai, web, ollama) e `.env.example` consolidado.
- **Contrato** OpenAPI em `packages/contracts/openapi.yaml`.
- **Seed** (`cmd/seed`): 2 unidades com cardápios distintos, medidas caseiras e guias para RAG.

### Changed
- **Front** migrado para **TypeScript** com roteamento (react-router); chat agora recebe a `unidade_id` do seletor.
- **Canal Telegram** migrado para a nova estrutura de pacotes (dormente até reintegração v2).
- **Gamificação**: pontuação passa a ser baseada em **proximidade calórica/nutricional** da meta do usuário,
  e não na aderência item a item à recomendação.

### Notes
- Diferido para fases seguintes: UI/CRUD completo de cadastro e admin, gamificação completa, dashboard de desperdício, memória de longo prazo (sumarização + rerank).

## [mvp-v1] — 2026-05-25

MVP validado do assistente de cardápio "Lia".

### Added
- Backend FastAPI + LangChain com **adapter duplo de LLM** (Ollama local / Anthropic).
- 4 tools determinísticas sobre `cardapio.json` (listar, filtrar, detalhar, comparar pratos).
- **Guardrail de escopo** em 2 camadas (keywords → classificador LLM).
- Memória de sessão em RAM (janela de 6 mensagens).
- Canal **Telegram** (webhook) e front **React/Vite** de chat.
- Orquestração com logging por etapa e prewarm do Ollama.
