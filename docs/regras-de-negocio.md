# Regras de Negócio — Menu-AI

> **Referência permanente do projeto.** Toda mudança de código deve consultar e respeitar este documento.
> Capturado a partir das reuniões de definição do produto. Atualize aqui sempre que uma regra mudar.

Última atualização: 2026-05-28

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

1. **Mostrar o cardápio completo primeiro:** ao pedir o cardápio, **sempre** mostrar o cardápio completo do
   dia, **mesmo que** o usuário tenha restrições.

2. **Depois recomendar, com justificativa:** a partir do cardápio completo, recomendar o que é indicado e
   **por quê**, no formato:
   > "O cardápio de hoje é …. Baseado nas suas restrições e preferências, recomendo …."

3. **Self-service → medidas caseiras:** traduzir a recomendação em **medidas caseiras** (colher, concha,
   etc.) com base na **meta calórica calculada** para o usuário.

---

## 4. Regras de admin

- **Configurar o cardápio por unidade** — cada unidade tem o seu; o admin configura no nível da unidade.
- **Cadastrar/editar cardápios** (que mudam semanal/mensalmente).
- **Cadastrar alimentos** e **organizar o cardápio semanal**, adicionando/removendo alimentos por dia.
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
