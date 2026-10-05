-- Estado durável de ações conversacionais que atravessam turnos.
--
-- O histórico em texto é memória para o modelo; `estado` é memória para o
-- produto. Uma confirmação de consumo não pode depender de o LLM reconstruir
-- itens e sobras a partir da conversa — ele confirma exatamente o payload que
-- foi mostrado na prévia.
ALTER TABLE sessoes
    ADD COLUMN IF NOT EXISTS estado JSONB NOT NULL DEFAULT '{}'::jsonb;

