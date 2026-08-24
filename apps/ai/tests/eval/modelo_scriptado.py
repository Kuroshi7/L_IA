"""Modelo de mentira, com respostas roteirizadas. Custo zero.

Para que serve: rodar o eval INTEIRO — carregar casos, instalar os fakes da API
Go, montar contexto, executar tools, aplicar pós-processamento, validar e
conferir asserções — sem uma única chamada de API.

Para que NÃO serve: dizer qualquer coisa sobre o comportamento do modelo. Aqui o
"modelo" faz exatamente o que o roteiro manda. O que isto prova é que o
ENCANAMENTO funciona; o que o modelo faz com ele só a rodada real diz.

Por que existe: a bateria completa com 3 repetições custa cerca de US$ 2,30 em
Haiku. Um erro bobo que quebre o harness — asserção com nome errado, caso
apontando para dataset inexistente, mudança de contrato de tool — não deveria
ser descoberto depois de gastar isso. Este modelo roda em todo commit, de graça,
e falha antes.

O `GenericFakeChatModel` do langchain_core não serve: ele não implementa
`bind_tools`, e sem isso o agente não monta.
"""

from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ModeloScriptado(BaseChatModel):
    """Devolve as respostas do roteiro, em ordem.

    Cada item do roteiro é uma tupla `(nome_da_tool, argumentos)` para simular
    uma chamada de tool, ou uma string para a resposta final. Esgotado o
    roteiro, devolve `resposta_padrao` — assim um roteiro curto demais falha na
    asserção do teste, não num IndexError sem contexto.
    """

    roteiro: list[Any] = []
    resposta_padrao: str = "Pronto!"
    chamadas: list[Any] = []

    @property
    def _llm_type(self) -> str:
        return "scriptado"

    def bind_tools(self, tools, **kwargs):
        # O agente exige este método; o roteiro já decide o que será chamado.
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.chamadas.append(messages)
        passo = self.roteiro.pop(0) if self.roteiro else self.resposta_padrao

        if isinstance(passo, tuple):
            nome, args = passo
            msg = AIMessage(
                content="",
                tool_calls=[{"name": nome, "args": args, "id": f"call_{len(self.chamadas)}"}],
            )
        else:
            msg = AIMessage(content=passo)

        return ChatResult(generations=[ChatGeneration(message=msg)])


def instalar(monkeypatch, roteiro: list[Any], resposta_padrao: str = "Pronto!") -> ModeloScriptado:
    """Substitui o modelo do motor pelo roteirizado, e limpa o cache de executor.

    O cache existe justamente para não remontar o grafo a cada turno — mas ele
    guardaria o modelo antigo entre testes.
    """
    from app.agent.motor import llm

    modelo = ModeloScriptado(roteiro=list(roteiro), resposta_padrao=resposta_padrao, chamadas=[])
    monkeypatch.setattr(llm, "obter_llm", lambda: modelo)
    monkeypatch.setattr(llm, "_executores", {})
    return modelo


def instalar_classificador(monkeypatch, veredicto: str = "nao") -> list[str]:
    """Roteiriza o CLASSIFICADOR do guardrail — o segundo LLM do turno.

    Fácil de esquecer que ele existe: o guardrail decide por keywords quando
    consegue e só chama o modelo quando não consegue. Offline, esse modelo não
    responde e o guardrail FALHA ABERTO por decisão de projeto (rejeitar a
    pergunta mais comum do produto seria pior) — então, sem roteiro, todo caso
    de fora-de-escopo passa.

    Devolve a lista de textos que chegaram ao classificador, para o teste poder
    afirmar se ele foi consultado ou se as keywords resolveram sozinhas.
    """
    from app.agent.dominio.refeitorio import guardrail

    consultas: list[str] = []

    class _Classificador:
        def invoke(self, mensagens):
            consultas.append(str(mensagens[-1][1]))
            return AIMessage(content=veredicto)

    monkeypatch.setattr(guardrail, "_get_classificador", lambda: _Classificador())
    return consultas
