# LangChain vs LangGraph — guia de decisão

> Este documento responde: "qual desses dois eu uso pro meu projeto?". Resposta curta: **comece com LangChain. Migre pra LangGraph quando o fluxo deixar de caber numa linha reta.**

---

## TL;DR

| Pergunta | LangChain | LangGraph |
|---|---|---|
| O que é? | Framework de "cola" entre LLM, tools, memória, prompts | Framework para **grafos de estado** com múltiplos nós/agentes |
| Modelo mental | "Pipeline / agent loop" | "Máquina de estados / workflow" |
| Caso clássico | Chatbot com tools, RAG, agent simples | Multi-agente, loops com aprovação humana, retry com backoff inteligente |
| Curva de aprendizado | Suave | Mais íngreme (precisa pensar em estado, edges, checkpoints) |
| Quando NÃO usar | Workflow com 5+ ramificações condicionais | Chatbot simples — vira over-engineering |

**Para a Lia (este projeto): LangChain basta.** Justificativa abaixo.

---

## Como cada um pensa

### LangChain — o "agent loop"

Modelo mental: o LLM é o motorista. Você dá ferramentas (tools). Ele decide qual usar, vê o resultado, decide a próxima ação ou responde.

```
┌─────────────────────────────────────────┐
│         create_agent(llm, tools)        │
└──────────────────┬──────────────────────┘
                   │
        ┌──────────▼──────────┐
        │  Mensagem chega     │
        └──────────┬──────────┘
                   │
        ┌──────────▼──────────┐
        │   LLM decide:       │
        │   tool ou resposta? │◄─────┐
        └─────┬──────────┬────┘      │
              │          │           │
         tool │          │ resposta  │
              ▼          ▼           │
       ┌──────────┐  ┌────────┐      │
       │  exec    │  │ FIM    │      │
       │  tool    │──┴────────┘      │
       └────┬─────┘                  │
            └────── resultado ───────┘
```

**O que LangChain te dá grátis:**
- Adapter pra dezenas de LLMs (`ChatOllama`, `ChatOpenAI`, `ChatAnthropic`, ...)
- Decorator `@tool` que vira schema JSON automático
- Mensagens padronizadas (`HumanMessage`, `AIMessage`, `ToolMessage`, `SystemMessage`)
- Memória (`InMemoryChatMessageHistory` e variantes persistidas)
- Retrievers pra RAG, parsers, splitters de documento, etc.

**Limite:** o "loop" é uma caixa preta. Difícil interromper, ramificar com regra customizada, ou ter dois LLMs colaborando.

### LangGraph — o "grafo de estado"

Modelo mental: você desenha um grafo. Cada nó é uma função (pode chamar LLM, pode rodar Python puro). Cada aresta é uma transição condicional. Há um **estado compartilhado** que cada nó lê/escreve.

```
              ┌─────────┐
              │  START  │
              └────┬────┘
                   │
                   ▼
            ┌─────────────┐
            │  classifica │
            └──┬───────┬──┘
       é venda│       │ é suporte
              ▼       ▼
       ┌──────────┐ ┌──────────┐
       │  agente_ │ │ agente_  │
       │  vendas  │ │ suporte  │
       └────┬─────┘ └─────┬────┘
            │             │
            └──────┬──────┘
                   ▼
            ┌─────────────┐
            │  precisa    │
            │  humano?    │◄─────┐
            └──┬───────┬──┘      │
               │       │         │
            sim│       │não      │
               ▼       ▼         │
        ┌─────────┐  ┌────────┐  │
        │ pause + │  │  FIM   │  │
        │ aguarda │  └────────┘  │
        └────┬────┘               │
             │                    │
             └────── retorno ─────┘
```

**O que LangGraph te dá além do LangChain:**
- **Estado tipado** (`TypedDict` ou Pydantic) compartilhado entre nós
- **Edges condicionais**: você decide com código a próxima transição
- **Checkpoints**: pausar o grafo, salvar estado, retomar depois (human-in-the-loop)
- **Multi-agente**: orquestrar vários LLMs cooperando
- **Streaming nó a nó**: ver o que está acontecendo em cada passo
- **Visualização** automática do grafo (debug visual)

**Custo:** mais código pra subir o mais simples. "Um agent" em LangGraph é mais verboso que `create_agent`.

---

## Tabela de decisão (use esta!)

Para cada pergunta, marque uma coluna. Maioria de **A** = LangChain. Maioria de **B** = LangGraph.

| Pergunta | A (LangChain) | B (LangGraph) |
|---|---|---|
| Quantos LLMs colaboram? | 1 | 2+ |
| Quantos passos típicos? | 1–3 | 4+ |
| Tem ramificação condicional não-trivial? | Não | Sim |
| Precisa pausar e retomar a execução? | Não | Sim |
| Precisa de aprovação humana no meio? | Não | Sim |
| Precisa de retry/loop com lógica customizada? | Não, o agent loop basta | Sim |
| Precisa visualizar o workflow pra stakeholders? | Não | Sim |
| Você já entendeu LangChain bem? | Tanto faz | Sim (LangGraph espera familiaridade) |

---

## Casos reais — qual escolheria?

### ✅ LangChain

1. **Chatbot de FAQ com RAG** — busca docs, monta contexto, responde. Linear.
2. **Lia (este projeto)** — pergunta → tool determinística → resposta. 1 LLM, ciclo curto.
3. **Resumidor de e-mails** — recebe texto, chama LLM, devolve resumo. Quase nem precisa de framework.
4. **Agent com 4 tools** — LLM decide qual usar, mas o fluxo é sempre "decidir tool → executar → responder".

### ✅ LangGraph

1. **Atendimento que classifica e roteia** — primeiro classifica (suporte/vendas/cancelamento), cada rota é um sub-agente especializado.
2. **Aprovação de gastos com humano** — agente sugere → usuário aprova/rejeita → agente executa ou volta. Precisa pausar.
3. **Pipeline de pesquisa** — agente A faz busca → agente B avalia relevância → agente C resume → agente D revisa → publica.
4. **Code review automatizado** — analisa diff → roda testes → se falha, agente conserta → re-roda → se ok, abre PR.

### 🤔 Caso de fronteira

> "Tenho um chatbot de cardápio, mas quero adicionar um agente que, ao final, **confirma o pedido** com o usuário e gera um PDF."

- **LangChain**: dá pra fazer encadeando manualmente, vira espaguete com 3+ ifs.
- **LangGraph**: encaixa naturalmente — nós `recomendar`, `confirmar`, `gerar_pdf`, com transição condicional baseada na resposta do usuário.

Migrar quando dá esse tipo de "puxadinho" é o sinal certo.

---

## Como migrar da Lia (LangChain) para LangGraph — exemplo

### Hoje (LangChain)

```python
# backend/agent.py
from langchain.agents import create_agent
from langchain_ollama import ChatOllama

executor = create_agent(
    model=ChatOllama(model="llama3.2"),
    tools=TOOLS,
    system_prompt=SYSTEM_AGENT,
)

# backend/chat.py
resultado = executor.invoke({"messages": messages})
```

### Equivalente em LangGraph (esqueleto)

```python
from typing import TypedDict, Annotated
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from langchain_ollama import ChatOllama
from langchain_core.messages import SystemMessage

class State(TypedDict):
    messages: Annotated[list, add_messages]

llm = ChatOllama(model="llama3.2").bind_tools(TOOLS)

def chamar_llm(state: State):
    msgs = [SystemMessage(content=SYSTEM_AGENT)] + state["messages"]
    return {"messages": [llm.invoke(msgs)]}

def precisa_tool(state: State):
    return "tools" if state["messages"][-1].tool_calls else END

graph = StateGraph(State)
graph.add_node("llm", chamar_llm)
graph.add_node("tools", ToolNode(TOOLS))
graph.set_entry_point("llm")
graph.add_conditional_edges("llm", precisa_tool)
graph.add_edge("tools", "llm")
executor = graph.compile()
```

**Repare:**
- Mais verboso (~3x linhas).
- Mas agora você **vê** o fluxo. Se quiser inserir um nó `validar_recomendacao` antes do END, é uma linha.
- Se quiser checkpoint pra pausar e pedir confirmação humana, `graph.compile(checkpointer=SqliteSaver(...))` e pronto.

---

## Sinais de que é hora de migrar

- 🚨 Você tem `if/else` aninhado dentro do orquestrador decidindo qual agent chamar.
- 🚨 Você criou um "super tool" que faz 3 coisas porque uma tool sozinha não bastaria.
- 🚨 Você precisa de "memória de longo prazo" estruturada (não só janela de mensagens).
- 🚨 Quer pausar o agent no meio, mostrar pro usuário, esperar input.
- 🚨 Quer mostrar pro time não-técnico o "fluxo" do bot — diagrama vale mais que código.
- 🚨 Quer que dois agentes (com prompts e tools diferentes) conversem entre si.

Sem nenhum desses sinais? **Não migre. LangChain é mais simples e suficiente.**

---

## Mitos comuns

| Mito | Realidade |
|---|---|
| "LangGraph substitui LangChain" | Não. LangGraph é construído **sobre** LangChain (usa `BaseMessage`, tools, LLMs do LangChain). É uma camada acima. |
| "Time profissa usa LangGraph, LangChain é hobby" | Errado. A escolha é por **complexidade do fluxo**, não maturidade do time. |
| "LangGraph é mais lento" | Praticamente igual. O custo é nos LLMs, não no framework. |
| "Migrar depois é dor" | Tem fricção, mas se você isolou as tools (como nós fizemos em `tools.py`), o investimento é localizado em `agent.py` + `chat.py`. |
| "LangChain está morrendo, todo mundo vai pra LangGraph" | Os dois são da mesma empresa (LangChain Inc) e mantidos juntos. LangChain 1.x e LangGraph evoluem em paralelo. |

---

## Para a videoaula — resumo de bolso

> "LangChain é o **agent loop padrão**: LLM → tool → LLM → resposta.
> LangGraph é o **workflow customizável**: você desenha um grafo de estados.
> Comece com LangChain. Migre pra LangGraph quando o `create_agent` deixar de caber no seu problema —
> sinais: múltiplos agentes, ramificação condicional, human-in-the-loop, checkpoint."

---

## Referências

- [LangChain docs](https://python.langchain.com/) — `create_agent`, tools, mensagens
- [LangGraph docs](https://langchain-ai.github.io/langgraph/) — grafos, checkpoints, ToolNode
- [LangGraph: When to use it](https://blog.langchain.dev/langgraph/) — artigo dos próprios autores

---

## Revisão de 24/08/2026 — evidência do Onyx

Lemos o código do Onyx (clone em `~/desenvolvimento/onyx`) procurando o que faz
o agente deles se comportar bem. Achado que muda o enquadramento deste
documento: **o Onyx não usa LangChain nem LangGraph.** O laço agentic é

```python
for llm_cycle_count in range(MAX_LLM_CYCLES):   # chat/llm_loop.py
```

um `for` sobre o litellm, com corte de histórico e orçamento de tokens escritos
à mão. Um produto maduro escolheu **não** usar framework de grafo.

### A dicotomia é falsa, e o eixo real é outro

Chain e graph não competem: um nó de grafo pode ser uma chain. A pergunta que
decide o desenho é **quem precisa estar certo — o modelo ou o código?**

| obrigação | onde vive | por quê |
|---|---|---|
| Sempre acontece (aviso legal, guardrail, validação) | **código** | "quase sempre" não serve |
| Precisa de julgamento (qual tool, como frasear) | **laço agentic** | entrada aberta demais para regra |

Este projeto já está certo nesse eixo, e não por teoria: pedir ao prompt o aviso
obrigatório deu **0 de 3** de aderência mesmo com reminder reinjetado. Por isso
`pos_processar` e `regras` são código, e a escolha de tool é do modelo.

### Decisão: ficar com `create_agent`, e o gatilho para revisar

**Mantido.** O motor tem ~4.100 linhas porque não escrevemos o laço; trocar
agora pagaria caro por controle que ainda não usamos.

**Revisar quando aparecer o terceiro remendo em volta do framework.** Hoje há
um: `motor/tools.py` existe porque o `create_agent` não trata erro de tool
(medido — a exceção aborta o grafo inteiro). Os outros dois módulos criados no
mesmo dia, `motor/erros.py` e `motor/preflight.py`, **não** são remendos:
existiriam com qualquer laço.

Candidatos a virar o terceiro: corte de histórico por orçamento de tokens,
retry por ciclo, streaming parcial. Se dois destes aparecerem, escrever o `for`
fica mais barato que continuar contornando.

A troca é barata porque a costura é uma função só: `construir_executor`, em
`motor/llm.py`. Trocar o laço não toca em nenhuma linha de domínio.
