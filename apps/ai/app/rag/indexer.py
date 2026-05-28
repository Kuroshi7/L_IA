"""Indexador de RAG: lê os guias do Postgres (seedados pelo Go), faz chunking,
gera embeddings e popula a tabela `embeddings`.

Uso: python -m app.rag.indexer
Requer Ollama com o modelo de embeddings disponível e o banco acessível.
"""

import logging

from app import config
from app.logging_config import setup_logging
from app.rag import chunking, embeddings as emb

log = logging.getLogger("indexer")


def _connect():
    import psycopg

    return psycopg.connect(config.DATABASE_URL)


def reindexar() -> None:
    with _connect() as conn, conn.cursor() as cur:
        cur.execute("SELECT id, unidade_id, titulo, conteudo FROM guias")
        guias = cur.fetchall()
        if not guias:
            log.info("nenhum guia para indexar")
            return

        cur.execute("TRUNCATE embeddings")
        total = 0
        for guia_id, unidade_id, titulo, conteudo in guias:
            pedacos = chunking.chunk(f"{titulo}\n\n{conteudo}")
            if not pedacos:
                continue
            vetores = emb.embed_documents(pedacos)
            for i, (texto, vec) in enumerate(zip(pedacos, vetores)):
                cur.execute(
                    """
                    INSERT INTO embeddings (guia_id, unidade_id, chunk_index, chunk, embedding)
                    VALUES (%s, %s, %s, %s, %s::vector)
                    """,
                    (guia_id, unidade_id, i, texto, emb.to_pgvector(vec)),
                )
                total += 1
        conn.commit()
        log.info("indexação concluída | chunks=%d | guias=%d", total, len(guias))


if __name__ == "__main__":
    setup_logging()
    reindexar()
