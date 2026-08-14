-- Menu-AI — identidade leve do usuário final: login por telefone + PIN.
-- Objetivo: o cliente recuperar o próprio perfil em outro aparelho sem depender
-- do usuario_id salvo no navegador. Telefone é único; PIN guardado com bcrypt.

ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS telefone TEXT;
ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS pin_hash TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_telefone
    ON usuarios (telefone) WHERE telefone IS NOT NULL;
