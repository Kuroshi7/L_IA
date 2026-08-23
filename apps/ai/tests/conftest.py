"""Ambiente determinístico para a suíte offline.

O pytest importa este arquivo ANTES dos módulos de teste — e portanto antes de
qualquer `import app.*`. Isso é o que faz as duas garantias abaixo funcionarem:

1. `app.config` chama `load_dotenv()` no import e leria o `.env` real da máquina,
   fazendo provider, modelo e URLs variarem por desenvolvedor. `load_dotenv` não
   sobrescreve variável já presente no ambiente, então fixar aqui vence o arquivo.

2. As URLs de rede apontam para uma porta fechada de propósito. Nenhum teste
   offline deve falar com a API Go nem com o Postgres; se algum tentar, falha na
   hora com "connection refused" em vez de passar na máquina de quem está com a
   stack de pé e quebrar só no CI.

Onde usamos `setdefault` (provider/modelo), é para o workflow de eval e o uso
local com `-m llm` poderem escolher explicitamente sem editar este arquivo.
"""

import os

# Provider e modelo: default previsível, mas sobrescrevível por quem roda `-m llm`.
os.environ.setdefault("LLM_PROVIDER", "ollama")
os.environ.setdefault("OLLAMA_MODEL", "llama3.2")
os.environ.setdefault("OLLAMA_BASE_URL", "http://127.0.0.1:9")

# Rede: porta 9 (discard) fechada — falha rápida, sem timeout de DNS.
os.environ["API_INTERNAL_URL"] = "http://127.0.0.1:9"
os.environ["DATABASE_URL"] = "postgres://offline:offline@127.0.0.1:9/offline?sslmode=disable"
os.environ["RABBITMQ_URL"] = "amqp://guest:guest@127.0.0.1:9/"
