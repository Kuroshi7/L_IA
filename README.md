# Lia — assistente de refeitório por conversa

A Lia ajuda a consultar o cardápio, escolher alimentos considerando o perfil e
registrar consumo e sobras pelo chat. As telas permitem criar um perfil,
cadastrar alimentos e acompanhar pontos e desperdício.

## Experimente em poucos passos

Você precisa de **Git**, **Docker com Docker Compose** e uma **chave da API Anthropic**
para a configuração de demonstração. Abra o Docker antes de começar.
Não precisa instalar Go, Python ou Node no computador.

### 1. Baixe o projeto

Abra um terminal e execute:

```bash
git clone --branch feat/motor-agente-onyx https://github.com/Kuroshi7/L_IA.git
cd L_IA
```

### 2. Inicie a demonstração

```bash
./demo.sh
```

O comando cria a configuração local, pede a chave Anthropic sem mostrá-la na
tela, inicia os serviços e prepara os dados de exemplo em um banco vazio.
A chave fica apenas no arquivo `.env`, ignorado pelo Git. O uso da API pode gerar
cobranças na sua conta Anthropic.

A primeira execução demora mais: baixa imagens, compila o projeto e baixa o
modelo local usado na busca de documentos. Espere aparecer **“Demonstração iniciada”**.
Nas próximas execuções, use o mesmo comando. Os dados cadastrados são preservados.

No Windows, use um terminal WSL com acesso ao Docker Desktop. No Linux e macOS,
use Bash e Docker Compose. O projeto foi executado e validado nesta máquina Linux.

### 3. Abra o site

Acesse **[http://localhost:5273](http://localhost:5273)**.

1. Escolha **Refeitório Central**.
2. Use **“Usar perfil de demonstração”** para entrar como Ana Demo, ou crie seu
   próprio perfil na tela **Perfil**.
3. Abra o chat e experimente as mensagens abaixo.

## Um passeio pelo chat

Envie uma mensagem por vez:

> Qual é o cardápio de hoje?

> Quero algo com bastante proteína, quanto eu ponho no prato?

> Comi 2 colheres de sopa de arroz integral e 1 concha de feijão. Não sobrou nada.

No registro de consumo, confira a **prévia**. Se estiver correta, confirme pelo
botão ou escreva **“Confirmo”**. Se estiver errada, escreva **“Cancelar”** e reformule.
Se a Lia pedir uma informação, responda antes de confirmar.

Para demonstrar restrições, cadastre **leite** nas alergias do perfil e pergunte:

> Tenho alergia a leite. O Strogonoff de Grão-de-Bico é uma opção?

A ficha demonstrativa desse prato contém creme de leite. A resposta deve apontar
o conflito, sem garantir ausência de contaminação cruzada.

Para informar uma sobra, experimente:

> Comi 2 conchas de feijão e deixei meia concha no prato.

Confira a interpretação na prévia antes de confirmar. Depois, veja o ranking
ou o painel administrativo de desperdício.

## Onde ficam as telas?

| Tela | Endereço local | O que fazer |
|---|---|---|
| Perfil | `/perfil` | Criar perfil, informar preferências e restrições |
| Unidades | `/unidades` | Escolher o refeitório |
| Chat do Central | `/u/1/chat` | Consultar e registrar consumo/sobras |
| Ranking do Central | `/u/1/ranking` | Ver a pontuação |
| Administração | `/admin` | Entrar na gestão |
| Alimentos do Central | `/admin/u/1/alimentos` | Cadastrar pratos, ingredientes e referências |
| Cardápio do Central | `/admin/u/1/cardapio` | Definir pratos por data |
| Desperdício do Central | `/admin/u/1/desperdicio` | Consultar os agregados de sobras |
| Usuários | `/admin/usuarios` | Consultar os perfis |

Na demonstração, o token administrativo padrão é **`dev-admin`**. Se você alterou
`ADMIN_TOKEN` no `.env`, use o valor configurado. Os endereços com `/1/` assumem
os dados iniciais; ao criar outra unidade, navegue pelo painel para abri-la.

**Conta/perfil e alimentos são cadastrados pelas telas.** O chat registra
consumo e sobras. Não há cadastro de despesas financeiras.

## Comandos do dia a dia

```bash
./demo.sh          # iniciar a demonstração
./demo.sh status   # conferir os serviços
./demo.sh logs     # consultar erros recentes
./demo.sh parar    # parar sem apagar os dados
```

Os dados ficam em volumes do Docker. Evite apagar volumes se quiser preservá-los.
O script não repopula um banco que já tenha unidades. Para outro dia de
apresentação, confira e prepare o cardápio da data pela administração.

## Se algo não funcionar

- **Docker não está disponível:** abra o Docker ou verifique o acesso ao serviço.
- **Porta ocupada:** edite a porta correspondente no `.env` e execute `./demo.sh`
  novamente. Por exemplo, `MENUAI_WEB_PORT=5274` muda o site para a porta 5274.
- **Chat não responde:** confira a chave e `LLM_PROVIDER` no `.env`; use
  `./demo.sh logs`. Verifique também acesso à internet e disponibilidade da API.
- **Cardápio vazio:** confira a unidade e a data no editor de cardápio.
- **Painel ainda não mudou:** aguarde alguns segundos; os agregados são
  atualizados pelo processamento de eventos.
- **Medida não disponível:** revise a referência cadastrada do alimento.
  O assistente deve informar a falta do dado, em vez de inventar uma porção.

## Como o projeto funciona

A interface **React** conversa com uma API **Go**, que guarda os dados no
**PostgreSQL**. Um serviço **Python** conduz o agente de IA e consulta ferramentas
da aplicação. O **RabbitMQ** transporta mensagens e eventos entre os serviços.
O **Ollama** fornece os embeddings usados na busca de documentos desta configuração.

O agente é separado em um **motor reaproveitável** e um **perfil de domínio**.
O motor conduz a conversa e o uso das ferramentas. O perfil do refeitório define
objetivo, escopo, ferramentas e regras de validação. Para outro produto, a ideia
é implementar outro perfil e suas operações, aproveitando a condução geral.
Esse contrato permite configurar o comportamento do agente sem dar acesso
irrestrito aos dados ou às ações.

Há configuração para outros provedores no [exemplo completo de ambiente](.env.example).
Para usar Ollama também na conversa, configure `LLM_PROVIDER=ollama` e
`OLLAMA_MODEL=llama3.2` no `.env`. O script baixa o modelo; em CPU, as respostas
podem ser lentas e exceder os prazos do chat.

## Limites da demonstração

Os dados nutricionais são demonstrativos e algumas referências precisam de
revisão. As respostas livres ainda podem conter afirmações imprecisas;
confira as fichas e os avisos de aproximação. A Lia não substitui orientação
profissional de saúde. Telegram não foi validado nesta instalação.

Esta configuração é para demonstração local, com credenciais locais de exemplo.
A revisão visual completa ainda exige uma passagem manual do apresentador.

## Guias e detalhes para quem quiser ir além

- [Roteiro de apresentação](docs/apresentacao/ROTEIRO-APRESENTACAO.txt)
- [Cola com mensagens prontas](docs/apresentacao/COLA-DEMO.txt)
- [Relatório de validação e limitações](docs/validacao/relatorio-demonstracao-2026-10-05.txt)
- [Regras de negócio](docs/regras-de-negocio.md)
- [Decisões de arquitetura](docs/decisoes-arquitetura.md)
- [Contrato da API](packages/contracts/openapi.yaml)

Para desenvolvimento, os testes são executados em `apps/api`, `apps/ai` e
`apps/web`. A suíte padrão de IA é offline; avaliações com modelo real ficam
separadas e podem consumir créditos de API.
