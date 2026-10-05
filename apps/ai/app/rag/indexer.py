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
        sem_vetor = 0
        for guia_id, unidade_id, titulo, conteudo in guias:
            pedacos = chunking.chunk(f"{titulo}\n\n{conteudo}")
            if not pedacos:
                continue
            # Sem embedder (ex.: deploy só com Anthropic, que não tem embeddings),
            # o trecho entra com vetor NULL: o retriever já cai no full-text, e
            # abortar aqui deixaria o RAG sem nada para buscar.
            try:
                vetores = [emb.to_pgvector(v) for v in emb.embed_documents(pedacos)]
            except Exception as e:
                log.warning("embeddings indisponíveis (%s) — indexando só para full-text", type(e).__name__)
                vetores = [None] * len(pedacos)
                sem_vetor += len(pedacos)
            for i, (texto, vec) in enumerate(zip(pedacos, vetores)):
                cur.execute(
                    """
                    INSERT INTO embeddings (guia_id, unidade_id, chunk_index, chunk, embedding)
                    VALUES (%s, %s, %s, %s, %s::vector)
                    """,
                    (guia_id, unidade_id, i, texto, vec),
                )
                total += 1
        conn.commit()
        log.info("indexação concluída | chunks=%d | sem_vetor=%d | guias=%d", total, sem_vetor, len(guias))


if __name__ == "__main__":
    setup_logging()
    reindexar()
