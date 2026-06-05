-- Base nutricional de referência (medidas caseiras) — fonte estruturada para o
-- motor de consumo/gamificação. Dados extraídos da "Tabela para Avaliação de
-- Consumo Alimentar em Medidas Caseiras" (Atheneu, 4ª ed.) + IBGE/GF.
--
-- Princípio: Postgres é a fonte da verdade do CÁLCULO. A LLM apenas interpreta a
-- linguagem natural; os números (g/kcal/macros) vêm daqui.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Legenda de medidas (pág. 2 do livro) + apelidos/gírias para resolução fuzzy.
-- Ex.: "COL S CH" → "colher de sopa cheia"; "conchinha" → CO (concha) tamanho P.
CREATE TABLE medida_aliases (
    alias       TEXT PRIMARY KEY,   -- normalizado (minúsculo, sem acento)
    medida_cod  TEXT NOT NULL,      -- código canônico, ex: "CO", "COL S", "PT F"
    descricao   TEXT NOT NULL       -- ex: "concha", "colher de sopa", "prato fundo"
);
CREATE INDEX idx_medida_aliases_trgm ON medida_aliases USING gin (alias gin_trgm_ops);

-- Alimento de referência (independente do cardápio das unidades).
CREATE TABLE nutri_alimentos (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nome        TEXT NOT NULL,
    nome_norm   TEXT NOT NULL,          -- minúsculo, sem acento (para busca)
    categoria   TEXT,
    fonte       TEXT,                   -- IBGE | GF | FCNT | FP | I | *
    aliases     TEXT[] NOT NULL DEFAULT '{}',
    UNIQUE (nome_norm)
);
CREATE INDEX idx_nutri_alimentos_trgm ON nutri_alimentos USING gin (nome_norm gin_trgm_ops);
CREATE INDEX idx_nutri_alimentos_aliases ON nutri_alimentos USING gin (aliases);

-- Porções por medida caseira, com nutrientes já calculados para aquela quantidade.
CREATE TABLE nutri_porcoes (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    alimento_id     BIGINT NOT NULL REFERENCES nutri_alimentos(id) ON DELETE CASCADE,
    medida_label    TEXT NOT NULL,      -- rótulo cru da tabela, ex: "COL S CH PICADO"
    medida_cod      TEXT,               -- código canônico resolvido, ex: "COL S"
    tamanho         TEXT,               -- P | M | G | GG | D (quando aplicável)
    estado          TEXT,               -- CH (cheio) | N (nivelado) | R (raso)
    quantidade_g    NUMERIC(8,2) NOT NULL,
    kcal            NUMERIC(8,2),
    proteina_g      NUMERIC(7,2),
    carboidrato_g   NUMERIC(7,2),
    gordura_g       NUMERIC(7,2),
    calcio_mg       NUMERIC(8,2),
    ferro_mg        NUMERIC(7,2),
    vit_c_mg        NUMERIC(8,2),
    vit_a_ug        NUMERIC(9,2),
    UNIQUE (alimento_id, medida_label)
);
CREATE INDEX idx_nutri_porcoes_alimento ON nutri_porcoes(alimento_id);
