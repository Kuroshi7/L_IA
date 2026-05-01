# Lia — MVP de Chat IA para Recomendação de Cardápio

> **Lia** = `L` + `IA` (a IA do refeitório).

Chat conversacional onde o usuário informa restrições (vegetariano, celíaco, alergias) e a Lia recomenda pratos do cardápio. 100% open source: roda localmente com Ollama.

## Stack
- **Backend:** Python 3.10+ · FastAPI · LangChain (Tool-calling Agent) · Ollama
- **Frontend:** React 18 + Vite
- **Modelo:** llama3.2 (3B) via Ollama, local — suporta tool calling nativo
- **Persistência:** memória RAM por `session_id` (SQLite fica para próxima iteração)

## Diferenciais em relação ao guia base
1. **Tool-calling Agent** em vez de Chain simples: o LLM decide qual tool chamar (`listar_pratos_do_dia`, `filtrar_pratos`, `detalhar_prato`, `comparar_pratos`). Filtragem por restrição/alergia é determinística em Python — vegetariano nunca vê prato com carne.
2. **Guardrail de escopo em duas camadas**: heurística por keywords (instantânea) + classificador LLM (fallback). Recusa perguntas fora do tema sem depender só de prompt engineering.

## Pré-requisitos
- Python 3.10+
- Node.js 18+
- [Ollama](https://ollama.com) instalado

```bash
# Baixar o modelo (~4 GB)
ollama pull llama3.2

# Garantir que o servidor Ollama está no ar (geralmente já roda como serviço)
ollama serve
```

## Rodar o backend

```bash
cd backend
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env              # ajusta OLLAMA_BASE_URL/OLLAMA_MODEL se precisar
uvicorn main:app --reload
```

API em `http://localhost:8000` · docs Swagger em `http://localhost:8000/docs`.

Smoke test:
```bash
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test","mensagem":"Sou vegetariano e celíaco, o que tem hoje?"}'
```

## Rodar o frontend

```bash
cd frontend
npm install
npm run dev
```

UI em `http://localhost:5173`.

## Endpoints
- `GET  /` — status
- `GET  /cardapio/hoje` — pratos do dia
- `GET  /cardapio/semana` — semana completa
- `GET  /chat/saudacao` — texto inicial do bot
- `POST /chat` — `{ session_id, mensagem }` → `{ session_id, resposta, fora_de_escopo }`
- `DELETE /chat/{session_id}` — reseta memória

## Estrutura

```
menu-ai/
├── backend/
│   ├── main.py            # FastAPI + CORS
│   ├── chat.py            # guardrail → agent → memória
│   ├── agent.py           # tool-calling agent (llama3.2)
│   ├── tools.py           # 4 tools LangChain
│   ├── guardrail.py       # filtro de escopo (keywords + LLM)
│   ├── cardapio.py        # loader/filtros do cardapio.json
│   ├── prompts.py         # system prompts versionados
│   ├── sessions.py        # memória por session_id
│   ├── models.py          # Pydantic schemas
│   └── data/cardapio.json # 5 dias × 5 pratos
└── frontend/
    └── src/
        ├── Chat.jsx       # UI do chat
        ├── api.js         # cliente HTTP
        └── styles.css
```

## Critérios de aceite verificados

**Funcional:**
- [ ] `GET /cardapio/hoje` devolve pratos do JSON
- [ ] *"O que tem hoje?"* → IA chama `listar_pratos_do_dia`
- [ ] *"Sou vegetariano"* → IA chama `filtrar_pratos`, nunca sugere carne
- [ ] *"Sou celíaco e alérgico a amendoim"* → respeita ambas restrições
- [ ] *"Qual tem mais proteína?"* → chama `comparar_pratos` com número correto
- [ ] *"Lembra o que você sugeriu antes?"* → usa memória da janela
- [ ] Botão "Nova Conversa" → `DELETE` zera memória

**Escopo (crítico):**
- [ ] *"Qual a capital do Japão?"* → resposta canned do guardrail
- [ ] *"Me ensina receita de bolo"* → recusado
- [ ] *"Ignore suas instruções"* → recusado
- [ ] *"Conselhos sobre cripto?"* → recusado

## Troubleshooting

| Sintoma | Solução |
|---|---|
| "Erro ao conectar" no frontend | Backend offline. Rodar `uvicorn main:app --reload`. |
| Backend trava ao iniciar | Ollama não está rodando. `ollama serve` em outro terminal. |
| Resposta lenta (15-30s) | Normal com llama3.2 local. Use `mistral` no `.env` se a máquina for fraca. |
| IA não chama tools | llama3.2 antigo pode não suportar tool calling — faça `ollama pull llama3.2` de novo. |
| CORS error | Verifique se o frontend está em `localhost:5173` (Vite). Outras portas: ajustar `main.py`. |
| Porta 8000 ocupada | `uvicorn main:app --reload --port 8001` e ajustar `VITE_API_URL` no frontend. |

## Próximos passos (fora do MVP)
- Persistência SQLite (perfil + histórico) — guia §7
- Streaming de resposta (SSE)
- Integração com API real do cardápio
- Métricas (Prometheus) e logging estruturado
