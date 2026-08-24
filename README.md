# Menu-AI — Lia (v2)

Assistente de IA para refeitório self-service. O cliente escolhe uma **unidade**, conversa com a **Lia**,
consulta o cardápio do dia e recebe recomendações personalizadas (restrições, preferências e meta calórica),
com porções em medidas caseiras. Depois da refeição, registra o que comeu (e o que sobrou) em linguagem
natural e **pontua** pela proximidade da meta (gamificação); o admin acompanha o **desperdício** por
unidade (índice de resto-ingesta) além de gerir unidades, alimentos, cardápios e usuários.

> O MVP validado está preservado na tag **`mvp-v1`**; `produto-v2` é a reestruturação para produto.
> Esta branch (**`feat/motor-agente-onyx`**) reorganiza a camada de agente em **motor reaproveitável +
> domínio**, com barreiras de segurança em código e um harness de avaliação medido. Ainda não integrada.
>
> Regras de negócio: [`docs/regras-de-negocio.md`](docs/regras-de-negocio.md) ·
> Medições do agente: [`docs/eval-linha-de-base.md`](docs/eval-linha-de-base.md)

## Arquitetura (monorepo)

```
apps/
  api/   Go   — fonte da verdade (Postgres), API pública+interna+admin, sessões, idempotência,
                outbox/relay, gamificação (pontuação síncrona) e ETL de desperdício (worker)
  ai/    Py   — agente LLM: motor reaproveitável + domínio do refeitório, tools que chamam a
                API Go, RAG (pgvector), worker RabbitMQ, canal Telegram (webhook + polling dev)
  web/   TS   — Vite + React: seletor de unidade → chat; cadastro/perfil; ranking;
                admin (unidades, alimentos, cardápio, usuários, desperdício)
packages/contracts/   openapi.yaml — contrato da API pública+admin
deploy/docker-compose.yml   Postgres+pgvector, RabbitMQ, api, workers, ai, web, ollama
docs/regras-de-negocio.md   referência permanente das regras
.github/workflows/          CI dos três apps (offline) + eval com LLM real (sob demanda)
```

### Fluxo do chat
1. Front: usuário escolhe a **unidade** (a `unidade_id` acompanha toda a sessão — sem "unit resolver").
2. `POST /chat` na **API Go** (resolve sessão, idempotência) → publica em **RabbitMQ** (`chat.requests`, RPC).
3. **Worker Python** consome e roda um turno (detalhado abaixo).
4. Go correlaciona a resposta (RPC reply) e responde ao front; sessão persistida no Postgres.
5. Efeitos assíncronos via **Outbox → RabbitMQ → consumer idempotente** (inbox).

## Camada de agente (`apps/ai/app/agent/`)

Partida em duas metades, com a fronteira defendida por teste:

```
motor/      reaproveitável — não conhece cardápio, prato, unidade nem alimento.
            Consome apenas um PerfilDeDominio (prompt, tools, guardrail, reminders,
            regras de validação, pós-processamento e textos de resposta).
dominio/refeitorio/   este produto: as 10 tools, prompts, filtros e regras.
```

`tests/test_fronteira_motor.py` varre os fontes do motor procurando vocabulário de domínio e proíbe
`import` do lado do produto. Trocar de produto significa escrever outro perfil ao lado — não mexer no motor.

### O que acontece em um turno

| | | onde |
|---|---|---|
| 1 | **Guardrail de escopo** — keywords decidem na hora (latência); o resto vai a um classificador, que falha aberto | `dominio/refeitorio/guardrail.py` |
| 2 | **Tools escolhidas por requisição** — sem usuário identificado, as de identidade saem do schema | `motor/registry.py` |
| 3 | **Contexto montado** — reminders vão no fim da mensagem, não no system prompt | `motor/turn.py` |
| 4 | **Loop de tool-calling** — um decorator aplica prazo, memoiza leituras repetidas e colhe o que voltou | `motor/observacao.py` |
| 5 | **Pós-processamento** — o que não pode depender de o modelo lembrar (hoje: encaminhamento a profissional de saúde) | `dominio/refeitorio/perfil.py` |
| 6 | **Validação** — 5 regras; 4 registram em log, 1 bloqueia | `motor/validacao.py` |

### Dois princípios que valem para todo o resto

**Números não são gerados.** O valor nutricional nunca vem do modelo: o termo que a pessoa escreveu é
resolvido contra a base no Postgres (alimento → medida caseira → gramas → macros) e volta com procedência
e nível de confiança. Item que não resolve fica **fora do total**, e isso sobe até a interface como campo
estruturado.

**Segurança alimentar mora no código.** O conflito entre um prato e o perfil de quem conversa é calculado
em código e anotado no próprio item que o modelo lê — a regra de negócio não permite esconder o prato, só
não recomendá-lo. Uma regra bloqueante é a última barreira. O aviso reporta em vez de proibir: *"você
informou alergia a amendoim, e este prato leva amendoim"* — o assistente cruza o que a pessoa declarou com
um fato do prato, não determina o que ela pode comer.

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

Provedor do modelo em `LLM_PROVIDER`: `ollama` (padrão), `anthropic`, `openrouter` ou
`openai_compat` — este último atende **qualquer** endpoint que fale o protocolo da OpenAI
(Hugging Face, Together, Groq, DeepInfra, vLLM ou LiteLLM auto-hospedado) via `LLM_BASE_URL`,
`LLM_API_KEY` e `LLM_MODEL`. Fornecedor novo é linha de `.env`, não commit.
Os três passam pelo mesmo `motor/provedores.py`; trocar é uma variável, não um refactor.
(O RAG ainda usa embeddings; mantenha o Ollama com `nomic-embed-text` ou troque `EMBED_PROVIDER`.)

**OpenRouter** (`OPENROUTER_API_KEY`, `OPENROUTER_MODEL`) fala o protocolo da OpenAI, então o mesmo
caminho serve para vLLM, LiteLLM ou Together — só muda a URL. O default `openrouter/free` é um
**roteador**: sorteia entre os modelos gratuitos a cada chamada. Bom para produção (disponibilidade),
ruim para medir — duas rodadas da mesma bateria deixam de ser comparáveis, e variação de quem
respondeu lê como regressão do produto. Para **avaliar**, fixe um modelo:

```bash
OPENROUTER_MODEL=google/gemma-4-31b-it:free    # o avaliado
EVAL_JUIZ_PROVIDER=openrouter
EVAL_JUIZ_MODELO=z-ai/glm-5.2:free             # o juiz, de outra família
```

O juiz precisa ser fixo **e** de família diferente do avaliado: modelo julgando saída da própria
família erra de forma correlacionada. Isso vale mesmo com um provedor só — num provedor que serve
dezenas de famílias, "mesmo provedor" deixou de significar "mesmo modelo".

> **Cota do free tier:** 50 requisições/dia (1.000/dia com US$ 10 de crédito). Uma bateria de 10
> casos × 3 repetições gasta ~120 requisições entre agente e juiz; a rodada completa de 6 baterias,
> ~700. Ou seja: o free tier cobre desenvolvimento e demonstração, **não** cobre uma rodada de eval.

Escalar concorrência de IA: `docker compose up -d --scale ai-worker=3`.

## Testes e avaliação

A suíte padrão é **offline**: não gasta API, não depende de modelo local, roda em todo commit.

```bash
cd apps/ai && pytest                 # ~300 testes, sem LLM
cd apps/api && go test ./...         # unidade
cd apps/api && ./scripts/test-integration.sh   # integração, sobe um Postgres descartável
cd apps/web && npm run typecheck && npm run build
```

O eval com **modelo real** é separado (`pytest.ini` exclui o marcador `llm`) porque gasta API e é
estocástico — misturar faria o gate de merge depender do humor de um modelo.

```bash
cd apps/ai
EVAL_REPETICOES=3 LLM_PROVIDER=anthropic pytest tests/eval -m llm -s      # 60 casos, 6 baterias
EVAL_REPETICOES=3 EVAL_BATERIA=seguranca LLM_PROVIDER=anthropic pytest tests/eval -m llm -s
LLM_PROVIDER=anthropic pytest tests/eval/test_juiz_calibracao.py -m llm -s   # calibra o juiz
```

Cada caso roda N vezes: **3/3** é estável, **0/3** é defeito reproduzível, o meio é instabilidade do
modelo. Sem repetição não dá para separar as duas coisas. Custo da rodada completa: ~US$ 2,30 em Haiku 4.5.

Antes de gastar, o harness inteiro é exercitado de graça — um modelo roteirizado substitui o LLM e o
classificador do guardrail, e o caminho real roda sem API:

```bash
cd apps/ai && pytest tests/test_eval_pipeline.py
```

Resultados, método e limitações: [`docs/eval-linha-de-base.md`](docs/eval-linha-de-base.md).
Custo por provedor e qual usar em cada situação (desenvolvimento, demonstração, eval):
[`docs/custos-provedores.md`](docs/custos-provedores.md).

### Auditoria da base nutricional

A base vem de uma tabela de medidas caseiras impressa. Parte dos valores não sobrevive à conferência
contra a TACO (NEPA/UNICAMP) — arroz integral cozido consta com 257 kcal/100 g contra 123,5 da referência.
Não corrigimos o número (sem medição primária seria trocar um palpite por outro): marcamos a porção,
a confiança do cálculo cai e a Lia declara a aproximação.

```bash
cd apps/ai
python -m app.nutrition.auditoria             # relatório
python -m app.nutrition.auditoria --aplicar   # marca nutri_porcoes.suspeito
```

## Desenvolvimento local (sem Docker)

- **API Go** (`apps/api`): `go build ./...`; precisa de Postgres+pgvector e RabbitMQ acessíveis (ver `.env`). `go run ./cmd/api`, `go run ./cmd/seed`, `go run ./cmd/worker`.
- **IA** (`apps/ai`): `pip install -r requirements-dev.txt`; worker: `python -m app.workers.chat_worker`; API: `uvicorn app.api.main:app`.
- **Web** (`apps/web`): `npm install`; `npm run dev` (typecheck: `npm run typecheck`, build: `npm run build`).

## Endpoints principais (API Go)

Contrato completo em [`packages/contracts/openapi.yaml`](packages/contracts/openapi.yaml).

- `GET /unidades` · `GET /unidades/{id}/cardapio?data=hoje` · `GET /unidades/{id}/ranking`
- `POST /chat` (`{unidade_id, session_id?, usuario_id?, mensagem}`; header `Idempotency-Key` opcional) · `DELETE /chat/{sessionId}`
  - resposta traz `confianca` (opcional) quando há incerteza a declarar — itens não reconhecidos ou valor aproximado
- Usuários: `POST/GET/PUT /usuarios[/{id}]` (devolve IMC + meta calórica) · `GET /usuarios/{id}/gamificacao`
- Admin (`X-Admin-Token`): unidades (CRUD + ativo), alimentos, cardápio-semana, `GET /admin/usuarios`,
  `GET /admin/unidades/{id}/desperdicio?de=&ate=` (índice de resto-ingesta, série diária, top alimentos)
- Internos (consumidos pela IA): cardápio dia/semana, perfil, gamificação, medidas caseiras,
  `POST /internal/consumo/registrar` (persiste, pontua e alimenta o desperdício), vínculo Telegram

> Consumo com item não reconhecido é gravado mas **não pontua** (`pontuacao_pendente` explica o motivo) e
> fica fora do agregado de desperdício — o total sai subestimado, e pontuar sobre ele corromperia o ranking
> e o KPI do gestor.

## Telegram

O canal Telegram roda no serviço `ai-api` (`POST /webhook/telegram`). Configure `TELEGRAM_BOT_TOKEN`
(e opcionalmente `TELEGRAM_WEBHOOK_SECRET`) no `.env`:

- **Produção (webhook):** `python -m app.channels.telegram_polling set-webhook https://SEU_HOST/webhook/telegram`
- **Dev local (sem URL pública):** `python -m app.channels.telegram_polling`
- Comandos do bot: `/start` e `/unidade` (seletor de unidade via botões), `/vincular <id>` (conecta o
  perfil criado no site → personalização + pontos), `/reset`, `/ajuda`.
