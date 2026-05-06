# Mapa Conceitual — Flow do Chat IA da Lia

> Esse documento mostra **visualmente** como uma mensagem do usuário vira uma recomendação. Use os diagramas no quadro durante a videoaula. Todos são em Mermaid — renderizam direto no GitHub/VS Code.

---

## 1. Visão de alto nível: as 3 camadas

```mermaid
flowchart LR
    subgraph BROWSER["🖥️ Navegador (cliente)"]
        UI[React + Vite<br/>Chat.jsx]
    end

    subgraph SERVER["🐍 Backend (FastAPI)"]
        API[main.py<br/>+ middleware timing]
        CHAT[chat.py<br/>orquestrador]
        GUARD[guardrail.py]
        AGENT[agent.py<br/>LangChain<br/>+ adapter dual]
        CB[agent_callbacks.py<br/>logs por etapa]
        TOOLS[tools.py<br/>4 tools]
        SESS[sessions.py<br/>memória RAM]
        DATA[(cardapio.json)]
    end

    subgraph LLM["🧠 LLM (escolha um)"]
        OLLAMA[Ollama local<br/>llama3.2:3b]
        ANTHROPIC[Claude API<br/>claude-haiku-4-5]
    end

    UI -->|HTTP POST /chat| API
    API --> CHAT
    CHAT --> GUARD
    CHAT --> AGENT
    CHAT --> SESS
    GUARD -.->|fallback| OLLAMA
    GUARD -.->|fallback| ANTHROPIC
    AGENT <-.->|LLM_PROVIDER=ollama| OLLAMA
    AGENT <-.->|LLM_PROVIDER=anthropic| ANTHROPIC
    AGENT --> CB
    AGENT --> TOOLS
    TOOLS --> DATA

    style ANTHROPIC fill:#fec,stroke:#c80
    style OLLAMA fill:#9ef,stroke:#06c
```

**Leia esse diagrama assim:**
1. **Navegador** envia uma mensagem por HTTP.
2. **Backend** (FastAPI) recebe, passa pelo middleware de timing, depois pro orquestrador (`chat.py`).
3. Orquestrador chama o **guardrail** (filtra fora-de-escopo).
4. Se passou, chama o **agent** (LangChain), que conversa com o **LLM escolhido** e usa **tools** quando necessário.
5. O **adapter** em `agent.py` decide o provider via `LLM_PROVIDER`: Ollama local OU Claude API.
6. **Tools** leem o `cardapio.json` (verdade absoluta sobre os pratos).
7. **Callbacks** logam cada chamada de LLM e tool com timing.
8. Resposta volta pelo mesmo caminho.

---

## 2. Sequência detalhada de uma mensagem (caminho feliz)

```mermaid
sequenceDiagram
    autonumber
    participant U as 👤 Usuário
    participant F as ⚛️ React (Chat.jsx)
    participant API as 🚀 FastAPI (main.py)
    participant C as 🎯 chat.py
    participant G as 🛡️ guardrail.py
    participant A as 🤖 agent.py
    participant L as 🧠 Ollama (llama3.2)
    participant T as 🔧 tools.py
    participant D as 📄 cardapio.json
    participant S as 💾 sessions.py

    U->>F: digita "sou vegetariano"
    F->>API: POST /chat<br/>{session_id, mensagem}
    API->>C: processar_mensagem()
    C->>S: get_historico_janela()
    S-->>C: últimas 20 msgs
    C->>G: is_in_scope("sou vegetariano")
    Note over G: 1) match keyword ✅<br/>(não precisa do LLM)
    G-->>C: True

    C->>A: executor.invoke({messages})
    A->>L: prompt + tools schema
    L-->>A: "vou chamar filtrar_pratos<br/>com restricoes='vegetariano'"
    A->>T: filtrar_pratos("vegetariano")
    T->>D: get_pratos_do_dia("hoje")
    D-->>T: 5 pratos do dia
    Note over T: filtra em Python<br/>(determinístico)
    T-->>A: 2 pratos compatíveis
    A->>L: resultado da tool
    L-->>A: texto formatado<br/>"🍽️ Bowl Vegano..."
    A-->>C: resposta final

    C->>S: adicionar_turno(user, ai)
    C-->>API: {resposta, fora_de_escopo: false}
    API-->>F: JSON
    F-->>U: renderiza bolha
```

---

## 3. O loop interno do Agent (a parte "mágica" do LangChain)

> É AQUI que mora o tool calling. Mostre essa parte com calma.

```mermaid
flowchart TD
    START([Mensagem do usuário<br/>chega no agent]) --> BUILD[Monta prompt:<br/>system + histórico + msg]
    BUILD --> CALL[Chama o LLM<br/>com schema das tools]
    CALL --> CHECK{LLM decidiu<br/>chamar tool?}
    CHECK -->|Sim| EXEC[Executa a função<br/>Python da tool]
    EXEC --> APPEND[Anexa resultado<br/>como ToolMessage]
    APPEND --> CALL
    CHECK -->|Não — só texto| FINAL[Resposta final<br/>em linguagem natural]
    FINAL --> END([Devolve pro chat.py])

    style EXEC fill:#9ef,stroke:#06c
    style CALL fill:#fec,stroke:#c80
    style CHECK fill:#fcf,stroke:#a0a
```

**O ponto-chave que confunde iniciantes:**
- O LLM **não executa código**. Ele só **escreve um JSON** dizendo "quero chamar X com argumentos Y".
- O LangChain pega esse JSON, **executa a função Python**, e devolve o resultado pro LLM.
- O LLM olha o resultado e decide: chamar outra tool? Já tem o suficiente pra responder?
- Esse loop pode rodar 1 ou várias vezes. No nosso caso, geralmente 1–2 voltas.

---

## 4. Guardrail em duas camadas

```mermaid
flowchart TD
    MSG[/"Mensagem:<br/>'me ensina a fazer bolo'"/] --> NORM[Normaliza<br/>minúscula, sem acento]
    NORM --> KW{Match com<br/>keywords do<br/>cardápio?}
    KW -->|Sim| OK1([✅ no escopo])
    KW -->|Não| HIST{Tem histórico<br/>+ é continuação<br/>curta?<br/>'ok', 'sim', 'mais'}
    HIST -->|Sim| OK2([✅ no escopo])
    HIST -->|Não| LLM[Chama LLM<br/>classificador<br/>SYSTEM_GUARDRAIL]
    LLM --> RESP{Resposta<br/>começa com<br/>'sim'?}
    RESP -->|Sim| OK3([✅ no escopo])
    RESP -->|Não| BLOCK([❌ fora de escopo<br/>resposta canned])
    LLM -.->|Ollama caiu| FAILSAFE([❌ fail-closed:<br/>recusa por padrão])

    style OK1 fill:#9f9
    style OK2 fill:#9f9
    style OK3 fill:#9f9
    style BLOCK fill:#f99
    style FAILSAFE fill:#f99
```

**Por que duas camadas?**
- **Keyword é instantânea (~0ms)**, mas falsos negativos: "preciso de algo gostoso e nutritivo" não tem `cardapio` mas é válido.
- **LLM cobre o resto (~500ms)**, mas é caro chamar pra TODA mensagem.
- **Combinando**: 90% das mensagens nunca chegam no LLM classificador. Só os casos ambíguos.

---

## 5. Estrutura de uma Tool (anatomia)

```mermaid
flowchart TB
    subgraph TOOL["@tool def filtrar_pratos(...)"]
        DECO["@tool<br/>(decorator LangChain)"]
        SIG["Assinatura:<br/>restricoes: str = ''<br/>alergias: str = ''<br/>preferencias: str = ''<br/>dia: str = 'hoje'"]
        DOC["Docstring:<br/>'Filtra pratos do dia que atendem<br/>TODAS as restrições...<br/>Use SEMPRE quando...'"]
        BODY["Corpo Python:<br/>filtragem determinística"]
    end

    LLM[🧠 LLM] -->|lê o schema<br/>gerado da assinatura| SIG
    LLM -->|lê pra decidir<br/>QUANDO usar| DOC
    LLM -.->|nunca lê| BODY

    style DOC fill:#fec,stroke:#c80
    style BODY fill:#9ef,stroke:#06c
```

**Aprendizado:**
- O **schema dos argumentos** vem dos tipos Python (a IA entende `str`, `int`, `list[dict]`, etc).
- A **docstring é o "manual de uso" pro LLM**. Reescrever a docstring → muda o comportamento.
- O **corpo da função** o LLM nunca vê — é segurança: ele não pode "manipular" código que não enxerga.

---

## 6. Memória de conversa

```mermaid
flowchart LR
    subgraph SESS["sessions.py — RAM"]
        DICT["dict[session_id, ChatMessageHistory]"]
    end

    USER1[👤 user_abc123] -->|envia msg 1| ADD1[adicionar_turno]
    ADD1 -->|append HumanMessage<br/>+ AIMessage| DICT
    USER1 -->|envia msg 2| GET[get_historico_janela]
    GET -->|últimas 20 msgs<br/>10 turnos| DICT
    DICT -.->|reset| DEL[DELETE /chat/abc123]

    USER2[👤 user_xyz789] -.->|nunca enxerga<br/>msgs do user_abc123| DICT
```

**Pontos:**
- **Sessão = chave** (`session_id`). Frontend gera UUID, salva no `localStorage`.
- **Janela de 20 mensagens** = LLM recebe só as últimas 10 trocas (custo de token + relevância).
- **Volátil**: reiniciou backend, perdeu memória. **SQLite é o próximo passo**.

---

## 7. Flow do Docker Compose

```mermaid
flowchart TD
    UP[docker compose up] --> O[ollama<br/>servidor LLM]
    O -->|healthcheck OK| OI[ollama-init<br/>baixa o modelo]
    OI -->|completed| B[backend<br/>FastAPI :8000]
    B --> F[frontend<br/>nginx :80]

    F -.->|proxy /api/*| B
    B -.->|HTTP :11434| O

    style O fill:#fec
    style OI fill:#fec
    style B fill:#9ef
    style F fill:#cfc

    UP -.->|volume| V[(ollama_data<br/>cache do modelo)]
    O -.- V
```

**Ordem garantida pelo `depends_on`:**
1. `ollama` sobe e fica esperando pull.
2. `ollama-init` (uma vez só) verifica/baixa o modelo, então **encerra** (`restart: "no"`).
3. `backend` e `frontend` só sobem depois disso.

---

## 8. Adapter dual de provider (Ollama vs Anthropic)

```mermaid
flowchart TD
    START([backend startup]) --> READ[Lê env LLM_PROVIDER]
    READ --> DEC{LLM_PROVIDER<br/>= ?}

    DEC -->|"ollama"<br/>(default)| LCO[from langchain_ollama<br/>import ChatOllama]
    LCO --> CFGO[ChatOllama com<br/>num_ctx=2048<br/>keep_alive=30m<br/>num_predict=512]
    CFGO --> AGENT_O[create_agent<br/>tools+system_prompt]
    AGENT_O --> PWO[prewarm thread<br/>~30-40s]
    PWO --> READY_O[Ready: ~30s/turno]

    DEC -->|"anthropic"| KEY{ANTHROPIC_API_KEY<br/>setada?}
    KEY -->|não| ERR[RuntimeError:<br/>API key ausente]
    KEY -->|sim| LCA[from langchain_anthropic<br/>import ChatAnthropic]
    LCA --> CFGA[ChatAnthropic com<br/>max_tokens=512]
    CFGA --> AGENT_A[create_agent<br/>tools+system_prompt]
    AGENT_A --> SKIP[prewarm SKIP<br/>cloud não tem cold start]
    SKIP --> READY_A[Ready: ~3s/turno]

    style LCO fill:#9ef,stroke:#06c
    style READY_O fill:#9ef,stroke:#06c
    style LCA fill:#fec,stroke:#c80
    style READY_A fill:#fec,stroke:#c80
    style ERR fill:#f99,stroke:#900
```

**Mensagem-chave:** o `executor` (criado por `create_agent`) tem a mesma interface independente do provider. As tools, o guardrail, o frontend, o cardápio — nada disso muda. Trocar de Ollama pra Anthropic é literalmente uma env var + rebuild do backend.

---

## 9. Lifecycle do backend (prewarm e reprewarm)

```mermaid
sequenceDiagram
    participant Docker
    participant FastAPI
    participant Lifespan
    participant Thread as Thread daemon
    participant Ollama
    participant User

    Docker->>FastAPI: container start
    FastAPI->>Lifespan: yield "startup"
    Lifespan->>Thread: dispara prewarm() em bg
    Thread->>Ollama: invoke(SYSTEM + tools + "oi")
    Note over Thread,Ollama: ~30-40s, popula KV cache
    FastAPI-->>Docker: healthcheck OK<br/>(não bloqueia!)
    Ollama-->>Thread: resposta dummy
    Thread->>FastAPI: log "PREWARM done"

    User->>FastAPI: POST /chat ("Sou vegetariano…")
    Note over FastAPI,Ollama: 1ª request real<br/>aproveita KV cache
    FastAPI-->>User: resposta em ~5s (cache hit)

    User->>User: conversa por alguns turnos<br/>(KV cache vai mudando)

    User->>FastAPI: clica "Nova Conversa"
    FastAPI->>FastAPI: DELETE /chat/{id}
    FastAPI->>Thread: dispara prewarm() de novo
    Note over Thread: roda em paralelo<br/>enquanto user pensa
    User->>FastAPI: POST /chat (próxima pergunta)
    Note over FastAPI: cache já está quente<br/>~5s de novo
```

**Pontos:**
- **prewarm no startup**: thread daemon, não bloqueia healthcheck do Docker
- **reprewarm no DELETE**: aproveita o intervalo humano (5–10s pensando) pra esquentar o cache
- **Para Anthropic**: prewarm é skipped (`PREWARM skipped | provider=anthropic`)

---

## 10. Pipeline de observabilidade (logs estruturados)

```mermaid
flowchart LR
    subgraph SETUP["Setup (startup)"]
        SL[logging_config.py<br/>setup_logging]
    end

    subgraph LIFECYCLE["Por request"]
        REQ[REQ START<br/>chat.py]
        GR[GUARDRAIL<br/>chat.py]
        AS[AGENT START<br/>chat.py]
        L1[LLM #1 START/END<br/>callback]
        TL[TOOL START/END<br/>callback]
        L2[LLM #2 START/END<br/>callback]
        END[REQ END<br/>chat.py]
        HR[HTTP RESP<br/>middleware]
    end

    SL --> REQ
    REQ --> GR
    GR --> AS
    AS --> L1
    L1 --> TL
    TL --> L2
    L2 --> END
    END --> HR

    style L1 fill:#fec
    style L2 fill:#fec
    style TL fill:#9ef
```

**Output típico:**

```
20:39:55.171 | chat   | REQ START   | session=user_xyz | msg='...'
20:39:55.171 | chat   | +0.00s | GUARDRAIL  | in_scope=True
20:39:55.180 | agent  | +0.01s | LLM #1 START   | chars_in=2634
20:39:56.948 | agent  | +1.78s | LLM #1 END     | dur=1.77s
20:39:56.949 | agent  | +1.78s | TOOL START      | name=filtrar_pratos
20:39:56.950 | agent  | +1.78s | TOOL END        | dur=0.00s
20:39:56.958 | agent  | +1.79s | LLM #2 START
20:39:59.100 | agent  | +3.93s | LLM #2 END     | dur=2.14s
20:39:59.100 | chat   | +3.93s | REQ END    | total=3.93s
20:39:59.101 | api    | HTTP RESP   | total_handler_ms=3930
```

Cada linha responde uma pergunta diferente: "onde foi o tempo?", "qual tool foi chamada?", "o LLM falhou?", "houve gap entre LLM terminar e HTTP responder?".

---

## 11. Resumo: o que cada arquivo faz

```mermaid
mindmap
  root((Lia))
    Backend
      main.py
        FastAPI + CORS
        lifespan + middleware timing
      chat.py
        orquestra guardrail+agent+memória
        logs por etapa
      guardrail.py
        keywords + LLM classificador
        adapter dual provider
      agent.py
        create_agent LangChain
        adapter Ollama vs Anthropic
        prewarm contextual
      agent_callbacks.py
        BaseCallbackHandler
        timing por LLM/tool
      logging_config.py
        setup centralizado de logs
      tools.py
        4 tools - CSV string args
      cardapio.py
        loader + filtros Python
      prompts.py
        system prompts (3 ramos)
      sessions.py
        memória WINDOW_SIZE=6
      models.py
        Pydantic schemas
      data/cardapio.json
        5 dias x 5 pratos
    Frontend
      Chat.jsx
        UI do chat
        Nova Conversa gera novo id
      api.js
        cliente HTTP
      styles.css
      nginx.conf
        proxy /api/ -> backend
    Infra
      docker-compose.yml
        4 services
        env vars LLM_PROVIDER ANTHROPIC_API_KEY
        portas 5273/8765/11534
        restart no
      Dockerfiles
        backend + frontend
      .env.example
        provider toggle
        OLLAMA + ANTHROPIC configs
        portas
```

---

## Como usar este documento na videoaula

| Bloco do roteiro | Diagrama recomendado |
|---|---|
| **2 — Stack** | #1 (visão de alto nível com adapter dual) |
| **5 — Tools** | #3 (loop do agent), #5 (anatomia da tool) |
| **6 — Guardrail** | #4 (duas camadas) |
| **7 — Observabilidade** | #10 (pipeline de logs) |
| **8 — Frontend HTTP** | #2 (sequência completa) |
| **9 — Docker** | #7 (ordem dos containers), #9 (lifecycle prewarm) |
| **10 — Local vs Cloud** | #8 (adapter dual de provider) |
| **Recap final** | #11 (mindmap dos arquivos) |

> **Dica:** se for gravar a tela do Mermaid renderizando ao vivo (no VS Code com a extensão Markdown Preview Mermaid Support), gera um efeito de "ah, então é isso que cada arquivo faz" muito mais forte do que slide estático.
