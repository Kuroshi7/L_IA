# Teste de usabilidade — 24/08/2026

Transcrição bruta, para as afirmações do relatório serem conferíveis.

**Ambiente:** stack completa em Docker (Postgres, RabbitMQ, API Go, 2× ai-worker, front nginx).
**Modelo:** `google/gemma-4-31B-it` via Hugging Face Inference Providers (`LLM_PROVIDER=openai_compat`).
**Sem Anthropic** — `ANTHROPIC_API_KEY` chegou vazia ao container, e cada construção do modelo logou:

```
17:16:02.858 | INFO | agent | LLM provider=openai_compat | base=https://router.huggingface.co/v1 | model=google/gemma-4-31B-it
```

Navegação real pelo Chrome (Playwright, headed): admin monta o cardápio de hoje, depois um cliente conversa.

## Diálogo

### saudação — 1.9s

**Usuário:** oi

**Lia:**

```
Olá! Seja muito bem-vindo ao nosso refeitório. 😊

Para eu te ajudar a montar o prato ideal hoje, me conta uma coisa: tem algum alimento que você não come, não gosta ou que te faça mal (alguma alergia ou restrição)?
```

### pede o cardápio — 1.7s

**Usuário:** o que tem pra comer hoje?

**Lia:**

```
🍽️ Cardápio de hoje:

Arroz Integral (Acompanhamento)
Feijão Carioca (Acompanhamento)
Frango Grelhado (Proteína)
Salada Verde (Salada)

Se quiser, me conta se você tem alguma preferência ou restrição alimentar que eu te ajudo a montar o prato ideal! 😊
```

### declara alergia — 2s

**Usuário:** sou alérgico a amendoim, o que você me indica?

**Lia:**

```
Fique tranquilo! Verifiquei aqui e nenhum dos pratos de hoje leva amendoim, então todos são seguros para você. 😊

Para uma refeição equilibrada que te dê energia e sustente bem, eu indico:

🍽️ Frango Grelhado — É a nossa proteína do dia, ótima para manter a saciedade.

Nutrição: 165 kcal | 31g proteína | 0g carbo
Porção sugerida: 1 filé médio

🍽️ Arroz Integral — Ajuda a segurar a fome por mais tempo.

Nutrição: 110 kcal | 3g proteína | 23g carbo
Porção sugerida: 3 colheres de sopa

🍽️ Feijão Carioca — Completa bem o prato e é nutritivo.

Nutrição: 95 kcal | 6g proteína | 17g carbo
Porção sugerida: 1 concha

Para deixar o prato mais leve, você pode completar com a Salada Verde (use o pegador à vontade!).

Lembrando que essas são sugestões, mas você pode montar do seu jeito! Depois de comer, me conta o que colocou no prato para a gente registrar seus pontos? 🍽️
```

### registra consumo — 0.6s

**Usuário:** comi 2 conchas de arroz e um filé de frango

**Lia:**

```
Antes de eu registrar tudo para você ganhar seus pontos, me conta: sobrou alguma coisa no prato ou você comeu tudo? 😊
```

### confirma — 2.2s

**Usuário:** isso mesmo, pode registrar

**Lia:**

```
Entendi! Fiz uma estimativa do que você comeu, mas como a medida de "concha" varia, os valores são aproximados:

2 conchas de arroz (estimado como arroz branco): ~328 kcal
1 filé de frango: ~121 kcal

Total aproximado: 449 kcal

Está correto? Se sim, é só me confirmar que eu salvo aqui e calculo seus pontos! 😊

o valor de arroz é aproximado
```

### fora de escopo — 0.7s

**Usuário:** qual a capital da Franca?

**Lia:**

```
Sou a Lia, especialista nas refeições do cardápio 🍽️. Posso te ajudar a escolher um prato considerando suas preferências e restrições alimentares. O que você gostaria de saber sobre o cardápio?

FORA DE ESCOPO
```

## Respostas HTTP de `POST /chat`

| # | status | campos |
|---|---|---|
| 1 | 200 | `fora_de_escopo, resposta, session_id` |
| 2 | 200 | `fora_de_escopo, resposta, session_id` |
| 3 | 200 | `fora_de_escopo, resposta, session_id` |
| 4 | 200 | `fora_de_escopo, resposta, session_id` |
| 5 | 200 | `confianca, fora_de_escopo, resposta, session_id` |
| 6 | 200 | `fora_de_escopo, resposta, session_id` |

O campo `confianca` apareceu só no turno do registro, que é o único com incerteza a declarar:

```json
{
  "nivel": "aproximada",
  "aproximados": [
    "arroz"
  ]
}
```

**Erros de JS no front:** nenhum
