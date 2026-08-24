# Custo por provedor — o que foi medido

Documento para decidir onde rodar o modelo em cada situação: desenvolvimento,
demonstração com usuário e avaliação (eval). Os números vêm de medição própria
em 24/08/2026; onde há extrapolação, está dito.

## As duas cargas do sistema são muito diferentes

Isto explica quase tudo o que vem depois.

| | entrada | saída | chamadas/rodada |
|---|---|---|---|
| **Agente** (fala com o usuário) | ~4.800 tokens | ~350 tokens | ~450 |
| **Juiz** (só no eval) | ~230 tokens | **4** tokens | ~81 |

O agente carrega system prompt, esquema das tools e retornos, e gera resposta
inteira. O juiz lê um critério e responde `SIM`/`NAO`. Numa rodada de eval o
agente é **98,7% do custo** — otimizar o juiz é disputar 1,3% da conta.

## Medições

### Hugging Face — free tier

Do painel de billing da conta, período AGO 1 – SET 1:

```
Inference Usage:  US$ 0,03 / US$ 0,10
Ends on: Sep 1
28 requisições · gemma-4-31B-it: 22 req, US$ 0,03
```

- Franquia de **US$ 0,10 por mês**, que **renova todo dia 1º**.
- Estourou → `402 You have depleted your monthly included credits`.
- Destrava com **Add Credits** (pré-pago, não expira) ou **PRO US$ 9/mês** (20×).
- Limite de *requisições* é irrelevante: 1,7 milhão/dia, 540 milhões de tokens/dia.
  Quem barra é o dinheiro, não a quantidade.

Custo derivado: **~US$ 0,003 por mensagem de usuário** (~2 chamadas de LLM).
US$ 0,10 compra **~35 mensagens no mês inteiro**.

> Atenção: os "Hub Rate Limits" (API 1.000 / Resolvers 5.000 / Pages 200 por
> janela de 5 min) governam baixar modelo e abrir página — **não** inferência.
> É fácil confundir os dois painéis.

### OpenRouter — free tier e o limiar de 10 créditos

Da documentação oficial (`openrouter.ai/docs/api-reference/limits`), coluna
**"Credits purchased (all time)"**:

| conta | modelos gratuitos |
|---|---|
| nunca comprou crédito | **50 requisições/dia** |
| comprou ≥ 10 créditos (US$ 10) **alguma vez** | **1.000 requisições/dia** |
| ambos | **20 requisições/minuto** |

**É limiar acumulado, não saldo ativo.** Comprado uma vez, o limite de 1.000/dia
vale para sempre, mesmo com saldo zerado. A API expõe isso em `is_free_tier`
(`GET /api/v1/key`) — booleano da conta, não do saldo.

Isso foi verificado na documentação depois de a mensagem de erro do 429
("Add 10 credits to unlock 1000 free model requests per day") deixar ambíguo se
era pagamento único ou enquanto durasse o crédito. **É único.**

## Onde cada limite morde

```
20 req/min  ÷ ~2 chamadas por mensagem  =  ~10 mensagens de usuário por MINUTO
1.000 req/dia ÷ ~2                      =  ~500 mensagens de usuário por DIA
```

O teto diário é folgado. **O teto por minuto não é** — e ele é igual pagando ou
não. Numa apresentação com 15 pessoas digitando ao mesmo tempo, estoura na hora.

## Recomendação por situação

| situação | provedor | por quê |
|---|---|---|
| Desenvolvimento diário | HF gratuito | ~35 msg/mês dá para conferir mudança |
| Cliente testando sozinho | OpenRouter (US$ 10 uma vez) | custo marginal zero, 500 msg/dia |
| Piloto: 30 pessoas / 1 semana | OpenRouter | ~2.000 mensagens cabem no diário |
| **Apresentação ao vivo com plateia** | **pago** (Anthropic ou HF pré-pago) | 20 req/min é apertado demais para simultâneos |
| Eval, iterando durante o dia | Anthropic Haiku | US$ 0,04 só o juiz; resposta em segundos |
| Eval, rodada agendada | **Qwen2.5-3B local** | US$ 0, 39 min, sem cota nem chave |

Uma rodada completa de eval no HF custaria **~US$ 1,00** (extrapolado por tokens:
~2,3 milhões). Contra US$ 0,10/mês de franquia, o free tier cobre **um décimo de
uma rodada por mês** — serve para demonstração, não para medição.

## Trocar de provedor não exige código

`motor/provedores.py` centraliza a construção do modelo, e o compose repassa as
variáveis desde 24/08/2026:

```bash
LLM_PROVIDER=openai_compat            # ou anthropic, openrouter, ollama
LLM_BASE_URL=https://router.huggingface.co/v1
LLM_API_KEY=...
LLM_MODEL=google/gemma-4-31B-it
```

O eval tem as suas próprias, para o juiz não seguir o agente:
`EVAL_JUIZ_PROVIDER` e `EVAL_JUIZ_MODELO`.

> **O `.env` que o compose lê é o de `deploy/`, não o da raiz.** Configurar o
> arquivo errado não dá erro — dá silêncio, e o worker cai no default `ollama`.

## Ressalvas

1. Os números por mensagem vêm de conversa curta com cardápio de 4 pratos.
   Cardápio maior e conversa longa aumentam o contexto. Trate como piso.
2. Modelo gratuito pode ficar indisponível sem aviso — e você descobre no meio
   da apresentação. Para demo com cliente pagante, prefira previsibilidade.
3. `openrouter/free` é **roteador**: sorteia o modelo a cada chamada. Para demo,
   fixe um modelo e confirme que ele faz tool calling — sem isso, nada funciona.
