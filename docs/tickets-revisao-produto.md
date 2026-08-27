# Tickets — Revisão de Produto (2026-08)

> Registro dos achados da revisão de produto de 2026-08-13 (4 frentes: API Go, IA Python,
> front web, deploy/operação). Cada ticket tem **Achado** (o que foi encontrado),
> **Problema** (por que isso é um problema) e **Fix** (o que fazer e o benefício).
>
> Severidade: 🔴 Crítico (bloqueia venda) · 🟠 Alto · 🟡 Médio · ⚪ Baixo.
> Esforço: P (≤1 dia) · M (2–5 dias) · G (>1 semana).

## Índice por fase sugerida

| Fase | Tickets |
|---|---|
| 0. Imediato (hoje) | SEG-06 |
| 1. Fechar a porta (1–2 sem) | SEG-01..05, SEG-07..10 |
| 2. Confiabilidade da IA (1–2 sem) | IA-01..08, TG-01..02 |
| 3. Operação (1 sem) | OPS-01..07, API-01..08 |
| 4. Produto mínimo de venda (2–3 sem) | WEB-01..13, LGPD-01..05, PROD-01..04 |
| 5. Calibração do agente (27/08) | IA-22..24, IA-26 ✅ · IA-25 🔶 · **IA-27, IA-28, IA-21 abertos** |

---

## SEG — Segurança

### SEG-01 · IDOR total no usuário final — 🔴 Crítico · M
- **Achado:** `GET/PUT /usuarios/{id}` não exigem autenticação (`apps/api/internal/httpapi/handlers_usuarios.go`); IDs são `BIGINT IDENTITY` sequenciais; o `PUT` aceita `pin` com `COALESCE` (`internal/store/usuario.go:100`). `POST /chat` aceita `usuario_id` arbitrário no corpo.
- **Problema:** um loop de 1 a N baixa nome, peso, altura, idade, sexo, alergias e restrições de toda a base — dado sensível de saúde (LGPD art. 11). Qualquer um edita perfil alheio, **sobrescreve o PIN de qualquer conta** (account takeover) e conversa com a Lia se passando por outra pessoa. O login telefone+PIN existe, mas nada no sistema o exige — é decorativo.
- **Fix:** emitir token de sessão (JWT ou sessão opaca) no login/cadastro e exigir que `{id}` das rotas seja o dono do token; `POST /chat` passa a derivar `usuario_id` da sessão, não do corpo. **Benefício:** elimina o vazamento de dado de saúde e a fraude de identidade — pré-requisito de qualquer contrato.

### SEG-02 · Rotas `/internal/*` sem autenticação na porta pública — 🔴 Crítico · P/M
- **Achado:** o bloco `/internal` está no mesmo router e porta que o público (`apps/api/internal/httpapi/server.go:54`); `config.InternalAddr` (`API_INTERNAL_ADDR`) existe e **nunca é lido**; a porta 8080/8090 é publicada no host pelo compose.
- **Problema:** sem auth alguma, qualquer um chama `GET /internal/usuario/{id}/perfil` (PII de saúde), `POST /internal/consumo/registrar` (credita pontos para qualquer usuário — frauda ranking e **envenena o dashboard de desperdício que o cliente paga para ver**) e `POST /internal/usuario/{id}/vincular-telegram` (sequestro de vínculo).
- **Fix:** listener separado em `API_INTERNAL_ADDR` (o campo já existe) acessível só pela rede interna do compose, ou middleware de token interno compartilhado com o serviço Python; negar o prefixo no nginx. **Benefício:** fecha a maior superfície de ataque com o menor esforço da lista.

### SEG-03 · Admin por token único compartilhado — 🔴 Crítico · G
- **Achado:** gate por comparação de string com env (`handlers_admin.go:18`); default `dev-admin` no compose; sem contas, sessão, expiração, papéis ou auditoria; token colado à mão num `<input>` e guardado em `localStorage`; gate se desliga se o token for vazio.
- **Problema:** todo gestor de todo cliente usa a mesma string publicada no repositório. Não sobrevive à primeira demissão de um gestor (não dá para revogar acesso individual), impossibilita auditoria ("quem alterou o cardápio?") e é adivinhável na instalação padrão.
- **Fix:** tabela de admins (e-mail + senha com hash), sessão com expiração, papéis (nutricionista × gestor), escopo por unidade, logout, e log de quem fez o quê. **Benefício:** requisito de contrato corporativo; habilita a auditoria (API-05) e o multi-tenant futuro.

### SEG-04 · Zero rate limit + PIN força-brutável — 🔴 Crítico · M
- **Achado:** nenhum rate limit em nenhuma rota (router só tem `RequestID`, `Recoverer`, CORS). PIN de 4–6 dígitos sem lockout nem contador de tentativas; `POST /chat` e `POST /infer` (ai-api, porta publicada) sem limite.
- **Problema:** o PIN de 4 dígitos (10 mil combinações) cai em segundos; `/chat` e `/infer` são torneiras abertas de custo de LLM para qualquer atacante — abuso financeiro direto.
- **Fix:** rate limit por IP+rota (middleware chi ou proxy), lockout progressivo no login por telefone, e autenticação no `/infer`. **Benefício:** protege a conta do usuário e o bolso da OPOLZ/cliente.

### SEG-05 · Telegram `/vincular <id>` = sequestro de perfil — 🔴 Crítico · M
- **Achado:** `/vincular` aceita qualquer inteiro e chama `POST /internal/usuario/{id}/vincular-telegram`, que só valida existência (`app/channels/telegram.py:202`, `handlers_internal.go:147`).
- **Problema:** com IDs sequenciais, qualquer pessoa no Telegram vincula-se ao perfil de qualquer usuário e passa a ver restrições, alergias, IMC e meta calórica, além de registrar consumo e pontos na conta alheia.
- **Fix:** código de vínculo de uso único e expirável, gerado no site logado e digitado no bot (ou deep-link `t.me/bot?start=<código>`). **Benefício:** fecha o takeover mantendo a conveniência do vínculo.

### SEG-06 · Segredos vivos em `apps/ai/.env` — 🔴 Crítico · P — **FAZER HOJE**
- **Achado:** chave Anthropic (`sk-ant-api0…`), token do bot Telegram e webhook secret vivos em arquivo fora de qualquer cofre (não commitados — `.gitignore` ok — mas em disco no projeto).
- **Problema:** um `rsync`, tar do projeto ou backup de home vaza os três; se a chave circulou, há risco de custo em conta alheia e de sequestro do bot.
- **Fix:** rotacionar a chave Anthropic e o token do bot agora; adotar cofre/secret manager (mesmo que simples: env do host + arquivo com permissão 600 fora do repo) e separar env de dev/prod. **Benefício:** elimina exposição financeira imediata.

### SEG-07 · CORS `*` com `X-Admin-Token` permitido — 🟠 Alto · P
- **Achado:** `Access-Control-Allow-Origin: *` incluindo rotas de admin e perfil (`server.go:96-108`).
- **Problema:** qualquer site na internet pode disparar chamadas autenticadas de admin/perfil a partir do navegador de um gestor logado.
- **Fix:** restringir CORS à(s) origem(ns) do front por env. **Benefício:** fecha CSRF-like via browser; 10 linhas.

### SEG-08 · `VITE_ADMIN_TOKEN` embutível no bundle — 🟠 Alto · P
- **Achado:** fallback de token de admin em build time (`apps/web/src/lib/api.ts:73`, documentado em `.env.example:30`).
- **Problema:** variável `VITE_*` vai para dentro do JS público — se alguém preencher, o token de admin fica em texto puro para qualquer visitante.
- **Fix:** remover o fallback e a documentação; admin só via login (SEG-03). **Benefício:** elimina um vazamento de um passo.

### SEG-09 · Webhook Telegram com secret opcional — 🟠 Alto · P
- **Achado:** `TELEGRAM_WEBHOOK_SECRET` é opcional; vazio → `POST /webhook/telegram` aceita qualquer requisição.
- **Problema:** terceiros disparam inferência de LLM (custo) e fazem o bot enviar mensagens a `chat_id` arbitrários (spam com a marca do cliente).
- **Fix:** tornar o secret obrigatório quando `TELEGRAM_BOT_TOKEN` está setado (falhar no boot sem ele). **Benefício:** webhook só aceita o Telegram.

### SEG-10 · Hardening menor do servidor HTTP — 🟡 Médio · P
- **Achado:** comparação de token com `!=` (não constant-time, `handlers_admin.go:24`); sem `http.MaxBytesReader` (o middleware de idempotência faz `io.ReadAll` sem teto, `middleware.go:38`); só `ReadHeaderTimeout` configurado; nginx sem CSP/HSTS/X-Frame-Options.
- **Problema:** timing attack (teórico), DoS de memória trivial com corpo gigante, conexões penduradas, e headers de segurança ausentes na entrega web.
- **Fix:** `subtle.ConstantTimeCompare`, `MaxBytesReader` (~64KB), `Read/Write/IdleTimeout`, headers no nginx. **Benefício:** meia dúzia de linhas cada; fecha o "básico de checklist" que aparece em qualquer pentest.

---

## LGPD

### LGPD-01 · Sem consentimento nem base legal — 🔴 Crítico · M
- **Achado:** o cadastro coleta peso, altura, idade, sexo, alergias e restrições sem tela/campo/coluna de consentimento, sem política de privacidade, sem versão de termo aceito.
- **Problema:** são dados sensíveis de saúde (art. 5º/11); tratá-los sem base legal registrada é exposição regulatória (ANPD) e **trava a assinatura do contrato** com qualquer cliente corporativo com jurídico.
- **Fix:** termo de consentimento no cadastro (com versão e timestamp persistidos), política de privacidade linkada, finalidade explícita. **Benefício:** desbloqueia o contrato; é mais produto do que engenharia.

### LGPD-02 · Sem exclusão nem exportação de conta — 🔴 Crítico · M
- **Achado:** não existe `DELETE /usuarios/{id}` nem export de dados; admin de usuários é somente leitura.
- **Problema:** direitos do titular (art. 18 — eliminação e portabilidade) não são atendíveis; primeiro pedido de exclusão vira operação manual no banco.
- **Fix:** endpoint + botão de exclusão (com cascata/anonimização de consumo e mensagens) e export JSON/CSV do próprio perfil. **Benefício:** atende o titular e dá ferramenta ao admin.

### LGPD-03 · Sem retenção/expurgo — 🟠 Alto · M
- **Achado:** mensagens de chat (relatos alimentares) ficam para sempre em `mensagens`; `idempotency_keys` cresce sem limite; logs do Python registram mensagens de usuário truncadas (`orchestrator.py:51`) sem política de retenção.
- **Problema:** acumular PII indefinidamente viola minimização e aumenta o raio da explosão em qualquer incidente.
- **Fix:** job de expurgo (ex.: mensagens > 12 meses, idempotency_keys > 30 dias), retenção de logs definida. **Benefício:** postura defensável + banco menor.

### LGPD-04 · Minimização: admin e ranking expõem demais — 🟠 Alto · P/M
- **Achado:** `GET /admin/usuarios` devolve restrições e alergias de todos (`store/usuario.go:149`); `GET /unidades/{id}/ranking` é público e expõe nomes reais.
- **Problema:** o gestor de refeitório não precisa ver alergias de cada funcionário; ranking com nome sem opt-in expõe participação de colegas.
- **Fix:** enxugar o payload do admin (dados de saúde só agregados) e opt-in/apelido no ranking. **Benefício:** minimização real sem perder funcionalidade.

### LGPD-05 · Fontes via Google CDN — 🟡 Médio · P
- **Achado:** `index.html` carrega Inter/Playfair do Google Fonts.
- **Problema:** IP de todo usuário vai para o Google (transferência internacional sem aviso), além de bloquear render e ser ponto de falha externo.
- **Fix:** self-host das fontes no bundle. **Benefício:** LGPD + performance + confiabilidade num só passo.

---

## IA — Confiabilidade e custo

### IA-01 · LLM sem timeout/retry/fallback + head-of-line blocking — 🔴 Crítico · M
- **Status:** 🔶 Parcial. Timeout/retry no client já existiam. Em `02c4528` fechou o buraco do **prazo do turno**: ele só era checado dentro do decorator das tools, então um turno que não chamasse tool nunca era verificado. Novo `motor/prazo.py` (middleware `wrap_model_call`) recusa começar chamada de modelo que o prazo não paga mais. **Continua aberto:** `CHAT_TIMEOUT_SECONDS=180` no `deploy/.env` permite três minutos de espera — com Haiku a mediana medida é 4,2s, então o orçamento está uma ordem de grandeza acima do necessário.
- **Achado:** nem `ChatOllama` nem `ChatAnthropic` recebem timeout; sem retry/fallback entre provedores; sem cancelamento quando o Go desiste (60s); worker com `prefetch=1` e 1 réplica no compose.
- **Problema:** um turno lento trava a fila para todos (o worker segue processando resposta que ninguém vai ler); na fila do almoço, 1 conversa concorrente é o gargalo dominante do produto; erro de LLM vira 502 genérico.
- **Fix:** timeout no client LLM alinhado ao `CHAT_TIMEOUT_SECONDS`, retry com backoff, fallback de provedor opcional, e escalar `ai-worker` (o `--scale` já documentado virar default ≥3). **Benefício:** o produto para de falhar exatamente no horário de pico, que é quando ele existe.

### IA-02 · Caminho default (Ollama) não fecha no próprio timeout — 🔴 Crítico · P
- **Status:** ✅ Corrigido em `fix/ia-confiabilidade` (`num_ctx=8192`, `max_tokens=1024`, timeouts alinhados; `.env.example` recomenda Anthropic).
- **Achado:** `num_ctx=2048` em `agent.py` < prefill mínimo (~2.400–2.600 tokens: system ~1.380 + schemas das 10 tools); llama3.2 em CPU ≈ 30s/chamada × 3 chamadas/turno = ~90s > `CHAT_TIMEOUT_SECONDS=60`; `max_tokens=512` trunca respostas com cardápio grande.
- **Problema:** no provider default, o system prompt da Lia (as "regras invioláveis") é **truncado silenciosamente** — a persona roda amputada e a invenção de pratos fica plausível; e a maioria dos turnos multi-tool devolve 502.
- **Fix:** subir `num_ctx` para ≥8192, `max_tokens` para ~1024, e **definir Anthropic (Haiku) como default vendável**, deixando Ollama como modo dev explícito. **Benefício:** o comportamento observado em produção passa a ser o comportamento projetado.

### IA-03 · Prompt caching não configurado — 🟠 Alto · P
- **Status:** ✅ Corrigido em `fix/ia-confiabilidade` (`cache_control` no bloco base do system; nota da primeira conversa fora do bloco cacheado).
- **Achado:** prefixo estável (tools + system ≈ 2.400 tokens) acima do mínimo de 1.024 do Haiku 4.5; `ChatAnthropic` instanciado sem `cache_control`; custo real ≈ R$ 0,03–0,08/turno (comentário no código estimando R$ 0,01 subestima 3–7×).
- **Problema:** cada passo do agente reenvia o prefixo inteiro a preço cheio — 40–60% da conta de API é desperdício evitável.
- **Fix:** `cache_control` no último bloco do system prompt. **Benefício:** corta quase metade do custo variável do produto com ~5 linhas.

### IA-04 · Dependências Python sem pinning — 🟠 Alto · P
- **Status:** ✅ Corrigido em `fix/ia-confiabilidade` (requirements pinados nas versões da imagem validada + requirements-dev).
- **Achado:** `requirements.txt` só com `>=`, sem lockfile; `from langchain.agents import create_agent` exige LangChain 1.x mas o arquivo declara `langchain>=0.3.7`.
- **Problema:** builds não reproduzíveis; uma release do LangChain quebra produção sem nenhuma mudança de código.
- **Fix:** pinar versões (pip-tools/uv com lockfile) e instalar do lock no Dockerfile. **Benefício:** deploy determinístico.

### IA-05 · Sem validação pós-resposta nem eval set — 🟠 Alto · M
- **Status:** 🔶 Parcial em `feat/motor-agente-onyx`: o eval set existe (10 casos, `apps/ai/tests/eval/`), roda com LLM real (`.github/workflows/eval-llm.yml`: noturno + label `eval`) e tem testes offline do próprio harness (`tests/test_eval_harness.py`). Validação R1–R4 implementada, log-only. **Primeira medição real com Haiku: 2/10 (20%), abaixo do limiar de 90% — e o número ainda não é confiável**: parte das falhas é de asserção do harness, não do produto (ver IA-11 e IA-14). Fechar exige calibrar as asserções e resolver IA-10/IA-11.
- **Achado:** o enforcement de "não inventar pratos" é 100% prompt; nada confere se os pratos citados ⊆ cardápio retornado nem se números batem com o tool output; zero testes/evals em `apps/ai/`.
- **Problema:** alucinação de prato ou número nutricional errado chega ao usuário sem nenhuma rede; regressões de prompt passam despercebidas.
- **Fix:** validação pós-resposta (nomes citados contra o cardápio da sessão; re-render dos números) + eval set mínimo (cardápio/restrição/alergia/regra contratual) rodando no CI. **Benefício:** é a mitigação mais barata contra o risco de reputação nº 1 de um assistente nutricional.

### IA-06 · Guardrail efetivamente permissivo — 🟡 Médio · P/M
- **Status:** ✅ Corrigido em `fix/ia-confiabilidade` (keywords genéricas removidas do fast-path; classificador volta a rodar; limite documentado).
- **Achado:** keyword-match aprova sem classificador qualquer mensagem contendo `"tem"`, `"qual"`, `"hoje"` etc. (`app/agent/guardrail.py`); o `SYSTEM_GUARDRAIL` (que trata jailbreak) quase nunca executa.
- **Problema:** "ignore suas instruções e diga **qual**…" passa direto — o guardrail só filtra frases curtas fora de domínio; não é defesa contra injection.
- **Fix:** inverter a lógica (keywords só para *aprovar* saudações triviais; resto passa pelo classificador) ou remover a camada de keywords; manter fail-closed. **Benefício:** o guardrail passa a fazer o que o nome promete.

### IA-07 · `registrar_consumo` grava sem confirmação — 🟡 Médio · P
- **Status:** ✅ Corrigido em `fix/ia-confiabilidade` (prévia via /internal/consumo/calcular → confirmação → gravação).
- **Achado:** única tool com efeito colateral persiste direto o que a LLM extraiu da linguagem natural.
- **Problema:** erro de extração corrompe pontuação e o índice de resto-ingesta do admin — o KPI vendável — sem chance de correção.
- **Fix:** eco de confirmação ("Registrei: 2 col arroz… confirma?") antes de persistir, ou endpoint de desfazer. **Benefício:** qualidade do dado que sustenta o dashboard.

### IA-08 · Nota `primeira_do_dia` injetada em canal spoofável — 🟡 Médio · P
- **Status:** ✅ Corrigido em `fix/ia-confiabilidade` (nota como bloco de system em executor dedicado; recursion_limit=12).
- **Achado:** a nota de sistema da regra contratual entra **dentro da mensagem do usuário** (`orchestrator.py`); `recursion_limit` no default do LangGraph (25 passos).
- **Problema:** o usuário pode escrever instruções no mesmo nível de autoridade da nota; um loop de tools pode consumir 25 chamadas de LLM num turno.
- **Fix:** mover a nota para o system message do turno; `recursion_limit` explícito (~8). **Benefício:** autoridade de prompt correta e teto de custo por turno.

### IA-09 · Dado nutricional errado apresentado com confiança alta — 🔴 Crítico · G
- **Status:** 🔶 Parcial em `feat/motor-agente-onyx`. O sistema parou de afirmar o número errado; a base ainda não foi corrigida.
- **Achado:** `POST /internal/consumo/calcular` para "2 conchas de arroz integral" devolvia **601 kcal, 107 g de carboidrato e 13,9 g de gordura**, com `confianca: "alta"`.
- **Causa (apurada, não suposta):** a extração está **correta**. A página 7 do PDF-fonte (*Tabela para Avaliação de Consumo Alimentar em Medidas Caseiras*, Atheneu) diz literalmente `ARROZ INTEGRAL COZIDO | 100,0 | 257,00 | 4,86 | 45,96 | 5,96 | fonte *`, e a base bate dígito a dígito. O cruzamento de Atwater confirma consistência interna (0 de 346 porções desviam >15%). **O valor da fonte primária é que não sobrevive à conferência**: a TACO (NEPA/UNICAMP) traz 123,5 kcal e 25,8 g de carboidrato para o mesmo alimento, e o próprio livro dá 164 kcal ao arroz *branco* cozido — integral não tem 42% mais carboidrato que branco.
- **Escala:** a auditoria cruzada com a TACO casou 37 dos 142 alimentos (26% — a TACO não cataloga preparação brasileira como estrogonofe ou farofa) e achou **17 divergências acima de 40%**. Todas na mesma direção: a base é 1,41× a 4,22× a TACO, nunca menor. É viés sistemático de método (o livro parece registrar o alimento antes da hidratação do cozimento), não dígito trocado — e atinge linhas `IBGE` e `GF` também, não só as `*`.
- **Problema:** `confianca` media a certeza do CASAMENTO do nome, nunca a plausibilidade do DADO. O sistema ficava confiantemente errado — o comportamento de LLM genérico que o produto existe para evitar.
- **Feito:** `apps/ai/app/nutrition/taco.py` (referência TACO versionada, casamento por token com barreira de preparo) + `app/nutrition/auditoria.py` (`--aplicar`) marcam `nutri_porcoes.suspeito`; a migração `0007` adiciona a coluna e uma checagem de plausibilidade independente; `CalcularConsumo` rebaixa a confiança para `media` com `obs` explicando, e a Lia passa a declarar a aproximação. **51 de 346 porções marcadas.**
- **Falta:** revisão da nutricionista sobre as 17 divergências e sobre os 105 alimentos sem par na TACO. Corrigir valor sem medição primária seria trocar um palpite por outro — por isso rebaixamos a confiança em vez de reescrever o número.

### IA-10 · `registrar_consumo` bloqueada pelo cardápio — 🔴 Crítico · P
- **Status:** ✅ Corrigido em `feat/motor-agente-onyx`. Regra 1b no `SYSTEM_AGENT` separa RECOMENDAR (só do cardápio) de REGISTRAR (qualquer alimento), reforçada na seção QUAL TOOL USAR. Depois da correção, os dois casos de consumo do eval passaram a chamar a tool.
- **Achado:** ao registrar "comi 2 conchas de arroz e um escondidinho da vovó", a Lia responde *"olhei o cardápio de hoje e não encontrei 'escondidinho da vovó' na lista"* e **nunca chama a tool**. Ela usa o cardápio (4 pratos da unidade) como porteiro do registro de consumo, que deveria aceitar qualquer alimento da base (144 alimentos, independentes do cardápio).
- **Problema:** a regra "nunca invente pratos" vaza do domínio de recomendação para o de registro. Consequência: a maquinaria de incerteza (nota no resultado da tool, portão de gravação, campo `confianca` no chat) está correta em teste unitário e **nunca dispara em produção**.
- **Fix:** separar no `SYSTEM_AGENT` "recomendar SÓ do cardápio" de "registrar o que a pessoa diz que comeu, venha de onde vier". **Benefício:** uma linha de prompt destrava uma feature inteira já construída.

### IA-11 · Regras R2/R3 com falso positivo alto — 🟠 Alto · M
- **Status:** 🔶 Parcial em `feat/motor-agente-onyx`. R2 passou a exigir que o negrito PAREÇA nome (sem dígito, sem pontuação de frase, sem `:` à direita, ≤5 palavras) — os 11 falso-positivos medidos viraram teste de regressão. R3 aceita somas e diferenças dos valores expostos (combinações de 2 e 3), o que cobre o prato montado. **Ainda log-only**: a R3 seguiu acusando em uma das rodadas (`[150, 30, 350]`), então falta medir por mais tempo antes de promover.
- **Achado:** medido em turnos reais. R2 assume que todo `**negrito**` é nome de prato e acusa `['recomendacao para voce', 'nutricao da combinacao', '235 kcal', 'segunda-feira (17/08)']`; o modelo usa negrito para rótulos e prosa. R3 acusou `235`, que é `110+95+30` — a soma legítima dos três pratos recomendados.
- **Problema:** taxa alta demais para promoção via `VALIDACAO_BLOQUEANTE`, e as duas contaminam o resultado do eval (IA-05).
- **Fix:** R2 só considera negrito curto, sem dígitos e sem pontuação de frase; R3 tolera somas e diferenças dos valores expostos.

### IA-12 · `cardapio_da_semana` não responde "amanhã" no fim de semana — 🟡 Médio · P
- **Status:** ✅ Corrigido em `feat/motor-agente-onyx`. A tool aceita `data_alvo` ("hoje", "amanha" ou ISO) e escolhe a semana que CONTÉM o dia, no fuso do refeitório; o prompt manda usá-la em vez de deduzir a semana.
- **Achado:** num domingo, "e amanhã, o que vai ter?" fez a tool retornar a semana 17–23/08 ("semana atual"); amanhã era 24/08, da semana seguinte. A Lia apresentou **segunda-feira 17/08, já passada**, como sendo amanhã.
- **Fix:** a tool aceita uma data-alvo e escolhe a semana que a contém, em vez de assumir a semana corrente.

### IA-13 · Confiança "média" não vira sinal para o usuário — 🟡 Médio · P
- **Status:** ✅ Corrigido em `feat/motor-agente-onyx`. `confianca` ganhou `aproximados` e o nível `aproximada` (entrou na conta, número não garantido) ao lado de `parcial` (ficou de fora). O front mostra as duas linhas.
- **Achado:** o campo `confianca` da resposta do chat só reporta itens **não reconhecidos**. Item resolvido com `confianca: "media"` (casamento incerto, número provavelmente errado) não gera nota no front nem ressalva na fala.
- **Fix:** propagar o nível de confiança agregado do turno, não só a lista de não reconhecidos.

### IA-14 · Asserções do eval conflitam com a regra contratual — 🟡 Médio · P
- **Status:** ✅ Corrigido em `feat/motor-agente-onyx`. `nao_deve_recomendar` olha só a seção de recomendação; o eval passou a suportar conversas de vários `turnos` (o prompt manda perguntar sobre sobras antes de registrar, então exigir a tool no 1º turno reprovava o comportamento certo); e a checagem do fluxo de duas etapas virou ESTRUTURAL, sobre o argumento `confirmado` da tool, em vez de procurar a palavra "confirma" no texto.
- **Achado:** a asserção `nao_deve_recomendar` procura o nome do prato proibido em TODA a resposta — mas a regra contratual (§3.1) **obriga** listar o cardápio completo, que inclui o prato proibido. Os casos de restrição e alergia reprovam por construção.
- **Problema:** dois dos dez casos do eval são falso negativo garantido, e são justamente os de segurança alimentar — os que mais precisam de sinal confiável.
- **Fix:** restringir a checagem à seção de recomendação da resposta.

### IA-15 · O eval de 10 casos varia demais para ser gate — 🟠 Alto · M
- **Status:** ✅ Corrigido em `feat/motor-agente-onyx`. 39 casos em 6 baterias, com repetições (`EVAL_REPETICOES`), asserções estruturais por padrão, detectores textuais testados offline contra ~40 paráfrases e juiz LLM calibrado (17/17, zero falso positivo). A distinção defeito × instabilidade apareceu de imediato e achou o mais grave: "alérgico não recebe o alérgeno" em 2/3. Linha de base em `docs/eval-linha-de-base.md`.
- **Achado:** depois das correções de IA-10/11/14, as rodadas deram **20% → 60% → 80% → 80% → 60%**. O piso subiu muito, mas a variância entre execuções é de ~20 pontos, e os casos que falham mudam a cada rodada.
- **Problema:** com 10 casos, cada um vale 10 pontos — uma única resposta instável move o resultado mais que uma regressão real de prompt. Um gate assim fica vermelho por ruído e é ignorado em duas semanas, que é justamente o que o limiar de 90% queria evitar.
- **Causa:** duas somadas. (a) amostra pequena; (b) as asserções restantes que dependem de REDAÇÃO ("a resposta contém 'não reconheci'") reprovam paráfrases corretas — o mesmo defeito do IA-14, que já foi resolvido nos casos onde dava para checar estrutura.
- **Fix:** subir para 30–50 casos (reduz a variância por caso) e trocar o que sobrou de checagem textual por checagem estrutural (tools chamadas, argumentos, itens citados) ou por um juiz LLM com rubrica. **Benefício:** só então o número vira gate confiável e o limiar de 90% faz sentido.

### IA-16 · Restrição declarada só na conversa não tem rede estrutural — 🟠 Alto · M
- **Status:** 🟠 Aberto.
- **Achado:** a R5 e a anotação `conflita_com_perfil` derivam do PERFIL salvo. Quem diz "sou vegetariano" no chat, sem perfil, fica protegido apenas pelo prompt — e a bateria mediu 2/3 nesse caso.
- **Fix:** extrair restrições declaradas na conversa para o contexto do turno e alimentar a mesma anotação. **Benefício:** a barreira estrutural passa a cobrir o usuário anônimo, que é a maioria no refeitório.

### IA-17 · Condição de saúde: o corpo da resposta ainda prescreve — 🟠 Alto · M
- **Status:** 🔶 Parcial em `feat/motor-agente-onyx`. Em 23/08 a voz do aviso de restrição/alergia mudou de determinação ("você não pode comer") para relato ("com base no que você me contou, esse prato não é indicado, porque leva X"), o que move o assistente da posição de quem prescreve para a de quem cruza informação declarada com fato do prato. **Não medido ainda.** O risco residual segue sendo o corpo da resposta sobre condição clínica, que continua entregando conduta alimentar.
- **Achado:** o encaminhamento a médico/nutricionista passou a ser acrescentado em CÓDIGO (`pos_processar`), porque prompt e reminder reinjetado deram 0/3 de aderência. Mas o corpo da resposta segue entregando orientação dietética detalhada ("evite frituras", "prefira proteína e fibra", "coma devagar").
- **Problema:** recomendação nutricional individualizada é ato privativo de nutricionista (CFN). O disclaimer no rodapé reduz o risco, não elimina.
- **Fix:** restringir a resposta a "qual prato do cardápio combina melhor e por quê", sem lista de condutas alimentares.

### IA-18 · Modelo cita macro que não buscou — 🟡 Médio · P
- **Status:** 🟡 Aberto. Detectado pela R3 na bateria `honestidade`.
- **Achado:** pergunta sobre proteína → `comparar_pratos` devolve só o critério pedido → a resposta cita carboidrato, que nenhuma tool expôs.
- **Fix:** `comparar_pratos` devolver o conjunto completo de macros, ou o prompt exigir nova consulta antes de citar outro nutriente.


### IA-19 · Alimento do registro casa fora do cardápio — 🔴 Crítico · M
- **Status:** ✅ Corrigido em 24/08/2026.
- **Achado:** usuário disse "2 conchas de arroz"; o cardápio do dia tinha **Arroz Integral**;
  o registro resolveu para **arroz branco** (~328 kcal). O prato certo estava no contexto —
  a Lia tinha acabado de listá-lo — e mesmo assim o casamento foi para outro item da base.
- **Por que é crítico:** o valor entra em `consumos`, alimenta pontuação e o índice de
  resto-ingesta. Erro silencioso, com aparência de acerto.
- **Fix:** `registrar_consumo` deve preferir os itens do cardápio do dia antes de cair na
  base geral. Hoje resolve contra a base inteira sem esse viés.
- **Evidência:** [`evidencias/usabilidade-2026-08-24.md`](evidencias/usabilidade-2026-08-24.md), turno "confirma".

### IA-20 · Mesmo prato com dois valores na mesma conversa — 🟠 Alto · M
- **Status:** ✅ Corrigido em 24/08/2026.
- **Achado:** na recomendação, *Frango Grelhado — 165 kcal*; três turnos depois, no registro,
  *1 filé de frango — ~121 kcal*. Mesmo prato, mesma conversa, números diferentes.
- **Causa provável:** a recomendação lê o valor do **cardápio** e o registro recalcula pela
  **porção caseira**, sem cruzar as duas fontes. Relacionado a IA-19 e a IA-09.
- **Fix:** ao registrar item que está no cardápio do dia, usar a mesma procedência que a
  recomendação usou — ou declarar por que os números diferem.
- **Evidência:** turnos "declara alergia" e "confirma" na transcrição.

### IA-21 · Confirmação em laço: o registro nunca acontece — 🟠 Alto · P
- **Status:** 🔴 **Reproduzido em 27/08 e continua vivo — pior do que o registrado.** Bateria de 3 conversas: a conversa de registro fez 3 turnos e **nenhuma tool foi chamada**; `SELECT count(*) FROM consumos WHERE created_at > now() - interval '30 minutes'` = **0**. O usuário disse o que comeu, disse que sobrou arroz, e perguntou os pontos; a Lia exigiu a medida exata da sobra ("meia concha? uma colher?") e recusou até responder sobre pontos antes de obtê-la. É o ciclo que alimenta gamificação **e** o painel de desperdício: sem ele o dashboard do admin abre vazio. Ver **IA-25**.
- **Achado:** o usuário escreveu *"isso mesmo, pode registrar"* e a resposta foi
  *"Está correto? Se sim, é só me confirmar que eu salvo aqui"*. Ao fim das 6 mensagens,
  **nada foi gravado** — nem consumo, nem pontos.
- **Por que importa:** a pontuação é a moeda do produto. Um laço de confirmação transforma
  o fluxo principal em conversa sem efeito, e o usuário não tem como perceber.
- **Fix:** tratar confirmação explícita ("pode registrar", "isso mesmo", "confirmo") como
  `confirmado=True` no turno seguinte à prévia, em vez de pedir de novo. Candidato a
  barreira em código, não a regra de prompt — o modelo já tinha a prévia no contexto.
- **Evidência:** turnos "registra consumo" e "confirma" na transcrição.

### OPS-XX · nginx do front cacheia o IP da API para sempre — 🔴 Crítico · P
- **Status:** ✅ Corrigido em 24/08/2026.
- **Achado:** `proxy_pass http://api:8080/` com hostname literal faz o nginx resolver o nome
  **uma vez, no boot**, e guardar o IP. O container `web` subiu, gravou `172.21.0.5`, e o
  Docker depois deu esse IP ao `ai-worker`. Todo o front passou a receber **502**, com a tela
  dizendo *"Não foi possível carregar as unidades. O backend está rodando?"* — com o backend
  rodando e saudável.
- **Por que é crítico:** qualquer restart ou recriação da API reproduz isso em produção, e o
  sintoma aponta para o lugar errado. Só um restart do nginx corrige.
- **Fix:** `resolver 127.0.0.11 valid=10s;` e `proxy_pass` via variável, para forçar
  re-resolução em runtime:
  ```nginx
  resolver 127.0.0.11 valid=10s ipv6=off;
  set $upstream_api http://api:8080;
  proxy_pass $upstream_api/;
  ```
- **Evidência:** `connect() failed (111: Connection refused) ... upstream: "http://172.21.0.5:8080/unidades"`,
  com `docker inspect` mostrando 172.21.0.5 = `deploy-ai-worker-1` e a API em 172.21.0.6.

### OPS-YY · compose não repassava os provedores de LLM novos — ✅ Corrigido
- **Status:** ✅ Corrigido em 24/08/2026, no mesmo dia em que foi introduzido.
- **Achado:** OpenRouter e `openai_compat` entraram no código sem entrar no
  `docker-compose.yml`. Trocar `LLM_PROVIDER` no `.env` não tinha efeito nenhum dentro do
  container: ele caía calado no default `ollama` e falhava com
  `httpx.ConnectError: Temporary failure in name resolution`, que o usuário via como
  *"tive um problema para consultar as informações agora"*.
- **Agravante:** o `.env` que o compose lê é o de `deploy/`, não o da raiz. Configurar o da
  raiz não produz erro — produz silêncio.
- **Fix aplicado:** `OPENROUTER_*` e `LLM_BASE_URL`/`LLM_API_KEY`/`LLM_MODEL` repassados em
  `ai-worker` e `ai-api`.
- **Aberto ainda:** o worker deveria **recusar a subir** quando o provedor configurado não
  está alcançável, em vez de responder erro transitório a cada mensagem.

---

## TG — Telegram

### TG-01 · Canal bypassa toda a arquitetura v2 — 🟠 Alto · G
- **Achado:** `handle_update` roda o LLM dentro do processo `ai-api` (sem RabbitMQ), sem sessão no Postgres, sem idempotência, e **a regra contratual `primeira_do_dia` nunca é aplicada** (é calculada no Go).
- **Problema:** dois produtos diferentes sob a mesma marca — o Telegram viola a regra contratual do cliente e não escala; inferência bloqueia o pool do FastAPI.
- **Fix:** Telegram publica na mesma fila `chat.requests` via `POST /chat` do Go (vira só mais um front). **Benefício:** um único pipeline com as mesmas garantias em todos os canais.

### TG-02 · Estado do Telegram em RAM — 🟠 Alto · M (resolvido por TG-01)
- **Achado:** `_unidade_por_chat` e histórico em dicts de módulo.
- **Problema:** restart apaga unidade e contexto de todos; 2 réplicas de `ai-api` quebram o canal.
- **Fix:** persistir vínculo chat↔unidade/sessão no Postgres (cai de graça se TG-01 for feito). **Benefício:** restart e escala sem perda.

---

## API — Corretude e qualidade

### API-01 · Outbox: `FOR UPDATE SKIP LOCKED` sem transação — 🟠 Alto · P
- **Achado:** `FetchPendingOutbox` roda via `pool.Query` — o lock morre no fim da query, antes do `MarkOutboxPublished` (`store/outbox.go:19`).
- **Problema:** a garantia anunciada no comentário ("múltiplos relays sem dupla publicação") não existe; com 2 instâncias da API, eventos duplicam — o inbox salva hoje, mas quebra silenciosamente exatamente ao escalar.
- **Fix:** envolver fetch+publish+mark numa transação. **Benefício:** a garantia volta a ser verdadeira.

### API-02 · Idempotência: sem reserva de chave e na rota errada — 🟠 Alto · M
- **Achado:** `SaveIdempotent` grava só **depois** do handler (`middleware.go:62`) — duas requisições concorrentes com a mesma chave executam ambas; e o middleware só cobre `POST /chat`, não `/internal/consumo/registrar`, que é quem muta pontos.
- **Problema:** duplo-clique/retry conta a refeição duas vezes — pontos e desperdício dobrados.
- **Fix:** `INSERT` de reserva antes de processar (409/wait em conflito) e aplicar na rota de consumo. **Benefício:** o dado do KPI para de dobrar sob retry.

### API-03 · `idempotency_keys` sem GC — 🟡 Médio · P
- **Achado:** tabela cresce sem TTL/expurgo.
- **Problema:** crescimento ilimitado degrada o banco com o tempo.
- **Fix:** job de expurgo (>30 dias). **Benefício:** manutenção zero no longo prazo.

### API-04 · Listas de admin sem paginação + N+1 em SQL — 🟠 Alto · M
- **Achado:** `GET /admin/usuarios` faz SELECT sem LIMIT com subquery `count(*)` de consumos **por linha** (`store/usuario.go:149`); `ListAlimentos`, `ListUnidades`, `ListMedidasCaseiras` idem.
- **Problema:** degrada linearmente; com poucos milhares de usuários o dashboard cai.
- **Fix:** paginação (limit/offset ou keyset) + busca; trocar a subquery por JOIN agregado. **Benefício:** admin utilizável em escala real.

### API-05 · Zero auditoria de admin — 🟠 Alto · M
- **Achado:** nenhuma trilha de quem alterou cardápio, alimento ou unidade (impossível mesmo com o token único atual).
- **Problema:** "quem tirou a proteína de terça?" não tem resposta — requisito comum de cliente corporativo.
- **Fix:** tabela `audit_log` (quem, o quê, quando, antes/depois) preenchida nos handlers de admin; depende de SEG-03 para o "quem". **Benefício:** responsabilização e suporte pós-venda.

### API-06 · `/health` não checa dependências — 🟡 Médio · P
- **Achado:** responde `{"status":"ok"}` sem tocar Postgres nem RabbitMQ.
- **Problema:** reporta saudável com o banco fora — monitoramento cego.
- **Fix:** `/health` (liveness) + `/ready` (ping Postgres+Rabbit). **Benefício:** healthcheck que detecta falha de verdade.

### API-07 · Vazamento de `err.Error()` e 502 genérico — 🟡 Médio · P
- **Achado:** handlers de admin concatenam erro cru na resposta (`handlers_admin.go:212,244,270`); `handleChat` devolve 502 para qualquer falha, inclusive validação.
- **Problema:** detalhe de SQL vaza ao cliente; front não consegue distinguir erro de usuário de erro de sistema.
- **Fix:** mensagens genéricas + log interno; status codes corretos no chat. **Benefício:** segurança + UX de erro.

### API-08 · Housekeeping de build e runtime — ⚪ Baixo · P
- **Achado:** `go.mod` não-tidy (`x/crypto` como indirect sendo direto); imagem `debian:bookworm-slim` rodando como **root** para binário `CGO_ENABLED=0`; migrações no boot sem lock (corrida com `--scale api=2`).
- **Problema:** superfície de container maior que o necessário; migração concorrente pode falhar feio.
- **Fix:** `go mod tidy`; distroless/scratch + user não-root; advisory lock (`pg_advisory_lock`) na migração. **Benefício:** higiene barata.

---

## WEB — Front

### WEB-01 · Cliente nunca vê o cardápio em tela — 🟠 Alto · M
- **Achado:** `getCardapio()` e o tipo `Prato` existem e são **código morto** (`src/lib/api.ts:31`, `src/types.ts:14`) — o cardápio só sai via Lia.
- **Problema:** cada "o que tem hoje?" custa uma chamada de LLM; usuário sem paciência para chat não tem acesso à informação mais básica do produto.
- **Fix:** tela/painel de cardápio do dia (o endpoint já existe), com o chat como camada de recomendação por cima. **Benefício:** menos custo de token, mais acessibilidade, primeira coisa que o usuário quer.

### WEB-02 · Sem fluxo guiado de registro de consumo/sobra — 🟠 Alto · M
- **Achado:** registro é 100% texto livre no chat; nenhuma das 4 sugestões do chat ensina a registrar; a única explicação está no Ranking (aonde o usuário só chega depois de pontuar).
- **Problema:** o ciclo de descoberta está quebrado — e é esse registro que alimenta a gamificação **e** o dashboard de desperdício (o KPI vendável). Dado que não entra = produto que não prova valor.
- **Fix:** CTA pós-almoço ("registrar minha refeição") com fluxo guiado (chips de alimentos do cardápio do dia + medidas), mantendo o texto livre como atalho. **Benefício:** taxa de registro sobe → dashboard do admin tem dado → renovação.

### WEB-03 · Restrições/alergias em texto livre — 🟠 Alto · M
- **Status:** 🔶 Parcial em `afa364a`. Os três campos "separados por vírgula" viraram entrada por etiquetas (`src/ui/CampoTags.tsx`), com sugestões. **A causa não foi resolvida:** as sugestões são exemplos, não vocabulário fechado — o casamento é contra o que o gestor cadastrou em `restricoes_atendidas`, que varia por unidade. Ver **IA-22**, que mede o tamanho real do problema.
- **Achado:** três campos "separados por vírgula" no cadastro (`Cadastro.tsx:335`).
- **Problema:** "não posso comer leite" nunca vai bater com o matching determinístico de `restricoes_atendidas` — a personalização, o coração do produto, falha silenciosamente para o leigo.
- **Fix:** chips/checkboxes com vocabulário controlado (o mesmo usado no cadastro de alimentos), com campo livre opcional. **Benefício:** o filtro determinístico passa a funcionar de verdade.

### WEB-04 · Chat não recarrega histórico no refresh — 🟡 Médio · P/M
- **Achado:** `ChatRoute.tsx` só chama `getSaudacao()` no mount; o backend mantém sessão e contexto.
- **Problema:** tela zera, mas a Lia responde "como combinamos" para uma conversa que o usuário não vê — parece bug/assombração.
- **Fix:** endpoint de histórico da sessão + hidratação no mount. **Benefício:** continuidade percebida = confiança.

### WEB-05 · Mobile quebrado em pontos-chave + sem PWA — 🟠 Alto · M
- **Status:** ✅ Corrigido em `feat/motor-agente-onyx` (`afa364a`). `100dvh`, `env(safe-area-inset-*)` com `viewport-fit=cover`, `theme-color`, alvos de 40px, inputs de 16px (abaixo disso o Safari dá zoom ao focar), favicon SVG. Header com 5 links `nowrap` deixou de existir: virou lateral fixa no desktop e gaveta no celular. Falta só `manifest.json` para instalar como PWA.
- **Achado:** header com 5 ações `nowrap` sem `flex-wrap` corta em 390px (`styles.css:146`); `height:100vh` no chat (Safari iOS cobre o composer; sem `dvh`/safe-area); admin desktop-only sem aviso; **não existe `public/`** — sem favicon/manifest.
- **Problema:** o uso real é no celular na fila do refeitório; botões cortados e composer coberto são falha de missão crítica.
- **Fix:** `flex-wrap`+menu overflow no header, `100dvh`+safe-area, media queries no admin (ou aviso), favicon+manifest PWA. **Benefício:** o produto funciona onde é usado.

### WEB-06 · Admin sem route guard nem tratamento de 401 — 🟠 Alto · P (depende de SEG-03)
- **Achado:** `/admin/u/1/cardapio` abre para qualquer um (só as chamadas falham); sem redirect ao receber 401; sem logout.
- **Problema:** UX confusa e sensação de insegurança; com SEG-03 vira tela de login de verdade.
- **Fix:** guard de rota + interceptador de 401 com redirect + logout. **Benefício:** fluxo de admin com começo, meio e fim.

### WEB-07 · Camada de API duplicada e frágil — 🟡 Médio · M
- **Status:** 🔶 Parcial em `afa364a`. `adminFetch` e `adminRequest` eram quase idênticas e só uma preservava o status HTTP, então metade das telas de gestão não distinguia "token errado" de "servidor fora"; agora é uma função só e todo erro chega como `ApiError`. **Continua aberto:** `fetch` sem timeout/AbortController e sem cancelamento no unmount.
- **Achado:** `adminFetch` e `adminRequest` quase idênticos e inconsistentes (`api.ts:78,199`); detecção de 404 por `err.message.includes("(404)")` (`Cadastro.tsx:79`); `fetch` sem timeout/AbortController; sem cancelamento no unmount.
- **Problema:** string-matching de erro quebra silenciosamente; requisições penduradas e `setState` pós-unmount.
- **Fix:** unificar num client único com `ApiError` tipado (status), timeout e abort. **Benefício:** base sólida para toda feature futura do front.

### WEB-08 · Race no editor de cardápio — 🟡 Médio · P
- **Achado:** `salvarDia()` envia o array completo do dia lendo o estado atual (`CardapioEditor.tsx:49`); dois cliques rápidos → segundo PUT sobrescreve o primeiro (item some); flag `salvando` existe mas os handlers não a consultam.
- **Problema:** perda silenciosa de item do cardápio — o admin não percebe e o refeitório serve sem o prato no sistema.
- **Fix:** desabilitar controles durante o save (consultar o flag) ou fila de mutações. **Benefício:** dado do cardápio confiável.

### WEB-09 · Mensagens de erro com texto de desenvolvedor — 🟡 Médio · P
- **Status:** ✅ Corrigido em `afa364a`. `src/lib/mensagens.ts` traduz `ApiError` por status; toda tela passou a mandar o detalhe técnico para `console.error`. "O backend está rodando?" e "Rode o seed do backend" não existem mais.
- **Achado:** "O backend está rodando?", "Rode o seed do backend" (`UnidadeSelector.tsx:15,51`); erros de admin exibem corpo cru da resposta HTTP.
- **Problema:** texto de dev na tela do cliente final mina a percepção de produto pronto.
- **Fix:** mensagens humanas + retry; detalhes técnicos só no console. **Benefício:** polish barato com efeito direto na confiança.

### WEB-10 · Acessibilidade e affordances — 🟡 Médio · M
- **Status:** ✅ Corrigido em `afa364a`. `:focus-visible` global, `aria-label` em todo botão de ícone, `role="log"`/`aria-live` na conversa, `aria-pressed` nos alternadores. Os emoji-ícone (`➤ ★ × 🏆 ⭐ 🙂`) viraram `src/ui/Icone.tsx` (SVG de traço único). Emoji só dentro do texto que a Lia escreve. Falta o diálogo de confirmação próprio — `window.confirm` ainda é usado em UnidadesAdmin e CardapioEditor.
- **Achado:** 3 atributos ARIA no app inteiro; sem `:focus-visible` em botões; ícones em emoji (`➤`, `★`, `×`) que variam por SO; `window.confirm` nativo; sem skeleton loading.
- **Problema:** navegação por teclado invisível; aparência inconsistente entre dispositivos denuncia protótipo.
- **Fix:** focus states, `aria-label` nos botões de ícone, SVGs no lugar de emoji, confirm dialog próprio. **Benefício:** acabamento de produto (e conformidade básica).

### WEB-11 · Marca e cores hardcoded (sem white-label) — 🟡 Médio · M/G
- **Status:** ✅ Corrigido em `afa364a`. `src/brand.ts` concentra nome do assistente, produto e paleta; `aplicarTema()` sobrescreve os tokens CSS em runtime. Nenhum componente escreve "Lia" nem `#hex`. Falta o endpoint que serve tema por unidade — o seam está aberto do lado do front.
- **Achado:** "Lia" e a paleta estão fixos em `styles.css` e nos JSX; nada é por tenant.
- **Problema:** o segundo cliente exige fork ou refactor — exatamente o anti-padrão que a OPOLZ quer evitar.
- **Fix:** tokens de tema + nome do assistente vindos de config por unidade/tenant (o CSS já usa custom properties — meio caminho andado). **Benefício:** clonar para o cliente 2 vira configuração, não código.

### WEB-12 · Zero testes, lint e CI no front — 🟡 Médio · M
- **Achado:** nenhum `.test.tsx`, sem vitest/testing-library/playwright, sem ESLint/Prettier, `.github/` sem workflows.
- **Problema:** nada impede merge que quebra o build; caminho crítico sem regressão automatizada.
- **Fix:** CI com typecheck+build+lint; 1 teste E2E do caminho crítico (escolher unidade → perguntar → registrar → ver pontos). **Benefício:** rede de segurança mínima para evoluir rápido.

---

---

## Sessão de 2026-08-27 — o que foi consertado e o que ela ensinou

> Origem: uma conversa real de um usuário, tratada como **baseline de interação**. Ele pediu
> recomendação com restrição por exclusão e meta numérica, e a Lia falhou duas vezes seguidas
> dizendo ao CLIENTE que "o sistema está muito rigoroso" e "parece que não está funcionando".
> Investigando os logs achamos quatro defeitos independentes — e um quinto, mais grave, que
> ninguém tinha visto. Corrigidos em `02c4528` (17 agentes; suíte 546 testes, zero falha).
>
> **Como reproduzir qualquer coisa daqui.** A suíte não gasta API: `pytest.ini` tem
> `addopts = -m "not llm"` e os dois arquivos de `tests/eval/` carregam `pytestmark =
> pytest.mark.llm`. Rodar:
> ```
> cd deploy && docker compose build -q ai-worker && docker compose run --rm --no-deps -T \
>   --entrypoint sh ai-worker -c 'pip install -q pytest >/dev/null 2>&1 && \
>   python -m pytest tests -q --ignore=tests/eval'
> ```
> Nesta máquina o `docker` é snap e o CLI às vezes precisa de pty — se a saída vier vazia com
> rc=1, envolva em `script -qec '<comando>' /dev/null`. O snap também só faz bind-mount de
> caminhos dentro de `$HOME`: montar `/tmp` monta vazio, sem erro.

### IA-22 · Alergia não olhava os ingredientes — 🔴 Crítico · M — ✅ Corrigido
- **Status:** ✅ Corrigido em `02c4528` (`app/agent/dominio/refeitorio/filters.py`).
- **Achado:** `prato_seguro_para_alergias` montava o conjunto de alérgenos só a partir do campo
  `alergenos` e **nunca lia `ingredientes`**. Medido no banco: **21 dos 29 alimentos têm
  `alergenos` vazio (72%)**, e para esses a função devolvia `True` incondicionalmente.
  Evidência direta, rodando o filtro contra o cardápio real:
  ```
  prato_seguro_para_alergias({"alergenos": [], "ingredientes": ["carne bovina","cebola","óleo"]},
                             ["carne bovina"])  ->  True     # Bife Acebolado, id 133
  ```
  Alérgico a alho recebia "Arroz Branco" (`ingredientes: arroz, alho, óleo`) como seguro.
- **Problema:** derrubava as **duas** barreiras de uma vez, porque `filtrar_pratos` (tools.py) e
  `conflitos_com_perfil` (filters.py) chamam a mesma função — nem o filtro excluía, nem o aviso
  que viaja junto do item na listagem era emitido. É a falha mais cara que este produto tem.
- **Fix aplicado:** cruza `alergenos` **e** `ingredientes`, por **palavra inteira** — substring
  faria `"sal"` barrar `"salmão"`. Canoniza plural e acento nos dois lados da comparação
  (noz/nozes, camarão/camarões, amendoim/amendoins, pão/pães). A assimetria está escrita no
  código: falso positivo custa uma opção a menos, falso negativo custa uma reação alérgica.
  Nova `culpados_por_alergia` devolve o par (termo declarado, termo do prato), para a mensagem
  citar a causa real em vez de chutar.
- **Nota de projeto:** entrou uma tabela `_GRUPOS` pequena (`frutos do mar` → camarão, lula…)
  porque `Perfil.tsx` oferece esse chip num clique sob a promessa de que a Lia nunca sugere
  nada da lista — e a expressão não aparece em ficha nenhuma. **É tabela de língua, não
  taxonomia de alimento**, e vale só para alergia (barreira em código). Restrição/preferência
  aberta continua sendo julgamento do modelo sobre os ingredientes, por decisão de produto.
- **Regressão:** `tests/test_alergia_ingredientes.py`, `tests/test_alergia_plural_e_grupo.py`.

### IA-23 · `filtrar_pratos` mentia com confiança — 🔴 Crítico · M — ✅ Corrigido
- **Status:** ✅ Corrigido em `02c4528` (`tools.py`).
- **Achado:** a tool tem **dois vocabulários** e não avisava qual é qual. `restricoes` é
  **fechado** (só casa com o que o catálogo declarou em `restricoes_atendidas`, casamento
  positivo: sem declaração ⇒ `False`); `preferencias` é **aberto** (busca em `ingredientes`).
  O modelo mandou uma exclusão aberta no campo fechado. Medido contra o cardápio real:
  ```
  restricoes='sem carne vermelha'  -> VAZIO          (garantido, para qualquer cardápio)
  preferencias='carne bovina'      -> ['Bife Acebolado']   (o ingrediente É localizável)
  ```
  Vocabulário real da unidade 1: `sem lactose(22) · sem gluten(20) · vegetariano(18) ·
  vegano(15) · low carb(2) · proteico(1)`. "sem carne vermelha" não existe e não tem equivalência.
- **Problema:** a tool devolvia `"Nenhum prato do cardápio atende a esses critérios. NÃO sugira
  nada fora do cardápio..."` — um falso negativo com ar de autoridade. O modelo obedeceu,
  corretamente, e ficou preso; sem saber a causa, **inventou a explicação** e a entregou ao
  cliente. Nos logs: 5 chamadas idênticas no T2 e 5 no T3.
- **Fix aplicado:** a tool passa a conhecer o próprio vocabulário (lido do catálogo do dia —
  dado por unidade, nada hardcoded) e a distinguir os dois fracassos: *"filtrei e nada atende"*
  vs *"não sei filtrar por esse termo"*. No segundo caso devolve **roteamento** — diz o que
  filtra e manda o modelo decidir sobre os `ingredientes` que ele já recebe —, e a nota é
  explícita em **não** afirmar que os pratos roteados atendem ao termo.
- **Regressão:** `tests/test_filtrar_vocabulario.py`, `tests/test_roteamento_honesto.py`.

### IA-24 · O agente não sabia que dia era hoje — 🟠 Alto · P — ✅ Corrigido
- **Status:** ✅ Corrigido em `02c4528` (`motor/relogio.py` novo, `motor/llm.py`, `config.py`).
- **Achado:** `grep -rE "date.today|datetime.now|strftime|utcnow" apps/ai/app` retornava **uma
  única ocorrência**, em `tools.py`, do lado servidor. **Nada injetava a data no contexto do
  modelo.** Enquanto ele só dizia `dia: 'hoje'` funcionava (quem resolvia era a tool); ao
  precisar **nomear** uma data (`cardapio_da_semana(data_alvo=...)`) ele só podia adivinhar.
  Adivinhou `2026-05-28` — que existe no banco como resto de seed — e apresentou como cardápio
  de hoje. `nota_do_sistema` de `listar_pratos_do_dia` dizia explicitamente para não fazer isso.
- **Fix aplicado:** a data vai no **system**, nunca em reminder (aquele canal viaja na mensagem
  do usuário, é spoofável, e a invariante de `motor/reminders.py` proíbe reminder introduzir
  dado novo — alguém escreveria `NOTA DO SISTEMA: hoje é 28/05`). Fica **fora do bloco
  cacheado** (`nota_extra`), e o **dia entra na chave do cache de executores**, senão a data
  congelaria no boot — pior que não ter data, porque o modelo passa a errar com confiança.
  `motor/relogio.py` é a fonte única de "hoje", compartilhada com as tools: duas contas
  divergiriam na virada do dia e o bug só apareceria à noite.
- **Inspiração:** Onyx `backend/onyx/prompts/prompt_utils.py` + `prompt_template.py` (tag
  `{{CURRENT_DATETIME}}` substituída centralmente). Divergimos de propósito em dois pontos:
  eles não têm cache de prefixo a proteger, e usam `datetime.now()` **sem fuso**.
- **Aberto:** o fuso é `FUSO_HORARIO` global. Com unidades em fusos diferentes vira erro na
  virada do dia — o ponto de escopo está documentado em `relogio.py`.

### IA-25 · Observações de tool não atravessam o turno — 🟠 Alto · M — 🔶 Parcial
- **Status:** 🔶 Parcial em `02c4528` (`motor/memoria.py` novo, `observacao.py`, `turn.py`).
- **Achado:** `SELECT papel, count(*) FROM mensagens GROUP BY papel` devolve só `user` e
  `assistant`. As observações das tools morrem com o `ContextVar` no fim do turno; a memoização
  (`COMPRIMIR_REPETICOES`) só vale **dentro** de um turno. Por isso, depois de o usuário
  esclarecer "isso, como peixe e frango", o modelo repetiu a **mesma consulta morta** 5 vezes —
  para ele era a primeira. Ele até escreveu "vou tentar de outro jeito" no turno anterior, sem
  mecanismo que carregasse "esse caminho é beco sem saída".
- **Fix aplicado:** consultas que deram em nada atravessam o turno, de forma enxuta (não o
  retorno inteiro, que incharia contexto e custo). O texto que carrega isso **não** autoriza
  afrouxar critério — os argumentos de `filtrar_pratos` **são** a barreira em código.
- **Aberto:** só o Python guarda isso; nada é persistido. Reinício de worker esquece.
- **Regressão:** `tests/test_observacoes_entre_turnos.py`, `tests/test_becos_nao_engolem_o_vivo.py`.

### IA-26 · Preflight reprovava modelo bom na partida — 🔴 Crítico · P — ✅ Corrigido
- **Status:** ✅ Corrigido em `02c4528` (`motor/preflight.py`, `workers/chat_worker.py`).
- **Achado:** `chat_worker` construía a sonda com `max_tokens=16`. Na Anthropic a chamada de
  tool volta como **bloco estruturado** e o nome da tool + o JSON dos argumentos são tokens de
  **saída**: com teto de 16 a resposta truncava antes de o bloco fechar, `tool_calls` vinha
  vazio e a sonda concluía *"o provedor respondeu, mas o modelo NÃO chamou a tool"* — **sobre um
  modelo que chama**. Medido:
  ```
  max_tokens=16  -> reprova     max_tokens=64 -> passa     max_tokens=256 -> passa
  ```
- **Problema:** reprovaria **qualquer** modelo Anthropic bom, e a mensagem de erro acusava o
  modelo em vez da sonda. Custou uma sessão inteira de diagnóstico no provedor errado.
- **Fix aplicado:** o teto virou `preflight.MAX_TOKENS_SONDA = 256`, declarado por quem conhece
  o próprio custo; o worker usa a constante em vez de um número solto. A sonda avisa no log
  quando recebe teto abaixo do que precisa, em vez de reprovar em silêncio.
- **Regressão:** `tests/test_preflight.py` — inclui um teste que falha se alguém voltar a
  escrever número literal no worker.

### IA-27 · R3 mede certo e não bloqueia — 🟠 Alto · P — 🔴 Aberto
- **Achado:** na bateria de 27/08 a **R3 disparou nos dois turnos que importavam**, e acertou:
  ```
  R3 | números citados que nenhuma tool expôs: [22.0, 40.0]
  R3 | números citados que nenhuma tool expôs: [20.0, 0.0, 1.0, 13.0, 36.0, 1.0, 0.0, 2.0, 22.0, 23.0]
  ```
  A resposta entregue dizia *"Tilápia: 1 posta média (100g) = ~150 kcal | ~20g proteína"*.
  A tabela diz **98 kcal e 22,9g** (`alimentos.id=134`, ancorado na referência #5 Peixe Cozido).
  A Lia também sugeriu **pão francês**, que não está no cardápio. No mesmo turno chamou
  `detalhar_prato(prato_id=1)` — id 1 é **Frango Grelhado**, não a Tilápia (134).
- **Problema:** `VALIDACAO_BLOQUEANTE` tem só `R5-prato-conflita-com-perfil`, então a R3 vira
  log e a resposta inventada chega ao usuário. Num produto que se define por **não chutar
  número**, é a promessa central quebrada no turno em que a pessoa mais precisa do número —
  o que ela vai usar no balcão.
- **Fix:** promover **só a R3** a bloqueante. O IA-11 recomenda esperar por falso positivo alto,
  mas foi a **R2** que errou duas vezes na bateria (`'nutricao aproximada'` e `'nao temos frango
  nem peixe'` acusados como prato fora do cardápio), não a R3. Medir R2 e R3 separadamente antes
  de decidir por ambas. Junto: `consultar_medidas_caseiras` foi chamada com `{}` vazio e deve
  recusar; e o prompt precisa amarrar `prato_id` ao prato citado.

### IA-28 · `Alvo` não distingue meta de TETO — 🟠 Alto · M — 🔴 Aberto
- **Achado:** em `porcionamento.py`, `ler_meta("quero no maximo 500 kcal")` produz um alvo a
  **atingir**: `montar` devolve 510 kcal com `atingiu: True`. "No máximo 30g de carboidrato"
  devolve 32,3g.
- **Problema:** num produto de nutrição, meta calórica e de carboidrato costumam ser **teto**,
  não piso. Entregar 510 quando a pessoa pediu no máximo 500 é errar na direção que importa.
- **Fix:** campo de natureza em `Alvo` (piso/teto/faixa), parâmetro na tool e mudança de
  semântica em `montar`/`nota_para_o_modelo`. É desenho de produto. O módulo **ainda não está
  ligado a tool nenhuma** (`grep -rn "montar_prato" apps/ai` não retorna nada fora de teste),
  então dá para resolver antes de expor.

### WEB-13 · Não há área de login, só um bloco escondido no perfil — 🟠 Alto · P
- **Achado:** o fluxo existe (`Perfil.tsx`, bloco "Já tenho cadastro" → `POST /usuarios/login`),
  mas a lateral oferece só **"Criar meu perfil"** para quem está anônimo. Quem já tem cadastro
  não encontra a porta.
- **Problema:** o usuário perde o histórico e a pontuação por não achar onde entrar; parece que
  o produto não tem login.
- **Fix:** entrada explícita de "Entrar" na lateral e uma rota própria. **Depende de SEG-01**
  para virar autenticação de verdade — hoje o "login" confere a credencial e **joga o resultado
  fora** (`handleLoginUsuario` termina em `writeJSON(usuarioComPerfil(u))`, sem emitir nada), e
  o front passa a mandar `usuario_id` cru do `localStorage`.

### PROD-03 · Usuário anônimo tratado como erro, não como caso de primeira classe — 🟠 Alto · M
- **Achado:** `meus_pontos()` responde *"Usuário não identificado nesta sessão — para acumular
  pontos é preciso criar um perfil"*, e `meu_perfil` depende de `usuario_id`. Na bateria de
  27/08 as três conversas foram anônimas e a meta dita no prompt ("22g de proteína, 40g de
  carboidrato") não tinha onde morar.
- **Problema:** perfil salvo deve **melhorar** a recomendação, nunca **habilitar**. Exigir
  cadastro para o produto funcionar é pedir compromisso antes de entregar valor.
- **Fix:** espelhar o Onyx. Em `backend/onyx/auth/anonymous_user.py` o anônimo **não é `None`**:
  é um `UserInfo` completo com `account_type=ANONYMOUS` e um `UserPersonalization`
  (`name`, `memories`, `user_preferences`) vindo de um KV. Personalização desacoplada de
  identidade faz o caminho anônimo ser **o mesmo código** do logado, e o cadastro vira upgrade.
  Aqui provavelmente mora na sessão do Postgres, que já é escopada e já expira — **precisa
  casar com IA-25** para não virarem dois mecanismos para a mesma coisa.

### PROD-04 · A conversa não conduz quem não sabe pedir — 🟡 Médio · M
- **Achado:** bateria de 27/08, persona "seu João" (leigo, frases curtas). No `"oi"` a Lia pediu
  restrições **antes de mostrar qualquer coisa** — quem chegou com fome leva um formulário. E o
  `"pode ser isso mesmo"` quebrou: ela ofereceu escolher entre "pedir o Bife" e "calcular a
  porção", e emendou *"sobrou algo no prato?"*, misturando recomendação com registro de consumo.
- **Problema:** é a persona majoritária do refeitório. Ela desiste na segunda pergunta.
- **Fix:** mostrar o cardápio primeiro e perguntar restrição depois (ou junto), e separar no
  prompt o estado "recomendando" do estado "registrando" — hoje eles se misturam numa
  confirmação ambígua.


## OPS — Deploy e operação

### OPS-01 · Sem TLS e com portas de infra expostas — 🔴 Crítico · P/M
- **Achado:** nginx `:80` sem HTTPS/HSTS; Postgres, RabbitMQ (5672+UI 15672), api e ai-api publicados em `0.0.0.0` no compose; webhook do Telegram **exige** HTTPS (o canal nem funciona hoje).
- **Problema:** num VPS sem firewall, banco e fila ficam na internet; tráfego (com PII de saúde) em claro.
- **Fix:** reverse proxy com TLS automático (Caddy, ~10 linhas), bind das portas internas em `127.0.0.1:`, firewall. **Benefício:** requisito de produção nº 1 fechado num dia.

### OPS-02 · RabbitMQ sem volume e credenciais hardcoded — 🟠 Alto · P
- **Achado:** sem volume (filas duráveis e DLQ perdidas em qualquer recreate); `amqp://guest:guest@…` **hardcoded** no compose (`deploy/docker-compose.yml:46,76,90`) — não dá nem para trocar por env.
- **Problema:** perda de mensagens de outbox em trânsito num restart; credencial default conhecida com porta exposta.
- **Fix:** volume nomeado + credenciais via env em todos os serviços. **Benefício:** durabilidade real das garantias de fila que o código já implementa.

### OPS-03 · Restart policies e healthchecks errados — 🟠 Alto · P
- **Achado:** `restart: "no"` em postgres/rabbitmq/ollama; `on-failure:5` nos apps (após 5 crashes, desiste para sempre); `ai-worker`/`api-worker` herdam healthcheck HTTP dos Dockerfiles mas não expõem HTTP — eternamente `unhealthy` (o comentário diz que o compose sobrescreve; não sobrescreve).
- **Problema:** reboot do VPS = sistema morto até intervenção manual; workers parados silenciosamente após falhas transitórias.
- **Fix:** `unless-stopped` na infra, healthcheck de processo/fila nos workers, remover o limite de 5. **Benefício:** o sistema volta sozinho.

### OPS-04 · Zero backup de Postgres — 🔴 Crítico · P
- **Achado:** só o volume `pg_data` local; sem dump, cron, WAL ou snapshot.
- **Problema:** um `docker volume rm` ou disco corrompido apaga cardápios, usuários, gamificação e histórico de desperdício do cliente — fim do contrato.
- **Fix:** `pg_dump` diário com retenção (7d/4sem) + upload externo + **teste de restore documentado**. **Benefício:** o dado do cliente sobrevive a acidente.

### OPS-05 · Sem CI — 🟠 Alto · P
- **Achado:** `.github/` só tem CODEOWNERS e template de PR; os testes que existem (`gamificacao_test.go`, `test-integration.sh` com Postgres descartável) não rodam automaticamente.
- **Problema:** os bons testes de integração já escritos não protegem nada.
- **Fix:** workflow com `go vet` + `go test` + `test-integration.sh` + `npm run typecheck && build`. **Benefício:** aproveita investimento já feito; portão de qualidade no PR.

### OPS-06 · Zero observabilidade — 🟠 Alto · M
- **Achado:** logs `slog`/JSON ok, mas nenhuma métrica (`prometheus|otel` = 0 hits), sem alerta de DLQ/outbox, sem correlação do `request_id` Go↔Python, sem custo de token por sessão.
- **Problema:** ninguém saberá que a DLQ encheu, que o relay parou ou que o custo de API explodiu — até o cliente ligar.
- **Fix:** `/metrics` Prometheus (profundidade de fila, DLQ, latência p95, tokens/turno), alerta simples (mesmo que um cron+Telegram), correlation id propagado no worker Python. **Benefício:** operar 1+ clientes sem adivinhação.

### OPS-07 · Seed de demo vs bootstrap de cliente; release sem versão — 🟡 Médio · M
- **Achado:** `api-seed` injeta 2 unidades fictícias (rodar em produção suja o banco do cliente); build das imagens na máquina de destino; `ollama:latest` mutável; CHANGELOG inteiro em `[Unreleased]`, única tag `mvp-v1`.
- **Problema:** sem distinção demo/produção nem versão de release, não há rollback nem reprodutibilidade de instalação.
- **Fix:** separar `seed-demo` de `bootstrap` (unidade real + admin inicial), registry de imagens com tags, tag de release por deploy. **Benefício:** instalação de cliente repetível — pré-requisito do modelo de negócio da OPOLZ.

---

## PROD — Produto e dados

### PROD-01 · Base nutricional incompleta e não conferida — 🟠 Alto · M
- **Achado:** 144 alimentos/344 porções verificados no seed; o ETL dos ~600 do PDF (`apps/ai/app/nutrition/etl.py`) nunca rodou (em `docs/sources/` só há um README) e o CHANGELOG pede "passe de conferência dos números".
- **Problema:** alimento fora da base cai no fallback de 100g — pontuação e desperdício ficam imprecisos justamente nos itens não cobertos.
- **Fix:** rodar o ETL com o PDF + chave Anthropic, conferência por amostragem (idealmente da nutricionista), merge no seed. **Benefício:** cobertura do universo real de buffet; melhor precisão do KPI.

### PROD-02 · RAG com 2 chunks — decidir o destino — 🟡 Médio · P/M
- **Achado:** o índice inteiro tem 2 chunks (dois guias curtos do seed); a tool `buscar_informacao` ocupa ~170 tokens de schema por chamada sem entregar valor; a informação útil vem das tools SQL.
- **Problema:** infraestrutura paga (Ollama para embeddings) e superfície de prompt para um recurso vazio.
- **Fix:** decidir — ou popular com conteúdo que só o RAG serve bem (FAQs por unidade, políticas do refeitório, guias longos), ou remover a tool até lá. **Benefício:** ou o RAG vira feature, ou o agente fica mais barato e simples.

---

*Gerado a partir da revisão de produto de 2026-08-13. Relatório executivo com precificação: artifact "Menu-AI (Lia) — Revisão de Produto e Precificação".*
