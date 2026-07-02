-- Menu-AI — Admin: catálogo de alimentos por unidade + edição de cardápio.
-- Vincula o alimento do menu à referência de medidas caseiras (nutri_alimentos),
-- e garante 1 alimento por (unidade, nome) — o catálogo do qual o cardápio é montado.

ALTER TABLE alimentos ADD COLUMN IF NOT EXISTS nutri_alimento_id BIGINT
    REFERENCES nutri_alimentos(id) ON DELETE SET NULL;
ALTER TABLE alimentos ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();

-- Deduplica alimentos pré-existentes: o seed antigo criava 1 linha por (dia × prato),
-- gerando duplicatas incoerentes com o modelo "catálogo da unidade + cardápio referencia".
-- Mantém o menor id por (unidade_id, nome), repõe as referências dos cardápios e remove o resto.

-- 1. remove itens que colidiriam após o repoint: para cada (dia, alimento canônico),
--    mantém só o item de menor id — cobre também o caso de DUAS duplicatas do mesmo
--    alimento no mesmo dia sem o canônico presente.
WITH mapa AS (
  SELECT id, MIN(id) OVER (PARTITION BY unidade_id, nome) AS keep_id FROM alimentos
),
ranqueado AS (
  SELECT ci.id AS ci_id,
         ROW_NUMBER() OVER (PARTITION BY ci.cardapio_dia_id, m.keep_id ORDER BY ci.id) AS rn
    FROM cardapio_itens ci
    JOIN mapa m ON m.id = ci.alimento_id
)
DELETE FROM cardapio_itens WHERE id IN (SELECT ci_id FROM ranqueado WHERE rn > 1);

-- 2. aponta os itens restantes para o alimento canônico.
UPDATE cardapio_itens ci
   SET alimento_id = r.keep_id
  FROM (SELECT id, MIN(id) OVER (PARTITION BY unidade_id, nome) AS keep_id FROM alimentos) r
 WHERE ci.alimento_id = r.id AND r.id <> r.keep_id;

-- 3. remove os alimentos duplicados (já sem referências).
DELETE FROM alimentos
 WHERE id IN (
   SELECT id FROM (
     SELECT id, MIN(id) OVER (PARTITION BY unidade_id, nome) AS keep_id FROM alimentos
   ) x WHERE id <> keep_id
 );

CREATE UNIQUE INDEX IF NOT EXISTS idx_alimentos_unidade_nome ON alimentos (unidade_id, nome);
