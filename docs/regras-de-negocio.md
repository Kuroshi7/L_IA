# Regras de Negócio — Menu-AI

> **Referência permanente do projeto.** Toda mudança de código deve consultar e respeitar este documento.
> Capturado a partir das reuniões de definição do produto. Atualize aqui sempre que uma regra mudar.

Última atualização: 2026-07-07

---

## 1. Visão geral

Assistente de IA ("Lia") para refeitórios/restaurantes **self-service**. O cliente conversa com a LLM para
entender o cardápio do dia e receber recomendações personalizadas com base no seu perfil (restrições,
preferências e metas calóricas). O admin gerencia cardápios por unidade. Há gamificação e controle de
desperdício a partir do consumo registrado.

---

## 2. Entidades

### Usuário (cliente)
- Dados: **nome, restrições alimentares, preferências, peso, altura, idade** (e sexo/nível de atividade para o cálculo).
- Usados para **cálculo calórico** (fórmula de Mifflin-St Jeor) e **IMC** (peso / altura²).
- A LLM tem acesso a esses dados **em nível de usuário** — sabe as restrições e preferências de quem está conversando.

### Unidade
- Possui **nome** e **cardápio próprio**, configurado pelo admin **no nível da unidade**.
- As informações de cardápio são **isoladas por unidade** (cada unidade só enxerga o seu cardápio).

### Alimento (base de pratos/itens)
- Cadastrado pelo admin.
- Pode estar **ativo ou inativo** em um cardápio.

### Cardápio semanal/mensal
- Composto por alimentos organizados **por dia**.
  - Ex.: Segunda → arroz, macarrão, cenoura cozida; Terça → batata cozida, feijão preto, beterraba.
- **Muda semanal ou mensalmente.**

---

## 3. Regras de chat / recomendação

0. **Seleção de unidade (obrigatória):** o front exibe um **seletor de unidades**. O usuário clica na
   unidade e abre o **chat daquela unidade**. A `unidade_id` é passada explicitamente do seletor para toda
   a sessão/requisição. **Não há "unit resolver"** nem inferência de unidade pela LLM. Cardápio e RAG
   **sempre filtram pela `unidade_id` selecionada**, isolando as informações e simplificando o contexto da LLM.

1. **Mostrar o cardápio completo primeiro (REGRA CONTRATUAL):** sempre que o usuário pedir o cardápio
   **ou uma recomendação**, mostrar o cardápio completo do dia, **mesmo que** o usuário tenha restrições.
   Na **primeira conversa do dia** isso é obrigatório e garantido pelo sistema (não só pelo prompt): a API
   Go calcula a flag `primeira_do_dia` (primeira mensagem do usuário no dia, no fuso do refeitório) e o
   agente recebe uma nota de sistema exigindo o cardápio completo antes da recomendação.
   > Ex.: "olá, gostaria de uma recomendação de alta proteína" → "Olá, X! O cardápio de hoje é ….
   > Baseado nas suas preferências/restrições, recomendo o prato Y por ter o maior teor de proteína."

2. **Depois recomendar, com justificativa:** a partir do cardápio completo, recomendar o que é indicado e
   **por quê**, no formato:
   > "O cardápio de hoje é …. Baseado nas suas restrições e preferências, recomendo …."

3. **Self-service → medidas caseiras:** traduzir a recomendação em **medidas caseiras** (colher, concha,
   etc.) com base na **meta calórica calculada** para o usuário.

4. **Persona da Lia:** nutricionista virtual do refeitório — acolhedora, linguagem simples (sem jargão
   nutricional), pensa em "prato montado" (medidas caseiras), nunca julga o consumo registrado e prioriza
   pratos compatíveis quando o perfil cita condições de saúde (pressão alta, diabetes etc.), **sem**
   prescrever dieta nem dar conselho médico. Definida em `apps/ai/app/agent/prompts.py`.

5. **Identidade leve do cliente:** cadastro pode incluir **telefone + PIN (4–6 dígitos)** para recuperar o
   perfil em outro aparelho (`POST /usuarios/login`). Telefone é único; PIN guardado com bcrypt. Não há
   senha/e-mail — é identidade de conveniência, não autenticação forte.

6. **Fuso do refeitório:** todo conceito de "dia" (streak, desperdício diário, primeira conversa do dia)
   usa **America/Sao_Paulo**, não o UTC do servidor.

---

## 4. Regras de admin

- **Configurar o cardápio por unidade** — cada unidade tem o seu; o admin configura no nível da unidade.
- **Cadastrar/editar cardápios** (que mudam semanal/mensalmente).
- **Cadastrar alimentos** e **organizar o cardápio semanal**, adicionando/removendo alimentos por dia.
  A grade cobre a semana **completa (seg–dom)**, com navegação para qualquer data e cópia de uma
  semana para qualquer outra (ex.: falta de insumo → ajustar só o dia; ciclo mensal → copiar semanas).
- **Criar/remover pratos da base**, mesmo que estejam ativos/inativos em algum cardápio.
- **Proteína do dia é o único item controlado:** limitada a **1 por pessoa**.
- **Controle de desperdício:** ter visão do desperdício a partir do **consumo individual registrado**.

---

## 5. Consumo individual

- Registro do que cada usuário efetivamente consumiu (em medidas caseiras / quantidades).
- Serve a dois propósitos:
  1. **Gamificação** (pontuação por aderência à recomendação).
  2. **Controle de desperdício** do admin (visão agregada).

---

## 6. Gamificação (versão inicial, simples)

- O usuário informa o que consumiu em **linguagem natural**, ex.:
  > "2 col de arroz, 1 concha de feijão, 1 frango grelhado, 2 col de legumes cozidos"
- O consumo é convertido em **calorias e nutrientes** (via guia de medidas caseiras).
- A pontuação é baseada na **proximidade entre o consumido e a META calórica/nutricional**
  recomendada para o usuário — **NÃO** em ter escolhido exatamente os itens recomendados:
  - Consumo **igual à meta** de calorias/nutrientes → **pontuação máxima** (sobe de nível).
  - **Acima ou abaixo** da meta → **menos pontos**, em **proporção ao desvio** calórico/nutricional.
  - **Muito distante** da meta → **0 pontos**.
- Observação: o cliente tem liberdade de montar o prato como quiser; o que pontua é o quão
  perto o resultado (calorias/nutrientes) ficou da meta dele, não a aderência item a item.

---

## 6.1 Fórmula de pontuação (implementada)

Registrar consumo pelo chat pontua assim (`internal/domain/gamificacao.go`):

- **Meta da refeição** = 35% da meta calórica diária (almoço concentra 30–40% do VET; usamos 35%).
- **Pontos base** = `100 × max(0, 1 − desvio/0.5)` onde `desvio = |kcal consumida − meta da refeição| / meta`.
  Meta exata → 100; desvio ≥50% → 0; linear entre os extremos.
- **Bônus prato limpo** = +20 quando o resto reportado ≤ 10% do servido (espelha o critério
  de aceitação do FNDE/PNAE: consumo ≥ 90%).
- **Bônus streak** = +5 por dia consecutivo registrando (a partir do 2º), máx. +25.
- Perfil sem meta calórica → 10 pontos fixos por registro (engajamento).
- **Nível** = `1 + pontos/500`.

## 6.2 Desperdício (implementado)

Metodologia de UAN (Unidade de Alimentação e Nutrição) adaptada ao auto-relato digital —
não pesamos resto fisicamente; o usuário informa o que comeu e, opcionalmente, o que
**deixou no prato** (a Lia pergunta uma vez ao registrar):

- **Índice de resto-ingesta (proxy)** = `resto / (consumido + resto)`, em gramas,
  agregado por unidade/dia. Análogo digital de `resto ÷ distribuído` da literatura.
- **Faixas de referência** (Teixeira 1990 / Vaz 2006): **≤3% ótimo · ≤10% bom ·
  ≤15% atenção · >15% crítico**. Resto per capita aceitável: 15–45 g.
- **Pipeline**: registro de consumo → evento `consumo.registrado` (outbox, mesma
  transação) → RabbitMQ → worker Go agrega em `desperdicio_diario` (idempotente via inbox)
  → dashboard admin (`GET /admin/unidades/{id}/desperdicio`), com série diária e
  top de alimentos deixados no prato.
- **Resiliência do worker**: mensagem que falha é retentada até 5×; depois vai para a
  DLQ `go.worker.events.dlq` (poison message não trava a fila). Datas do agregado e do
  top de desperdiçados usam o fuso do refeitório (America/Sao_Paulo).
- **Testes reais**: `apps/api/scripts/test-integration.sh` roda os testes de integração
  (Postgres descartável) cobrindo pontuação, streak, nível, ranking, ETL de desperdício
  idempotente e login por telefone+PIN.
- Ressalva: auto-relato é indicador de **tendência/engajamento**, não medida absoluta;
  agregação semanal reduz o ruído.

## 7. Cálculos de referência

- **IMC** = peso (kg) / altura (m)².
- **Meta calórica** = Mifflin-St Jeor (usa peso, altura, idade, sexo, nível de atividade).
- **Medidas caseiras** = tabela de referência que converte medida caseira → gramas → kcal. Usada para
  recomendar porções e para interpretar o consumo informado.

---

## 8. Notas de arquitetura (resumo; detalhes no plano e no README)

- **Go** é a fonte da verdade (Postgres): usuários, unidades, alimentos, cardápios, sessões, consumo, gamificação.
- **Python** cuida da IA: agente LLM, RAG/embeddings (pgvector), memória. Obtém dados de domínio via **API interna do Go**.
- **RabbitMQ** + **Outbox transacional** (Postgres) para filas/idempotência; workers controlam concorrência de múltiplos usuários.
- **Front** Vite/React+TS: seletor de unidade → chat por unidade; áreas de cadastro e admin.
