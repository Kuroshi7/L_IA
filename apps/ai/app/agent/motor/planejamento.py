"""Tool de planejamento: o modelo pensa antes de agir, por escrito.

Pergunta composta — "compare X e Y no período Z e recomende" — chega ao agente
como um passe único: ele escolhe uma tool, vê o retorno e responde. Sem lugar
para decompor, ele tenta resolver tudo de uma vez e erra por omissão: consulta
uma coisa e conclui sobre três.

`pensar` dá esse lugar. A tool não faz nada — recebe o raciocínio e devolve uma
confirmação curta. O valor está inteiro no efeito colateral: o plano vira texto
no contexto, e as chamadas seguintes passam a ser decididas contra ele em vez de
contra a pergunta crua.

É a mesma ideia do `think_tool` do Onyx, e o motivo de funcionar é conhecido:
tokens gerados antes da decisão melhoram a decisão. A diferença aqui é que o
plano fica no histórico e o usuário nunca o vê — não é resposta, é rascunho.

**Não é raciocínio nativo.** Modelo com `reasoning` embutido já faz isso por
conta; esta tool serve aos que não fazem, que é a maioria dos abertos e baratos
que este projeto usa. Ligar as duas coisas ao mesmo tempo é desperdício.

Agnóstica de produto: não sabe o assunto, só que existe um.
"""

from __future__ import annotations

import logging

from langchain_core.tools import tool

log = logging.getLogger(__name__)

# Curta de propósito. Resposta longa aqui viraria contexto competindo com o
# plano que o modelo acabou de escrever — que é justamente o que se quer no topo
# da atenção dele.
_CONFIRMACAO = "Plano registrado. Execute-o agora, um passo por vez."


@tool
def pensar(raciocinio: str) -> str:
    """Use ANTES de agir quando a pergunta tiver mais de uma parte, exigir
    comparação, agregação por período, ou uma recomendação apoiada em dados.

    Escreva em texto corrido: o que a pergunta pede, quais dados faltam, quais
    consultas você fará e em que ordem. Isto NÃO é a resposta ao usuário e ele
    não vai ver — é o seu rascunho.

    Não use para pergunta direta que uma consulta resolve.
    """
    texto = (raciocinio or "").strip()
    if not texto:
        return "Plano vazio. Escreva o que pretende fazer antes de seguir."
    # No log para dar para auditar por que o agente decidiu o que decidiu — é a
    # única janela para dentro do raciocínio depois que o turno terminou.
    log.info("PLANO | %s", texto.replace("\n", " ")[:400])
    return _CONFIRMACAO
