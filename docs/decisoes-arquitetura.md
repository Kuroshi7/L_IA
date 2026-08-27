# Decisões de arquitetura — o que foi decidido, e por quê

> Para quem chega depois (pessoa ou agente): o **quê** está no código, o **porquê**
> está aqui. Cada decisão traz o que a motivou e o que a faria mudar.

## O objetivo que orienta tudo

O `motor/` precisa servir a **outro produto** sem reescrita. O refeitório é o
primeiro domínio, não o único. Toda decisão abaixo passa por esse filtro.

Isso não é aspiração escrita em documento: está **sob teste**.
`tests/test_fronteira_motor.py` reprova import ou vocabulário de domínio dentro
de `motor/`, e `tests/test_portabilidade_motor.py` reprova campo de perfil sem
consumidor. Os dois já pegaram erro real — inclusive vocabulário de refeitório
deixado num docstring do próprio motor.

**A fronteira:** `motor/` não importa nada de `dominio/`; `dominio/` importa do
motor. `PerfilDeDominio` é a única superfície entre os dois. Trocar de produto
significa escrever outro perfil.

## Core vs domínio — onde cada coisa mora

| vive no `motor/` | vive no `dominio/` |
|---|---|
| classificar falha do provedor (`erros.py`) | quais tools existem |
| verificar provedor na partida (`preflight.py`) | o que cada frase de erro diz |
| tool que falha não derruba o turno (`tools.py`) | quando um reminder dispara |
| planejar antes de agir (`planejamento.py`) | o que está dentro do escopo |
| posicionar reminders no fim do contexto | o texto dos reminders |

Regra prática: se a resposta muda ao trocar refeitório por outro produto, é
domínio.

## Decisões

### Falha do modelo é classificada, não genérica

Todo erro colapsava numa frase só: *"tente de novo em instantes"*. Para rate
limit é verdade; para chave errada ou cota esgotada é mentira, e a pessoa repete
para sempre. Visto em produção-de-teste: seis mensagens seguidas assim.

`motor/erros.py` classifica por **status HTTP e nome da exceção**, sem importar
SDK de provedor — importar acoplaria o motor à lista de provedores que
`provedores.py` existe justamente para desacoplar.

O motor decide se insistir adianta; **a frase é do domínio**. Um campo novo no
perfil, não cinco: o usuário só precisa distinguir "espera" de "isso não passa".

> A distinção que motivou o módulo: `429` chega tanto para "20 por minuto"
> quanto para "1000 por dia". O primeiro passa em segundos; o segundo não passa
> hoje.

### O worker recusa subir se o provedor não responde

Consumir fila sem conseguir responder é pior que não subir: a mensagem do
usuário some e o operador não recebe sinal. O `prewarm` que existia não cobre
isso — pula inteiro para provedor que não é Ollama e só emite `warning`.

`motor/preflight.py` roda antes de tocar na fila e verifica duas coisas:
alcançabilidade **e tool calling**. A segunda entrou como requisito porque a
falha dela não parece falha — o modelo responde texto plausível e alucina o dado
que deveria ter buscado.

Desligável por `PREFLIGHT_OBRIGATORIO=false`, para desenvolvimento sem chave.

### Tool que estoura devolve texto ao modelo

Medido: uma exceção na tool aborta o grafo inteiro; o usuário recebia erro
genérico e o modelo nunca sabia que a busca falhou — nem tinha chance de
contornar.

Dois níveis, como no Onyx: `ErroDeTool` carrega a frase que o domínio escreveu;
qualquer outra exceção vira aviso genérico.

**Desvio deliberado do Onyx:** eles interpolam `str(e)` na mensagem que o modelo
lê. Não fazemos. Exceção de banco carrega host e credencial, e o modelo é
instruído a explicar a situação ao usuário. O erro real fica no log.

Sinais de controle do motor (`PrazoEsgotado`) atravessam a blindagem intactos —
engolir "pare agora" transformaria em "responda que deu erro".

### O que deve sempre acontecer é código, não prompt

Aviso legal obrigatório, validação, guardrail: `pos_processar` e `regras`.
Medido: pedir ao prompt deu **0 de 3** de aderência mesmo com reminder
reinjetado, e exigência regulatória não admite "quase sempre".

O corolário aparece três vezes no projeto: **instrução mais longa não compra
aderência.** Contexto extra compete com a instrução pela atenção do modelo.

### Regra que o modelo precisa lembrar vai para o fim do contexto

Reminders existem para isso. Retorno de tool fica enterrado no histórico do
turno seguinte; reminder é reposicionado a cada turno.

**Invariante:** todo reminder declara uma `regra_de_origem` que precisa aparecer
**literalmente** no system prompt — há teste. Reminder repõe o que já vale,
nunca concede o que o system não autoriza.

### Precedência de dado: o específico vence o genérico

Quem diz "arroz" num refeitório que serviu "Arroz Integral" quis dizer o
integral. A busca por similaridade na base geral devolvia o arroz branco, com
outro valor calórico — e isso ia para pontuação e índice de desperdício.

O cardápio do dia tem precedência. O casamento é **conservador de propósito**:
igualdade ou palavra inteira, nunca substring solta. Similaridade difusa aqui
trocaria um erro conhecido por outro imprevisível.

Consequência: todo número sai com `procedencia`, e divergência acima de 25%
entre o valor declarado no cardápio e o calculado pela medida caseira gera nota.
Divergir é legítimo; **esconder que divergiu** é o defeito.

### Privilégio vem de token validado, nunca do cliente

Tools de gestão leem dado agregado da unidade inteira. A flag `admin` sai do
`X-Admin-Token` validado no handler Go e é carimbada no envelope da fila. O
corpo da requisição é escrito pelo cliente e **nunca** decide privilégio.

Com `ADMIN_TOKEN` vazio ninguém é admin no chat: o gate desligado abre as rotas
de admin, não a conversa.

### Provedor é configuração, não código

`motor/provedores.py` centraliza a construção. O eval tem as suas
(`EVAL_JUIZ_PROVIDER`, `EVAL_JUIZ_MODELO`) porque modelo julgando saída da
própria família tende a erro correlacionado.

Qual usar em cada situação, com os números medidos: [`custos-provedores.md`](custos-provedores.md).

> **Armadilha:** o `.env` que o compose lê é o de `deploy/`, não o da raiz.
> Configurar o arquivo errado não dá erro — dá silêncio, e o worker cai no
> default.

## Decisões que foram revisadas, e o que as mudou

**Few-shot no juiz do eval.** Previmos que exemplos ajudariam sempre. Medido: o
1.5B **piorou** (82% → 76%) e o 3B melhorou (94% → 100%). Capacidade decide se
exemplo ancora ou distrai — modelo pequeno segue o padrão mais concreto que
enxerga, e um exemplo é mais concreto que a instrução abstrata.

**Framework do laço agentic.** Mantido `create_agent`, com gatilho explícito
para revisar. Ver [`langchain-vs-langgraph.md`](langchain-vs-langgraph.md).

## Referência externa

O **Onyx** está clonado em `~/desenvolvimento/onyx` como referência de
arquitetura. Foi lido, não copiado: o `llm/` deles tem 8.192 linhas contra ~4.100
do nosso motor inteiro, e boa parte é suporte a dezenas de provedores com quirks
de cada um.

O que pegamos: erro classificado, preflight, tool que não derruba o turno, tool
de planejamento. O que deliberadamente não pegamos: o registro de capacidades de
modelo (690 linhas derivadas do litellm), o `deep_research` (1.179 linhas) e a
interpolação do erro cru na mensagem que o modelo lê.
