"""Configuração central do serviço de IA, lida de variáveis de ambiente."""

import os

from dotenv import load_dotenv

load_dotenv()

# LLM provider
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower().strip()
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")
# OpenRouter: endpoint compatível com a OpenAI que revende dezenas de modelos,
# incluindo alguns gratuitos. Serve para medir o mesmo eval em outro modelo sem
# tocar no código — o que o harness já permitia e nenhum provider exercitava.
OPENROUTER_BASE_URL = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free")

# Limites do LLM. O pior caso de UMA chamada é LLM_TIMEOUT_SECONDS × (LLM_MAX_RETRIES+1)
# e precisa caber no CHAT_TIMEOUT_SECONDS do Go (default 60s), senão o Go desiste antes,
# devolve 502 e o worker segue queimando uma resposta que ninguém lê. Com 45s × 2 =
# 90s isso era violado; 45s × (1+1) mantém 1 retentativa útil (para 429/rede) sem
# estourar o orçamento numa única chamada.
# NOTA: um turno pode fazer VÁRIAS chamadas (recursion_limit), então o orçamento total
# ainda pode ser excedido. A proteção para quem espera é a expiração da fila
# (REQUEST_MAX_AGE_SECONDS) + réplicas do worker. O fix completo — propagar o deadline
# absoluto do Go por requisição e abortar quando esgotar — está no follow-up (ver PR).
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "45"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "1"))
# Resposta completa = cardápio inteiro + recomendação + porções; 512 truncava.
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "1024"))
# Prefill mínimo do agente ≈ 2.5k tokens (system + schemas das 10 tools); 2048
# truncava o system prompt silenciosamente no Ollama.
OLLAMA_NUM_CTX = int(os.getenv("OLLAMA_NUM_CTX", "8192"))
# Teto de passos do grafo do agente (cada tool call = 2 passos). 12 ≈ 5 tool calls
# por turno — acima disso é loop, não conversa.
AGENT_RECURSION_LIMIT = int(os.getenv("AGENT_RECURSION_LIMIT", "12"))
# Mensagem mais velha que isso na fila é descartada sem processar: quem pediu já
# recebeu 502 do Go e não está mais esperando a resposta.
REQUEST_MAX_AGE_SECONDS = int(os.getenv("REQUEST_MAX_AGE_SECONDS", os.getenv("CHAT_TIMEOUT_SECONDS", "60")))

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

# --- Validação pós-resposta -------------------------------------------------
# Ids de regra que BLOQUEIAM a resposta (CSV). Vazio = todas apenas registram em
# log. O default é log-only de propósito: bloquear sem poder REPARAR troca uma
# resposta provavelmente boa por uma mensagem de erro, e reparar exigiria mais
# uma chamada de modelo dentro de um orçamento de 60s. Promover uma regra só
# depois de medir a taxa de falso positivo nos logs `VALIDACAO | regra=`.
# R5 nasce bloqueante, sozinha. É a única regra 100% estrutural (o conflito vem
# anotado no prato, calculado em código a partir do perfil) e a única cujo erro
# pode mandar alguém para o hospital. Nas demais, bloquear trocaria uma resposta
# provavelmente boa por uma mensagem de erro — aqui, deixar passar é pior.
VALIDACAO_BLOQUEANTE = frozenset(
    r.strip() for r in os.getenv(
        "VALIDACAO_BLOQUEANTE", "R5-prato-conflita-com-perfil"
    ).split(",") if r.strip()
)

# Repetição exata de tool (mesmo nome, mesmos argumentos) devolve um marcador em
# vez do corpo. Kill-switch para desligar em produção sem deploy caso um modelo
# pequeno se confunda com o marcador.
COMPRIMIR_REPETICOES = os.getenv("COMPRIMIR_REPETICOES", "1").lower() not in ("0", "false", "nao", "no")
