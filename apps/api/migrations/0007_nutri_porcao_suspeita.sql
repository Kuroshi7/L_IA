-- Sinalização de porções nutricionalmente implausíveis.
--
-- Motivação (medido em 2026-08-23): "Arroz Integral Cozido" está na base com
-- 257 kcal e 46 g de carboidrato por 100 g, contra 164 kcal e 32 g do "Arroz
-- Branco Cozido" (fonte IBGE). Arroz cozido é ~70% água; 46 g de carboidrato
-- por 100 g é valor de produto seco. O agente entregava esse número com
-- `confianca: "alta"`, porque a confiança media a certeza do CASAMENTO do nome,
-- nunca a plausibilidade do DADO.
--
-- A base é internamente consistente (cruzamento de Atwater: 0 de 346 porções
-- desviam mais de 15%) e bate dígito a dígito com a página 7 do PDF-fonte: não
-- é erro de transcrição, é o valor da fonte primária. A TACO traz 123,5 kcal
-- para o mesmo alimento. Corrigir o número sem medição própria seria trocar um
-- palpite por outro; o que dá para fazer é PARAR DE AFIRMÁ-LO COM CERTEZA.
--
-- Esta migração é a checagem determinística, independente de fonte externa.
-- O cruzamento com a TACO fica em `app.nutrition.auditoria`, que marca a mesma
-- coluna e cobre casos que a heurística de densidade não pega.
--
-- Duas regras determinísticas, escolhidas por precisão e não por cobertura:
--   A) preparação hidratada (cozido/refogado/ensopado/sopa/caldo/purê/guisado)
--      com soma de macros > 45 g/100 g — deveria ser majoritariamente água;
--   B) qualquer porção com soma de macros > 95 g/100 g — sobra pouco ou nada
--      para água, o que é fisicamente improvável em alimento preparado.
--
-- Na base atual: 6 porções pela regra A (Arroz Integral Cozido, Costela de
-- Porco Cozida) e 3 pela regra B (Farofa). Ruído baixo o suficiente para uma
-- nutricionista revisar uma a uma.
ALTER TABLE nutri_porcoes
    ADD COLUMN IF NOT EXISTS suspeito BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN nutri_porcoes.suspeito IS
    'Valor implausível segundo checagem determinística; rebaixa a confiança do cálculo até revisão.';

UPDATE nutri_porcoes p
   SET suspeito = true
  FROM nutri_alimentos a
 WHERE a.id = p.alimento_id
   AND p.quantidade_g > 0
   AND (
        (a.nome_norm ~ '(cozid|refogad|ensopad|sopa|caldo|pure|guisad)'
         AND (COALESCE(p.proteina_g,0)+COALESCE(p.carboidrato_g,0)+COALESCE(p.gordura_g,0))
             * 100.0 / p.quantidade_g > 45)
     OR ((COALESCE(p.proteina_g,0)+COALESCE(p.carboidrato_g,0)+COALESCE(p.gordura_g,0))
             * 100.0 / p.quantidade_g > 95)
       );

CREATE INDEX IF NOT EXISTS idx_nutri_porcoes_suspeito
    ON nutri_porcoes (suspeito) WHERE suspeito;
