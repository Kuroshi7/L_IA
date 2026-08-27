"""Tool que falha não pode derrubar o turno.

Medido antes de existir este módulo: uma tool que levanta exceção aborta o grafo
inteiro. O usuário recebia erro genérico e o modelo nunca sabia que a busca
falhou — nem tinha chance de contornar.
"""

from langchain_core.tools import tool

from app.agent.motor.tools import AVISO_GENERICO, ErroDeTool, blindar, blindar_todas


@tool
def busca_que_cai() -> str:
    """Busca alguma coisa."""
    raise RuntimeError("conexão com o banco recusada em pg://user:senha@10.0.0.5")


@tool
def busca_com_erro_previsto() -> str:
    """Busca alguma coisa."""
    raise ErroDeTool("O cardápio de hoje ainda não foi publicado pela nutricionista.")


@tool
def busca_que_funciona() -> str:
    """Busca alguma coisa."""
    return "arroz, feijão, frango"


def test_falha_nao_previsto_vira_texto_para_o_modelo():
    r = blindar(busca_que_cai).invoke({})
    assert r == AVISO_GENERICO


def test_detalhe_de_infra_nao_chega_ao_modelo():
    """Desvio deliberado do Onyx, que interpola str(e) na mensagem.

    Exceção de banco carrega host, usuário e às vezes senha. O modelo é
    instruído a explicar a situação ao usuário — esse detalhe não pode entrar
    no contexto dele. Fica no log, onde o operador vê e o usuário não.
    """
    r = blindar(busca_que_cai).invoke({})
    for vazamento in ("senha", "10.0.0.5", "pg://", "RuntimeError"):
        assert vazamento not in r, f"vazou {vazamento!r} para o contexto do modelo"


def test_erro_previsto_usa_a_frase_do_dominio():
    """O caso bom: o domínio sabe o que houve e a falha vira informação útil."""
    r = blindar(busca_com_erro_previsto).invoke({})
    assert "ainda não foi publicado" in r


def test_tool_saudavel_passa_intacta():
    assert blindar(busca_que_funciona).invoke({}) == "arroz, feijão, frango"


def test_o_turno_sobrevive_a_tool_que_estoura():
    """A regressão que motivou o módulo, no grafo de verdade."""
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage, ToolMessage

    class _Falso(GenericFakeChatModel):
        def bind_tools(self, *a, **k):
            return self

    modelo = _Falso(messages=iter([
        AIMessage(content="", tool_calls=[{"name": "busca_que_cai", "args": {}, "id": "1"}]),
        AIMessage(content="Não consegui consultar agora."),
    ]))

    agente = create_agent(model=modelo, tools=blindar_todas([busca_que_cai]),
                          system_prompt="teste")
    r = agente.invoke({"messages": [("user", "busca aí")]})

    observadas = [m.content for m in r["messages"] if isinstance(m, ToolMessage)]
    assert observadas == [AVISO_GENERICO], "o modelo precisa VER que a tool falhou"
    assert "Não consegui" in r["messages"][-1].content
