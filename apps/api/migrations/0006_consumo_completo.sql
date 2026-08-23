-- Cobertura do cálculo de consumo.
--
-- Um item que não resolve contra a base nutricional entra no registro com
-- nutrientes zerados e NÃO soma aos totais (store/nutri.go). O total resultante
-- é menor que o real, e é ele que alimenta a pontuação do usuário e o índice de
-- resto-ingesta do dashboard de desperdício.
--
-- Marcar a linha permite: (a) não pontuar sobre número incompleto, e (b) manter
-- o KPI do admin calculado só sobre refeições com cobertura total.
--
-- DEFAULT true: registros anteriores a esta migração seguem contando. Não temos
-- como saber retroativamente quais foram parciais, e assumir o contrário
-- zeraria o histórico do dashboard.
ALTER TABLE consumos
    ADD COLUMN IF NOT EXISTS completo BOOLEAN NOT NULL DEFAULT true;

-- O dashboard filtra por (unidade, período, completo); o índice acompanha.
CREATE INDEX IF NOT EXISTS idx_consumos_unidade_completo
    ON consumos (unidade_id, completo, created_at);
