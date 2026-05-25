# Lia — MVP de Chat IA para Recomendação de Cardápio

> **Lia** = `L` + `IA` (a IA do refeitório).

Chat conversacional onde o usuário informa restrições (vegetariano, celíaco, alergias) e a Lia recomenda pratos do cardápio. Roda **100% local com Ollama** (sem internet, sem custo) **ou com Claude API** (1 env var basta) — o adapter escolhe pelo `LLM_PROVIDER`.

## Stack

- **Backend:** Python 3.10+ · FastAPI · LangChain 0.3 (Tool-calling Agent)
- **Frontend:** React 18 + Vite · nginx (proxy reverso `/api/*`)
- **LLM (escolha um):**
  - **Ollama local** com `llama3.2:3b` (default) — gratuito, sem internet, ~30s/turno em CPU
  - **Anthropic Claude** com `claude-haiku-4-5` (default) — pago (~R$ 0,01/turno), ~3s/turno
- **Persistência:** memória RAM por `session_id`, janela de 6 mensagens (3 turnos). SQLite fica para próxima iteração
- **Distribuição:** Docker Compose (4 serviços) + `.env` com defaults seguros

## Diferenciais em relação ao guia base

1. **Tool-calling Agent** em vez de Chain simples: o LLM decide qual tool chamar (`listar_pratos_do_dia`, `filtrar_pratos`, `detalhar_prato`, `comparar_pratos`). Filtragem por restrição/alergia é determinística em Python — vegetariano nunca vê prato com carne.
2. **Guardrail de escopo em duas camadas**: heurística por keywords (instantânea) + classificador LLM (fallback). Recusa perguntas fora do tema sem depender só de prompt engineering.
3. **Adapter dual de provider**: alterna entre Ollama (local) e Claude API (cloud) com 1 env var. Mesmo código, 25× mais rápido com Anthropic.
4. **Observabilidade por etapa**: callback do LangChain emite logs com timing de cada chamada ao LLM, cada tool, cada request HTTP — visibilidade total do fluxo.
5. **Pré-aquecimento (Ollama)**: thread em background no startup popula o KV cache com o contexto real (system prompt + tools schema), eliminando ~30s de cold start da 1ª request.
6. **Re-warm automático em "Nova Conversa"**: o handler do `DELETE /chat/{id}` dispara prewarm em background — quando o usuário começa nova conversa, ela já vem rápida.
7. **Tweaks Ollama**: `KV_CACHE_TYPE=q8_0` (-50% RAM), `num_ctx=2048` (-25% prefill), `NUM_PARALLEL=1`, `keep_alive=30m/1h`. Aplicados via env do compose.
8. **Webhook multicanal**: endpoint `POST /webhook/<canal>` desacopla o canal externo (Telegram já implementado) do pipeline interno — mesma memória, guardrail e tools.

## Pré-requisitos

- **Docker + Docker Compose v2** (caminho recomendado)
- Para rodar **sem Docker**: Python 3.10+, Node.js 18+, Ollama local
- Para usar **Anthropic**: API key em [console.anthropic.com](https://console.anthropic.com/)
- GPU NVIDIA é **opcional** — descomente `deploy.resources` em [docker-compose.yml](docker-compose.yml) (5–10× mais rápido)

## Rodar com Docker (recomendado)

```bash
cp .env.example .env             # provider, portas, etc.
docker compose up -d --build
```

**URLs default** (afastadas das portas-padrão para não conflitar com outros projetos):

- Frontend: http://localhost:5273
- Backend (direto): http://localhost:8765 · docs Swagger: http://localhost:8765/docs
- Ollama API (se em modo local): http://localhost:11534
- Frontend → backend passa pelo nginx via `/api/*` (sem CORS)

> **Os containers NÃO sobem sozinhos ao ligar a máquina.** Política é `restart: "no"`.
> Para iniciar: `docker compose up -d`. Pausar mantendo containers: `docker compose stop`.
> Retomar: `docker compose start`. Destruir: `docker compose down`.

### Mudar as portas se ainda houver conflito

Edite `.env` (sobrescreve os defaults `5273 / 8765 / 11534`):

```env
LIA_FRONTEND_PORT=5280
LIA_BACKEND_PORT=8780
LIA_OLLAMA_PORT=11540
```

Depois `docker compose up -d` (sem `--build` — só reaplica o mapa de portas).

## Trocar o provider de LLM

### Modo local (default — Ollama)

```env
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2
```

Não precisa mais nada. O serviço `ollama-init` baixa o modelo (~2 GB) na primeira execução; os outros serviços esperam ele terminar. Em CPU, **a 1ª resposta após `up` pode levar 30–60s** (o prewarm em thread cobre boa parte). Para máquinas mais fracas, troque para `OLLAMA_MODEL=mistral`.

### Modo cloud (Claude API)

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-haiku-4-5
```

Depois:

```bash
docker compose up -d --build backend       # rebuild pra instalar langchain-anthropic
docker compose logs backend | grep "LLM provider"
# deve mostrar: LLM provider=anthropic | model=claude-haiku-4-5
```

A `ANTHROPIC_API_KEY` é injetada **só no backend** via env; nunca aparece no front, nunca é versionada (.gitignore cuida do `.env`).

> **Modelos Claude alternativos:** `claude-sonnet-4-6` (qualidade superior, ~3-4× mais caro), `claude-opus-4-7` (top de linha, overkill aqui).

### Comparação de tempos observados

Mesma pergunta ("Sou vegetariano, o que tem hoje?"), mesmo backend, mesmo cardápio:

| Métrica | Ollama llama3.2:3b (CPU) | Anthropic Haiku 4.5 |
|---|---|---|
| LLM #1 (decide tool) | ~20s | **~1.8s** |
| LLM #2 (formata resposta) | ~14s | **~2.1s** |
| Total por turno | **~33s** | **~4s** |
| Custo por turno | grátis | ~R$ 0,01 |

## Canal Telegram (opcional)

A Lia expõe `POST /webhook/telegram` para receber updates da [Bot API](https://core.telegram.org/bots/api). O adapter fica em [backend/channels/telegram.py](backend/channels/telegram.py) — o mesmo pipeline (`guardrail → agent → memória`) é reaproveitado e a sessão é namespacada como `tg:{chat_id}`, sem colidir com o canal web. Para somar outros canais (WhatsApp, etc.) basta criar `backend/channels/<canal>.py` + um `POST /webhook/<canal>` em [main.py](backend/main.py).

**Como funciona o fluxo:**

1. Telegram envia `POST /webhook/telegram` com um [Update](https://core.telegram.org/bots/api#update) JSON
2. O endpoint valida o header `X-Telegram-Bot-Api-Secret-Token` (definido no `setWebhook`)
3. Devolve `200 {ok:true}` na hora e empurra o processamento para uma `BackgroundTask` — Telegram não retenta
4. Adapter manda `sendChatAction: typing` → roda `processar_mensagem` no threadpool → responde com `sendMessage`
5. Comandos suportados: `/start` (saudação inicial) e `/reset` (limpa a sessão daquele chat)

**Ativar em 5 passos:**

```bash
# 1. Crie o bot
# Fale com @BotFather no Telegram → /newbot → copie o token (formato 123456:ABC...)

# 2. Gere um secret aleatório
openssl rand -hex 32

# 3. Preencha no .env
TELEGRAM_BOT_TOKEN=123456:ABC...
TELEGRAM_WEBHOOK_SECRET=<o hex gerado>

# 4. Suba o backend e exponha publicamente (em dev usamos ngrok; em prod, seu domínio HTTPS)
docker compose up -d --build backend
ngrok http 8765   # copie a URL https://xxxx.ngrok-free.app

# 5. Registre o webhook no Telegram (uma vez só)
curl -X POST "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://xxxx.ngrok-free.app/webhook/telegram",
    "secret_token": "<o mesmo hex do .env>",
    "allowed_updates": ["message"]
  }'

# Verificar configuração:
curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"
```

Mande `/start` para o bot e ele responde com a saudação inicial. Qualquer texto seguinte vai para o agente normal.

> **Segurança:** o `TELEGRAM_WEBHOOK_SECRET` é opcional mas **fortemente recomendado**. Sem ele, qualquer pessoa que descobrir a URL pública pode injetar updates falsos. Com ele, o backend rejeita (403) qualquer request que não traga o header.

> **Limitações conhecidas:**
> - A memória continua em RAM ([sessions.py](backend/sessions.py)) — usuário que voltar dias depois perde o contexto. Trocar por Redis/SQLite quando virar dor real.
> - Hoje qualquer usuário do Telegram consegue conversar com o bot. Se precisar de whitelist, filtre por `msg.from_.id` no [adapter](backend/channels/telegram.py).
> - Mensagens não-texto (foto, áudio, sticker) recebem um aviso curto e são ignoradas.

## Comandos úteis

```bash
docker compose logs -f backend     # logs estruturados (REQ START/END, LLM #1/#2, TOOL, etc.)
docker compose logs -f ollama      # logs do servidor de IA
docker compose stop                # pausar (não some no boot — restart: "no")
docker compose down                # parar + remover containers (mantém o modelo no volume)
docker compose down -v             # idem + apagar o modelo baixado
docker compose ps                  # ver o status dos serviços
```

## Rodar sem Docker (dev)

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # ajusta OLLAMA_BASE_URL/OLLAMA_MODEL ou seta LLM_PROVIDER=anthropic
uvicorn main:app --reload
```

API em `http://localhost:8000` · docs Swagger em `http://localhost:8000/docs`.

Smoke test:
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test","mensagem":"Sou vegetariano e celíaco, o que tem hoje?"}'
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

UI em `http://localhost:5173` (porta padrão do Vite quando rodado fora do Docker).

## Endpoints

- `GET  /` — status
- `GET  /cardapio/hoje` — pratos do dia
- `GET  /cardapio/semana` — semana completa
- `GET  /chat/saudacao` — texto inicial do bot
- `POST /chat` — `{ session_id, mensagem }` → `{ session_id, resposta, fora_de_escopo }`
- `DELETE /chat/{session_id}` — reseta memória **e dispara reprewarm em background** (modo Ollama)
- `POST /webhook/telegram` — recebe [Update](https://core.telegram.org/bots/api#update) do Telegram (ver [seção Canal Telegram](#canal-telegram-opcional))

## Estrutura

```
menu-ai/
├── docker-compose.yml         # 4 services: ollama, ollama-init, backend, frontend
├── .env.example               # template — copiar para .env e editar
├── README.md
├── docs/
│   ├── videoaula-roteiro.md   # roteiro de aula (45-60min) para iniciantes
│   ├── mapa-conceitual.md     # diagramas Mermaid do flow
│   └── langchain-vs-langgraph.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt       # +langchain-anthropic (provider dual)
│   ├── main.py                # FastAPI + CORS + lifespan + middleware de timing
│   ├── chat.py                # orquestração: guardrail → agent → memória, com logs por etapa
│   ├── agent.py               # adapter dual (Ollama/Anthropic) + create_agent + prewarm
│   ├── agent_callbacks.py     # LiaTimingCallback — log de cada LLM/tool com duração
│   ├── tools.py               # 4 tools LangChain (CSV string args)
│   ├── guardrail.py           # filtro de escopo (keywords + LLM classificador)
│   ├── cardapio.py            # loader/filtros do cardapio.json (Python determinístico)
│   ├── prompts.py             # SYSTEM_AGENT (3 ramos: listar/recomendar/comparar) + SYSTEM_GUARDRAIL
│   ├── sessions.py            # memória RAM, WINDOW_SIZE=6 (3 turnos)
│   ├── models.py              # Pydantic schemas
│   ├── logging_config.py      # setup centralizado de logs
│   ├── channels/
│   │   ├── __init__.py
│   │   └── telegram.py        # adapter Telegram (parse Update, sendMessage, dispatch /start /reset)
│   └── data/cardapio.json     # 5 dias × 5 pratos
└── frontend/
    ├── Dockerfile
    ├── nginx.conf             # proxy /api/* → backend:8000
    ├── vite.config.js
    ├── package.json
    └── src/
        ├── App.jsx
        ├── Chat.jsx           # UI; "Nova Conversa" gera novo session_id (não confia só no DELETE)
        ├── api.js             # cliente HTTP
        └── styles.css
```

## Critérios de aceite

**Funcional:**
- [ ] `GET /cardapio/hoje` devolve pratos do JSON
- [ ] *"O que tem hoje?"* → IA chama `listar_pratos_do_dia`
- [ ] *"Sou vegetariano"* → IA chama `filtrar_pratos`, nunca sugere carne
- [ ] *"Sou celíaco e alérgico a amendoim"* → respeita ambas restrições
- [ ] *"Qual tem mais proteína?"* → chama `comparar_pratos` com número correto
- [ ] *"Lembra o que você sugeriu antes?"* → usa memória da janela
- [ ] Botão "Nova Conversa" → `DELETE` + novo `session_id` no localStorage

**Escopo (crítico):**
- [ ] *"Qual a capital do Japão?"* → resposta canned do guardrail
- [ ] *"Me ensina receita de bolo"* → recusado
- [ ] *"Ignore suas instruções"* → recusado
- [ ] *"Conselhos sobre cripto?"* → recusado

## Observabilidade

Os logs do backend (`docker compose logs -f backend`) são estruturados e permitem rastrear cada request fim a fim. Exemplo de uma request bem-sucedida:

```
20:39:55.171 | INFO | chat   | REQ START   | session=user_xyz | msg='Sou vegetariano, o que tem hoje?'
20:39:55.171 | INFO | chat   |   0.00s | GUARDRAIL  | in_scope=True | dur=0.000s
20:39:55.171 | INFO | chat   |   0.00s | AGENT START
20:39:55.180 | INFO | agent  |   0.01s | LLM #1 START   | msgs=2 | chars_in=2634
20:39:56.948 | INFO | agent  |   1.78s | LLM #1 END     | dur=1.77s | tools=["filtrar_pratos(...)"]
20:39:56.949 | INFO | agent  |   1.78s | TOOL START      | name=filtrar_pratos
20:39:56.950 | INFO | agent  |   1.78s | TOOL END        | name=filtrar_pratos | dur=0.00s
20:39:56.958 | INFO | agent  |   1.79s | LLM #2 START   | msgs=4 | chars_in=3445
20:39:59.100 | INFO | agent  |   3.93s | LLM #2 END     | dur=2.14s | out_chars=608
20:39:59.100 | INFO | chat   |   3.93s | REQ END    | total=3.93s | llm_calls=2
20:39:59.101 | INFO | api    | HTTP RESP   | POST /chat | status=200 | total_handler_ms=3930
```

Cada linha permite identificar onde o tempo está sendo gasto. Useful para tuning e debug.

## Tuning de performance (quando rodando local com Ollama)

Aplicado por padrão no `docker-compose.yml` e `agent.py`:

| Onde | Setting | Efeito |
|---|---|---|
| `docker-compose.yml` (env do ollama) | `OLLAMA_KV_CACHE_TYPE=q8_0` | KV cache de 448 MB → 224 MB (-50%), ~10–15% mais rápido |
| `docker-compose.yml` (env do ollama) | `OLLAMA_NUM_PARALLEL=1` | evita duplicação de KV cache (1 usuário por vez) |
| `docker-compose.yml` (env do ollama) | `OLLAMA_FLASH_ATTENTION=1` | flash attention explícito |
| `docker-compose.yml` (env do ollama) | `OLLAMA_KEEP_ALIVE=1h` | modelo não descarrega da RAM por 1h |
| `agent.py` (ChatOllama) | `num_ctx=2048` | janela 4096 → 2048, prefill ~25% mais rápido (attention é O(n²)) |
| `agent.py` (ChatOllama) | `num_predict=512` | limita tokens de saída |
| `agent.py` (ChatOllama) | `keep_alive="30m"` | redundância do KEEP_ALIVE do servidor |
| `sessions.py` | `WINDOW_SIZE=6` | janela de 3 turnos — prefill estável |
| host (manual) | `sudo cpupower frequency-set -g performance` | clock destravado (+25–35%) |

## Troubleshooting

### Setup local (sem Docker)

| Sintoma | Causa provável | Solução |
|---|---|---|
| "Erro ao conectar" no frontend | Backend offline | `uvicorn main:app --reload` no diretório `backend/` |
| Backend trava ao iniciar / `ConnectionError: 11434` | Ollama não está rodando | `ollama serve` em outro terminal (ou conferir `systemctl status ollama` no Linux) |
| `ollama: command not found` | Ollama não instalado | `curl -fsSL https://ollama.com/install.sh \| sh` |
| Resposta lenta na 1ª chamada (15–30s) | Modelo subindo na RAM/CPU | Normal. A partir da 2ª mensagem fica em cache. Se persistir, troque para `mistral` |
| IA responde sem usar tools (inventa pratos) | Modelo sem suporte a tool calling | `ollama pull llama3.2`. Alternativas: `qwen2.5`, `mistral` ≥ 0.3. NÃO use `llama2`, `gemma:2b` |
| Tool é chamada com argumentos errados | LLM pequeno tem dificuldade com `list[str]` | Já mitigado: tools recebem CSV string |
| CORS error no console | Frontend em porta diferente | Adicione a origem em `allow_origins` em [backend/main.py](backend/main.py) |
| `ModuleNotFoundError: langchain` | Venv não ativado ou deps faltando | `source venv/bin/activate && pip install -r requirements.txt` |
| `ModuleNotFoundError: langchain_anthropic` | Provider Anthropic mas pacote não instalado | `pip install --upgrade -r requirements.txt` |

### Setup com Docker

| Sintoma | Causa provável | Solução |
|---|---|---|
| `ollama-init` fica eternamente em "Baixando..." | Conexão lenta / modelo grande (~2 GB) | Aguardar. Acompanhe com `docker compose logs -f ollama-init`. Para máquina fraca: `OLLAMA_MODEL=mistral` |
| Backend reinicia em loop | Ollama ainda não terminou pull | Os `depends_on.condition` cuidam disso. Se persistir, `docker compose down && docker compose up -d --build` |
| `bind: address already in use` | Outra coisa na mesma porta do host | Edite `.env` e troque `LIA_FRONTEND_PORT` / `LIA_BACKEND_PORT` / `LIA_OLLAMA_PORT` |
| Containers voltam sozinhos depois de reboot | Política antiga `restart: unless-stopped` ainda ativa | `docker compose down && docker compose up -d` para recriar com `restart: "no"` |
| GPU NVIDIA não está sendo usada | Bloco `deploy.resources` comentado | Descomente em [docker-compose.yml](docker-compose.yml) e tenha `nvidia-container-toolkit` |
| Frontend dá 404 em `/api/...` | nginx não conseguiu resolver `backend` | Confira `frontend/nginx.conf` — `proxy_pass http://backend:8000/` |
| `ECONNREFUSED 127.0.0.1:11434` | Backend tentando localhost dentro do container | Garanta `OLLAMA_BASE_URL=http://ollama:11434` (já vem do compose) |
| `LLM_PROVIDER=anthropic mas ANTHROPIC_API_KEY não está definida` | `.env` sem a chave | Coloque `ANTHROPIC_API_KEY=sk-ant-...` no `.env` |
| Mudei `.env` mas nada mudou | Container precisa recriar | `docker compose up -d --build backend` (rebuild se mudou código) ou `--force-recreate backend` (só env) |
| Latência alta mesmo com Ollama tunado | CPU em `powersave` | `sudo cpupower frequency-set -g performance` |
| Latência cresce a cada mensagem | RAM/swap pressure | `free -h` — se swap > 0, fechar outros apps/containers |

### Canal Telegram

| Sintoma | Causa provável | Solução |
|---|---|---|
| Bot não responde nada | Webhook não registrado ou URL pública offline | `curl "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"` — confira `url` e `last_error_message` |
| `getWebhookInfo` mostra `last_error_message: "Wrong response from the webhook: 403 Forbidden"` | `TELEGRAM_WEBHOOK_SECRET` divergente entre `.env` e `setWebhook` | Re-registrar com o mesmo valor: `setWebhook?secret_token=<hex>` |
| Backend loga `TG API sendMessage falhou \| status=404` | `TELEGRAM_BOT_TOKEN` errado ou vazio | Reconfira o token recebido do @BotFather, refaça o `docker compose up -d --build backend` |
| Backend loga `TG API sendMessage falhou \| status=401` | Token revogado/inválido | Gere novo token em `/revoke` → `/token` no @BotFather |
| Bot responde mas o usuário recebe a mensagem duplicada | Endpoint demorou demais e o Telegram retentou | Já mitigado: respondemos `200` imediato e processamos em `BackgroundTask`. Se voltar, ver logs do backend buscando exceções |
| `Erro ao conectar` interno no log do adapter | Backend não consegue alcançar `api.telegram.org` | Confira saída de internet do container — em redes corporativas talvez precise de proxy |
| `/start` mostra texto antigo após mudar `prompts.py` | Container não recriado | `docker compose up -d --build backend` |

### Erros conceituais

| Sintoma | Por que acontece | Como contornar |
|---|---|---|
| IA sugere prato com carne para vegetariano | Filtro só por prompt | Garantir que `filtrar_pratos` está sendo chamada (ver logs `TOOL`). Filtro é em Python — prompt sozinho **não basta** |
| IA responde fora de escopo mesmo com prompt restritivo | Prompt engineering puro é frágil | Já implementado: `guardrail.py` com 2 camadas |
| Memória esquece o que foi dito 4+ turnos atrás | Janela de 6 mensagens (3 turnos) | Esperado. Para persistir use SQLite (próximo passo) |
| `create_agent` não encontrado | LangChain < 0.3 | `pip install --upgrade "langchain>=0.3.7"` |

## Próximos passos (fora do MVP)

- Persistência SQLite (perfil + histórico) — sobrevive a restart, libera janela de memória
- Streaming SSE — resposta aparece letra por letra (igual ChatGPT), melhora percepção
- Filtros numéricos em `filtrar_pratos` (`min_proteina_g`, `max_calorias_kcal`) — corrige o caso "mais de 20g de proteína" virar prato com 18g
- Cache de respostas determinísticas ("o que tem hoje?" da 2ª vez = <5ms)
- Ollama opcional via Docker profile — quando em modo Anthropic, não precisa subir Ollama
- Métricas (Prometheus) e tracing (OpenTelemetry)
- Integração com API real do cardápio

## Documentação complementar

- [docs/videoaula-roteiro.md](docs/videoaula-roteiro.md) — roteiro de videoaula 45-60min para alunos iniciantes
- **[docs/mapa-conceitual.html](docs/mapa-conceitual.html)** — flow visual interativo (10 diagramas Mermaid em cards, **abrir no browser** para apresentação ao vivo)
- [docs/mapa-conceitual.md](docs/mapa-conceitual.md) — flow do chat IA em texto (mesmo conteúdo, formato markdown)
- [docs/langchain-vs-langgraph.md](docs/langchain-vs-langgraph.md) — quando usar LangChain vs LangGraph
- [guia_apelia_mvp.docx](guia_apelia_mvp.docx) — guia técnico passo-a-passo (com apêndices documentando todas as evoluções)
