-- A checagem da 0007 como FUNÇÃO, para rodar também depois de carga de dados.
--
-- Medido no E2E de 23/09/2026: numa instalação nova as migrações rodam no boot da
-- API, com `nutri_porcoes` ainda vazia, e o seed só carrega a base depois. O UPDATE
-- da 0007 não encontrava nada para marcar, e "Arroz Integral Cozido" (257 kcal/100 g)
-- voltava a sair com confiança alta — 4 colheres registradas como 1.028 kcal, e a
-- pontuação do usuário zerada por um número que o produto já sabia ser implausível.
--
-- As regras são as mesmas da 0007 (ver lá o porquê de cada uma). Idempotente: só
-- liga o flag, nunca desliga. Consequência: revisão que desmarca a linha SEM
-- corrigir o número é desfeita na próxima carga — revisar é corrigir o valor.
CREATE OR REPLACE FUNCTION marcar_porcoes_suspeitas() RETURNS integer
LANGUAGE sql AS $$
    WITH marcadas AS (
        UPDATE nutri_porcoes p
           SET suspeito = true
          FROM nutri_alimentos a
         WHERE a.id = p.alimento_id
           AND NOT p.suspeito
           AND p.quantidade_g > 0
           AND (
                (a.nome_norm ~ '(cozid|refogad|ensopad|sopa|caldo|pure|guisad)'
                 AND (COALESCE(p.proteina_g,0)+COALESCE(p.carboidrato_g,0)+COALESCE(p.gordura_g,0))
                     * 100.0 / p.quantidade_g > 45)
             OR ((COALESCE(p.proteina_g,0)+COALESCE(p.carboidrato_g,0)+COALESCE(p.gordura_g,0))
                     * 100.0 / p.quantidade_g > 95)
               )
        RETURNING 1
    )
    SELECT count(*)::integer FROM marcadas;
$$;

SELECT marcar_porcoes_suspeitas();
