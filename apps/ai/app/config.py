"""Configuração central do serviço de IA, lida de variáveis de ambiente."""

import os

from dotenv import load_dotenv

load_dotenv()

# LLM provider
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower().strip()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")

# Embeddings (RAG). nomic-embed-text => 768 dimensões (bate com a coluna vector(768)).
EMBED_PROVIDER = os.getenv("EMBED_PROVIDER", "ollama").lower().strip()
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")

# Integrações
API_INTERNAL_URL = os.getenv("API_INTERNAL_URL", "http://localhost:8080")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
DATABASE_URL = os.getenv("DATABASE_URL", "postgres://menuai:menuai@localhost:5432/menuai?sslmode=disable")

# Fila consumida por este worker (deve casar com a do serviço Go).
CHAT_REQUESTS_QUEUE = os.getenv("CHAT_REQUESTS_QUEUE", "chat.requests")
PREFETCH = int(os.getenv("WORKER_PREFETCH", "1"))
