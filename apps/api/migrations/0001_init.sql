-- Menu-AI — schema inicial (Fase 1: fundação).
-- Go é a fonte da verdade. pgvector usado para RAG (populado pelo serviço Python).

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto; -- gen_random_uuid()

-- ----------------------------------------------------------------------------
-- Domínio
-- ----------------------------------------------------------------------------
CREATE TABLE unidades (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    ativo       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE usuarios (
    id               BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    unidade_id       BIGINT REFERENCES unidades(id) ON DELETE SET NULL,
    nome             TEXT NOT NULL,
    peso_kg          NUMERIC(5,2),
    altura_cm        NUMERIC(5,2),
    idade            INT,
    sexo             TEXT CHECK (sexo IN ('M','F','O')),
    nivel_atividade  TEXT CHECK (nivel_atividade IN ('sedentario','leve','moderado','intenso','muito_intenso')),
    restricoes       TEXT[] NOT NULL DEFAULT '{}',
    preferencias     TEXT[] NOT NULL DEFAULT '{}',
    alergias         TEXT[] NOT NULL DEFAULT '{}',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Base de pratos/alimentos (cadastrada pelo admin), por unidade.
CREATE TABLE alimentos (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    unidade_id          BIGINT NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    nome                TEXT NOT NULL,
    categoria           TEXT,
    ingredientes        TEXT[] NOT NULL DEFAULT '{}',
    alergenos           TEXT[] NOT NULL DEFAULT '{}',
    restricoes_atendidas TEXT[] NOT NULL DEFAULT '{}',
    nao_indicado_para   TEXT[] NOT NULL DEFAULT '{}',
    calorias            INT,
    proteinas_g         NUMERIC(6,2),
    carboidratos_g      NUMERIC(6,2),
    gorduras_g          NUMERIC(6,2),
    ativo               BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_alimentos_unidade ON alimentos(unidade_id);

-- Cardápio por dia (cada unidade tem o seu).
CREATE TABLE cardapio_dias (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    unidade_id  BIGINT NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    data        DATE NOT NULL,
    dia_semana  TEXT NOT NULL,
    UNIQUE (unidade_id, data)
);
CREATE INDEX idx_cardapio_dias_unidade_data ON cardapio_dias(unidade_id, data);

CREATE TABLE cardapio_itens (
    id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cardapio_dia_id    BIGINT NOT NULL REFERENCES cardapio_dias(id) ON DELETE CASCADE,
    alimento_id        BIGINT NOT NULL REFERENCES alimentos(id) ON DELETE CASCADE,
    is_proteina_do_dia BOOLEAN NOT NULL DEFAULT FALSE,
    UNIQUE (cardapio_dia_id, alimento_id)
);

-- Guia de medidas caseiras (referência para porções e leitura de consumo).
CREATE TABLE medidas_caseiras (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    medida      TEXT NOT NULL,         -- ex: "colher de sopa"
    alimento    TEXT NOT NULL,         -- ex: "arroz cozido"
    gramas      NUMERIC(6,2) NOT NULL,
    kcal        NUMERIC(6,2) NOT NULL,
    UNIQUE (medida, alimento)
);

-- ----------------------------------------------------------------------------
-- Sessões / memória de curto prazo
-- ----------------------------------------------------------------------------
CREATE TABLE sessoes (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    unidade_id  BIGINT NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    usuario_id  BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
    canal       TEXT NOT NULL DEFAULT 'web',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE mensagens (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sessao_id   UUID NOT NULL REFERENCES sessoes(id) ON DELETE CASCADE,
    papel       TEXT NOT NULL CHECK (papel IN ('user','assistant')),
    conteudo    TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_mensagens_sessao ON mensagens(sessao_id, created_at);

-- ----------------------------------------------------------------------------
-- Consumo / gamificação (modelado agora; feature completa em fases seguintes)
-- ----------------------------------------------------------------------------
CREATE TABLE consumos (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id      BIGINT REFERENCES usuarios(id) ON DELETE SET NULL,
    unidade_id      BIGINT NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    cardapio_dia_id BIGINT REFERENCES cardapio_dias(id) ON DELETE SET NULL,
    itens           JSONB NOT NULL DEFAULT '[]',
    kcal_estimada   NUMERIC(7,2),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE gamificacao (
    usuario_id  BIGINT PRIMARY KEY REFERENCES usuarios(id) ON DELETE CASCADE,
    pontos      INT NOT NULL DEFAULT 0,
    nivel       INT NOT NULL DEFAULT 1,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE eventos_pontuacao (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id  BIGINT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    consumo_id  BIGINT REFERENCES consumos(id) ON DELETE SET NULL,
    pontos      INT NOT NULL,
    motivo      TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- Filas / idempotência (outbox + inbox)
-- ----------------------------------------------------------------------------
CREATE TABLE outbox (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate     TEXT NOT NULL,
    event_type    TEXT NOT NULL,
    payload       JSONB NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','published','failed')),
    attempts      INT NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at  TIMESTAMPTZ
);
CREATE INDEX idx_outbox_pending ON outbox(created_at) WHERE status = 'pending';

CREATE TABLE inbox_processados (
    msg_id        TEXT PRIMARY KEY,
    consumer      TEXT NOT NULL,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE idempotency_keys (
    chave         TEXT PRIMARY KEY,
    request_hash  TEXT NOT NULL,
    status_code   INT,
    response      JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- RAG: guias e embeddings (populados pelo serviço Python)
-- ----------------------------------------------------------------------------
CREATE TABLE guias (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    unidade_id  BIGINT REFERENCES unidades(id) ON DELETE CASCADE, -- NULL = global
    tipo        TEXT NOT NULL,    -- 'medidas_caseiras' | 'nutricao' | 'faq'
    titulo      TEXT NOT NULL,
    conteudo    TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- nomic-embed-text => 768 dimensões. Ajuste a dimensão ao trocar de modelo.
CREATE TABLE embeddings (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    guia_id     BIGINT REFERENCES guias(id) ON DELETE CASCADE,
    unidade_id  BIGINT REFERENCES unidades(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    chunk       TEXT NOT NULL,
    embedding   vector(768),
    metadata    JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_embeddings_unidade ON embeddings(unidade_id);
-- HNSW (boas práticas 2026: m=16, ef_construction=64); cosine.
CREATE INDEX idx_embeddings_hnsw ON embeddings USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);
-- Full-text para busca híbrida.
ALTER TABLE embeddings ADD COLUMN chunk_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('portuguese', chunk)) STORED;
CREATE INDEX idx_embeddings_tsv ON embeddings USING gin (chunk_tsv);
