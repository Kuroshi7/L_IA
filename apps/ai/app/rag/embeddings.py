"""Adapter de embeddings (espelha o adapter de LLM).

Default: Ollama com `nomic-embed-text` (768 dim, local). Trocar de modelo exige
ajustar a dimensão da coluna `embeddings.embedding` na migração.
"""

import logging

from app import config

log = logging.getLogger("embeddings")

_backend = None


def _get_backend():
    global _backend
    if _backend is not None:
        return _backend
    if config.EMBED_PROVIDER == "ollama":
        from langchain_ollama import OllamaEmbeddings

        _backend = OllamaEmbeddings(model=config.EMBED_MODEL, base_url=config.OLLAMA_BASE_URL)
    else:
        raise RuntimeError(f"EMBED_PROVIDER não suportado: {config.EMBED_PROVIDER}")
    return _backend


def embed_documents(texts: list[str]) -> list[list[float]]:
    return _get_backend().embed_documents(texts)


def embed_query(text: str) -> list[float]:
    return _get_backend().embed_query(text)


def to_pgvector(vec: list[float]) -> str:
    """Serializa um vetor no formato aceito pelo cast ::vector do pgvector."""
    return "[" + ",".join(f"{x:.6f}" for x in vec) + "]"
