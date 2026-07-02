-- Menu-AI — Consumo, gamificação e desperdício (regras §5, §6 e §4 de docs/regras-de-negocio.md).
--
-- Desperdício segue a metodologia de UAN adaptada ao auto-relato digital:
-- o usuário reporta o que consumiu e (opcionalmente) o que deixou no prato.
-- Índice de resto-ingesta proxy = resto / (consumido + resto), com faixas de
-- referência da literatura (Teixeira 1990 / Vaz 2006): ≤3% ótimo, ≤10% bom,
-- ≤15% atenção, >15% crítico. "Prato limpo" espelha o critério FNDE (consumo ≥90%).

-- Usuário: vínculo com o Telegram e updated_at.
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS telegram_chat_id BIGINT UNIQUE;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Consumo: nutrientes totais, meta da refeição no momento do registro (snapshot),
-- resto (o que ficou no prato) e pontos atribuídos.
ALTER TABLE consumos ADD COLUMN IF NOT EXISTS sessao_id UUID REFERENCES sessoes(id) ON DELETE SET NULL;
ALTER TABLE consumos ADD COLUMN IF NOT EXISTS refeicao TEXT NOT NULL DEFAULT 'almoco';
ALTER TABLE consumos ADD COLUMN IF NOT EXISTS gramas_estimadas NUMERIC(8,2);
ALTER TABLE consumos ADD COLUMN IF NOT EXISTS proteina_g NUMERIC(7,2);
ALTER TABLE consumos ADD COLUMN IF NOT EXISTS carboidrato_g NUMERIC(7,2);
ALTER TABLE consumos ADD COLUMN IF NOT EXISTS gordura_g NUMERIC(7,2);
ALTER TABLE consumos ADD COLUMN IF NOT EXISTS meta_kcal_refeicao INT;
ALTER TABLE consumos ADD COLUMN IF NOT EXISTS resto_itens JSONB NOT NULL DEFAULT '[]';
ALTER TABLE consumos ADD COLUMN IF NOT EXISTS resto_g NUMERIC(8,2) NOT NULL DEFAULT 0;
ALTER TABLE consumos ADD COLUMN IF NOT EXISTS resto_kcal NUMERIC(8,2) NOT NULL DEFAULT 0;
ALTER TABLE consumos ADD COLUMN IF NOT EXISTS pontos INT NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS idx_consumos_unidade_data ON consumos(unidade_id, created_at);
CREATE INDEX IF NOT EXISTS idx_consumos_usuario ON consumos(usuario_id, created_at);

-- Gamificação: streak de dias consecutivos com registro.
ALTER TABLE gamificacao ADD COLUMN IF NOT EXISTS streak_dias INT NOT NULL DEFAULT 0;
ALTER TABLE gamificacao ADD COLUMN IF NOT EXISTS ultimo_registro DATE;

-- Agregado diário de desperdício por unidade — mantido pelo worker Go (ETL:
-- outbox → RabbitMQ → consumer idempotente). Leitura rápida para o dashboard admin.
CREATE TABLE IF NOT EXISTS desperdicio_diario (
    unidade_id      BIGINT NOT NULL REFERENCES unidades(id) ON DELETE CASCADE,
    data            DATE NOT NULL,
    refeicoes       INT NOT NULL DEFAULT 0,
    consumido_g     NUMERIC(12,2) NOT NULL DEFAULT 0,
    consumido_kcal  NUMERIC(12,2) NOT NULL DEFAULT 0,
    resto_g         NUMERIC(12,2) NOT NULL DEFAULT 0,
    resto_kcal      NUMERIC(12,2) NOT NULL DEFAULT 0,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (unidade_id, data)
);
