# Changelog

Todas as mudanças relevantes do Menu-AI são registradas aqui.

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
e versionamento em [SemVer](https://semver.org/lang/pt-BR/).

> Convenção: a cada commit/versão, adicione as mudanças em `[Unreleased]`. Ao marcar
> uma versão (tag), mova as entradas para uma seção `[x.y.z] - AAAA-MM-DD`.

## [Unreleased] — produto-v2 (fundação)

### Added — Motor de agente reaproveitável (conceitos do Onyx)
- **Fronteira motor/domínio** em `apps/ai/app/agent/`: `motor/` (registry, turn controller,
  reminders, observação, validação, LLM) não conhece vocabulário de refeitório; o produto
  atual vive em `dominio/refeitorio/` e é declarado por um `PerfilDeDominio`. Trocar de
  produto = escrever outro perfil. `tests/test_fronteira_motor.py` defende a separação a
  cada commit (varredura de vocabulário + proibição de import).
- **Tool registry por requisição**: sem usuário identificado, as tools de identidade ficam
  fora do schema em vez de custarem um turno de LLM para o modelo descobrir que não pode
  usá-las. Executor cacheado por assinatura do conjunto de tools; LLM construído sob demanda.
- **Reminders no fim do contexto**: a regra contratual (cardápio completo antes da
  recomendação) deixou de ser bloco de system e passou a ser a última coisa antes da
  geração — posição com aderência muito maior. Invariante testada: um reminder só repete
  regra que já existe no system prompt, então entregá-lo pelo canal do usuário não concede
  nada novo. `executor_primeira_do_dia` deixou de existir.
- **Deadline propagado**: o worker calcula o prazo a partir do `timestamp` da mensagem AMQP
  e o turno aborta antes de cada tool quando o tempo de quem esperava acabou — em vez de
  queimar tokens de uma resposta que ninguém lê e segurar a fila.
- **Cache e compressão do turno**: as 4 tools de cardápio passaram a fazer 1 leitura da API
  em vez de 4; repetição exata de tool devolve marcador em vez do corpo.
- **Confiança visível**: `confianca.nao_reconhecidos` no contrato de chat (opcional,
  retrocompatível) e nota discreta abaixo da bolha no front. O assistente não gera número
  nutricional — resolve contra a base; quando falha, diz.

### Fixed — Total de consumo subestimado em silêncio
- Item que não resolvia contra a base entrava zerado e **não somava** aos totais
  (`store/nutri.go`), mas a pontuação de gamificação e o índice de resto do dashboard eram
  calculados sobre esse total menor. Agora `ConsumoTotais` expõe `itens_ignorados`/`completo`,
  o registro incompleto **não pontua** (devolve `pontuacao_pendente` com o motivo), a linha é
  marcada em `consumos.completo` (migração `0006`) e o agregado de desperdício a ignora.
- Na IA: a Lia declara o que não entrou na conta, e `registrar_consumo` se recusa a gravar
  quando NENHUM item foi reconhecido (seria um registro de 0 kcal, indesfazível).

### Known Issues — medidos na validação end-to-end (2026-08-23)
Stack real + Anthropic/Haiku + navegador. O que a validação mostrou, além do que passou:
- **IA-09 (crítico):** número nutricional errado com `confianca: "alta"` — 2 conchas de arroz
  integral saem como 601 kcal. A confiança mede a certeza do CASAMENTO, não a correção do
  DADO; parte da base tem `fonte: '*'` (extração por LLM sobre PDF, não verificada).
- **IA-10 (crítico):** a Lia usa o cardápio como porteiro do registro de consumo e nunca
  chama `registrar_consumo` para alimento fora dele. Na prática a camada de incerteza
  entregue aqui **não dispara em produção** até isso ser corrigido no prompt.
- **IA-11:** R2/R3 com falso positivo alto (negrito de rótulo tratado como nome de prato;
  soma legítima tratada como número inventado). Por isso seguem log-only.
- **IA-05:** primeira medição do eval: 2/10. Parte das falhas é do próprio harness (IA-14).

### Added — CI e eval
- `.github/workflows/ci.yml`: pytest (`apps/ai`), `go vet`/`go test` (`apps/api`),
  typecheck/build (`apps/web`), em paralelo.
- `.github/workflows/eval-llm.yml`: eval de 10 casos com LLM real, noturno em dia útil e
  sob demanda via label `eval`; limiar de 90% em vez de all-or-nothing (modelo é
  estocástico; gate binário vira ruído ignorado). PR de fork pula o job em vez de falhar.


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

### Added — Base nutricional + motor de consumo
- **Schema** (`migrations/0002_nutricao.sql`): `nutri_alimentos`, `nutri_porcoes`, `medida_aliases` (+ `pg_trgm` para resolução fuzzy de nomes/medidas).
- **Seed** (`seed/nutricao.json`): **144 alimentos / 344 porções** cobrindo o universo de buffet self-service — acompanhamentos (51), proteínas (40), saladas (13), pratos principais (12), frutas (11), sobremesas (7), molhos (4), queijos (4) e bebidas (2) — extraídos da tabela (kcal+macros) + legenda de medidas caseiras com plurais. Itens industrializados de lanche/doce/bebida de marca foram omitidos (não são itens de self-service); ficam para o ETL. Carregado pelo `cmd/seed`.
- **Resolução + cálculo (Go)**: `ResolverAlimento`/`ResolverPorcao` (exato → alias → trigram, com fallback p/ 100g) e `CalcularConsumo`; endpoint interno `POST /internal/consumo/calcular`. O cálculo nutricional é determinístico no banco.
- **Motor de consumo (agente)**: tool `registrar_consumo` — a LLM extrai `{alimento, medida, quantidade}` da linguagem natural e o backend devolve kcal/macros + confiança por item.
- **ETL reproduzível** (`apps/ai/app/nutrition/etl.py` + `requirements-etl.txt`): extrai os ~600 alimentos do PDF escaneado via visão da LLM, página a página, com merge no seed sem sobrescrever o núcleo verificado. Parser de rótulos de medida em `app/nutrition/medidas.py`.

### Added — Admin dashboard (gestão de cardápio e alimentos)
- **API de admin** (grupo `/admin`, gate via header `X-Admin-Token` / `ADMIN_TOKEN`): catálogo de alimentos da unidade
  (`GET/POST /admin/unidades/{id}/alimentos`, `PUT /admin/alimentos/{id}`, `PATCH .../ativo`); referência nutricional
  (`GET /admin/nutri-alimentos?q=`, `GET/POST /admin/nutri-alimentos`); cardápio semanal
  (`GET /admin/unidades/{id}/cardapio-semana?inicio=`, `PUT .../cardapio-dia/{data}/itens`, `POST .../cardapio-semana/copiar`).
- **Cadastro de alimento cria as medidas caseiras junto** (trabalho do nutricionista): o alimento do menu (`alimentos`)
  vincula-se a uma referência `nutri_alimentos` + `nutri_porcoes` — criada no ato (porções com g/kcal/macros) ou vinculada a
  uma existente. Nova coluna `alimentos.nutri_alimento_id` (migração `0003_admin.sql`) e índice único `(unidade_id, nome)`.
- **Front**: `/admin` (seletor de unidade + token), `/admin/u/:id/cardapio` (grade seg–sex por datas reais, add/remover por dia,
  marcar proteína do dia, navegação de semana e "copiar p/ próxima semana") e `/admin/u/:id/alimentos` (lista + formulário com
  seção obrigatória de medidas caseiras).
- **Seed corrigido**: alimentos passam a ser **distintos por unidade** (sem a duplicata por dia×prato do seed antigo); os dias
  do cardápio referenciam o catálogo. A migração deduplica bases pré-existentes antes de criar o índice único.

### Notes
- Diferido para fases seguintes: CRUD completo de cadastro de usuário; gamificação completa (score por proximidade da meta),
  dashboard de desperdício, memória de longo prazo (sumarização + rerank). Auth de admin é um gate por token simples (auth de
  usuário completa segue diferida).
- A tabela nutricional completa (~600 alimentos) ainda não foi ingerida: rodar o ETL com o PDF em `docs/sources/` + chave Anthropic, seguido de um passe de conferência dos números.

## [mvp-v1] — 2026-05-25

MVP validado do assistente de cardápio "Lia".

### Added
- Backend FastAPI + LangChain com **adapter duplo de LLM** (Ollama local / Anthropic).
- 4 tools determinísticas sobre `cardapio.json` (listar, filtrar, detalhar, comparar pratos).
- **Guardrail de escopo** em 2 camadas (keywords → classificador LLM).
- Memória de sessão em RAM (janela de 6 mensagens).
- Canal **Telegram** (webhook) e front **React/Vite** de chat.
- Orquestração com logging por etapa e prewarm do Ollama.
