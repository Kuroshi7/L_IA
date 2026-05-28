"""Retriever híbrido sobre pgvector (vetor + full-text), com degradação graciosa.

Boas práticas aplicadas: prefiltro por unidade antes do ANN; recall via HNSW
(cosine). Se embeddings/embedder/banco não estiverem disponíveis, retorna [] para
não derrubar o agente (RAG é complementar ao dado estruturado vindo da API Go).
"""

import logging

from app import config
from app.rag import embeddings

log = logging.getLogger("retriever")


def _connect():
    import psycopg

    return psycopg.connect(config.DATABASE_URL)


def buscar(consulta: str, unidade_id: int | None = None, k: int = 4) -> list[str]:
    # 1) tenta busca vetorial
    try:
        vec = embeddings.embed_query(consulta)
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT chunk
                  FROM embeddings
                 WHERE (unidade_id = %s OR unidade_id IS NULL)
                   AND embedding IS NOT NULL
                 ORDER BY embedding <=> %s::vector
                 LIMIT %s
                """,
                (unidade_id, embeddings.to_pgvector(vec), k),
            )
            rows = [r[0] for r in cur.fetchall()]
            if rows:
                return rows
    except Exception as e:
        log.warning("busca vetorial indisponível (%s: %s) — tentando full-text", type(e).__name__, e)

    # 2) fallback: full-text
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT chunk
                  FROM embeddings
                 WHERE (unidade_id = %s OR unidade_id IS NULL)
                   AND chunk_tsv @@ plainto_tsquery('portuguese', %s)
                 LIMIT %s
                """,
                (unidade_id, consulta, k),
            )
            return [r[0] for r in cur.fetchall()]
    except Exception as e:
        log.warning("full-text indisponível (%s: %s)", type(e).__name__, e)
        return []
