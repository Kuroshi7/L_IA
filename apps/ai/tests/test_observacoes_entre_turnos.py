"""O que uma tool descobriu num turno tem que chegar ao turno seguinte.

Defeito de origem (medido em 27/08/2026): a pessoa esclareceu o critério e o
modelo refez EXATAMENTE a consulta que tinha falhado cinco vezes trinta segundos
antes. Nada do que as tools descobrem atravessa o turno — o histórico é só texto
de pessoa e de assistente —, então para ele era a primeira vez.

Tudo aqui roda sobre tools FALSAS declaradas neste arquivo, e não sobre as do
produto: o comportamento em teste é do motor. Amarrado a uma tool real, este
arquivo quebraria toda vez que o domínio mexesse no filtro dela — e passaria a
medir o domínio em vez do mecanismo.
"""

import copy

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from app import config
from app.agent.motor import memoria, turn
from app.agent.motor.observacao import (
    CHAVE_NOTA,
    TEXTO_JA_CONSULTADO,
    TEXTO_SEM_SAIDA,
    ObservacoesDoTurno,
    PrazoEsgotado,
    _args_canonicos,
    encerrar_turno,
    iniciar_turno,
    observado,
)
from app.agent.motor.perfil import PerfilDeDominio
from app.agent.motor.registry import ToolSpec

# O que a tool falsa devolve neste teste, e o que ela recebeu. Estado de módulo
# porque a tool precisa ser declarada uma vez (o decorator embrulha na
# declaração), e cada teste reconfigura pela fixture.
RESPOSTA: dict = {"atual": None}
CHAMADAS: list = []

SEM_NADA = {"itens": [], CHAVE_NOTA: "Não encontrei nada com esses critérios."}
COM_ITEM = {"itens": [{"nome": "Item A"}]}


@tool
@observado
def consultar(criterio: str, quando: str = "hoje") -> dict:
    """Consulta o conjunto disponível por um critério."""
    CHAMADAS.append({"criterio": criterio, "quando": quando})
    # Cópia profunda: o retorno é anotado pelo motor, e um teste não pode
    # contaminar o retorno do teste seguinte.
    return copy.deepcopy(RESPOSTA["atual"])


PERFIL = PerfilDeDominio(
    nome="teste-entre-turnos",
    system_prompt="Assistente de teste.",
    registro=(ToolSpec(consultar),),
    esta_no_escopo=lambda _texto, _tem: True,
    resposta_fora_de_escopo="fora",
    resposta_erro_transiente="tente de novo",
)

CONTEXTO = object()  # o motor trata o contexto como opaco

# Histórico não-vazio: histórico vazio significa conversa nova e dispara o
# esquecimento proposital. Os testes que querem esse caminho passam [] à mão.
HISTORICO = [{"papel": "user", "conteudo": "oi"}, {"papel": "assistant", "conteudo": "olá"}]


class AgenteFalso:
    """Substitui o executor do agente: roda um roteiro fixo de chamadas de tool
    e devolve uma resposta pronta. É o que permite exercitar `executar_turno`
    inteiro — inclusive o `finally` que grava a memória — sem nenhum LLM."""

    def __init__(self, roteiro, explodir=None):
        self.roteiro = roteiro
        self.explodir = explodir
        self.retornos = []

    def invoke(self, _payload, config=None):
        for argumentos in self.roteiro:
            self.retornos.append(consultar.invoke(argumentos))
        if self.explodir:
            raise self.explodir
        return {"messages": [AIMessage(content="pronto")]}


@pytest.fixture(autouse=True)
def ambiente_limpo():
    memoria._becos.clear()
    CHAMADAS.clear()
    RESPOSTA["atual"] = SEM_NADA
    yield
    memoria._becos.clear()


def rodar(monkeypatch, session_id, roteiro, historico=HISTORICO, explodir=None):
    """Um turno completo com o executor falsificado. Devolve os retornos que as
    tools entregaram ao modelo — é lá que a informação nova precisa aparecer."""
    agente = AgenteFalso(roteiro, explodir=explodir)
    monkeypatch.setattr(turn, "obter_executor", lambda *a, **k: agente)
    turn.executar_turno(
        PERFIL, "qualquer coisa", CONTEXTO, historico=historico, session_id=session_id
    )
    return agente.retornos


def nota(retorno) -> str:
    return str(retorno.get(CHAVE_NOTA) or "") if isinstance(retorno, dict) else str(retorno)


# --- o que a frente conserta --------------------------------------------------

def test_caminho_morto_atravessa_o_turno(monkeypatch):
    # O teste do defeito. Sem a memória entre turnos os dois retornos são
    # idênticos, e é exatamente isso que o modelo viu no baseline: o segundo
    # turno chega sem nenhum sinal de que aquele caminho já morreu.
    t1 = rodar(monkeypatch, "s1", [{"criterio": "x"}])
    t2 = rodar(monkeypatch, "s1", [{"criterio": "x"}])

    assert TEXTO_SEM_SAIDA not in nota(t1[0])
    assert TEXTO_SEM_SAIDA in nota(t2[0])


def test_a_nota_da_propria_tool_continua_no_retorno(monkeypatch):
    # O aviso do motor ACRESCENTA; ele não pode engolir a orientação concreta
    # que a tool escreveu, que é a que conhece a situação.
    rodar(monkeypatch, "s1", [{"criterio": "x"}])
    t2 = rodar(monkeypatch, "s1", [{"criterio": "x"}])

    assert SEM_NADA[CHAVE_NOTA] in nota(t2[0])
    assert TEXTO_SEM_SAIDA in nota(t2[0])


def test_anota_mas_nao_bloqueia(monkeypatch):
    # A garantia que torna a solução segura: a tool roda SEMPRE. Se o que se
    # consulta mudou desde o turno passado, o modelo recebe o resultado real e
    # nenhuma nota. Sem isso, a memória viraria censura de consulta viva.
    rodar(monkeypatch, "s1", [{"criterio": "x"}])
    RESPOSTA["atual"] = COM_ITEM
    t2 = rodar(monkeypatch, "s1", [{"criterio": "x"}])

    assert t2[0]["itens"] == [{"nome": "Item A"}]
    assert TEXTO_SEM_SAIDA not in nota(t2[0])
    assert len(CHAMADAS) == 2, "a tool precisa ter rodado de verdade nos dois turnos"


def test_turno_abortado_por_prazo_ainda_grava_o_que_aprendeu(monkeypatch):
    # O turno que estoura o prazo é justamente aquele em que o modelo passou o
    # tempo todo insistindo num caminho morto. Por isso a gravação é no
    # `finally`, e não no caminho feliz.
    rodar(monkeypatch, "s1", [{"criterio": "x"}], explodir=PrazoEsgotado("consultar"))
    t2 = rodar(monkeypatch, "s1", [{"criterio": "x"}])

    assert TEXTO_SEM_SAIDA in nota(t2[0])


# --- os limites: quando a memória NÃO pode agir -------------------------------

def test_nao_contamina_outra_conversa(monkeypatch):
    rodar(monkeypatch, "s1", [{"criterio": "x"}])
    t2 = rodar(monkeypatch, "s2", [{"criterio": "x"}])

    assert TEXTO_SEM_SAIDA not in nota(t2[0])


def test_sem_identificador_nao_ha_memoria(monkeypatch):
    # A rota de inferência direta aceita identificador vazio. Se ele fosse
    # tratado como uma conversa, todas essas chamadas cairiam num balde só e
    # uma pessoa herdaria o fracasso de outra.
    rodar(monkeypatch, "", [{"criterio": "x"}])
    t2 = rodar(monkeypatch, "", [{"criterio": "x"}])

    assert TEXTO_SEM_SAIDA not in nota(t2[0])


def test_conversa_zerada_esquece(monkeypatch):
    # Histórico vazio é o sinal de conversa nova ou zerada. Sem o esquecimento,
    # quem reinicia a conversa recomeçaria carregando o fracasso da anterior.
    rodar(monkeypatch, "s1", [{"criterio": "x"}])
    t2 = rodar(monkeypatch, "s1", [{"criterio": "x"}], historico=[])

    assert TEXTO_SEM_SAIDA not in nota(t2[0])


def test_memoria_expira(monkeypatch):
    # O conjunto consultável muda com o tempo: "não achei" de meia hora atrás
    # não é evidência sobre agora.
    agora = [1000.0]
    monkeypatch.setattr(memoria, "_relogio", lambda: agora[0])

    rodar(monkeypatch, "s1", [{"criterio": "x"}])
    agora[0] += memoria.TTL_SEGUNDOS + 1
    t2 = rodar(monkeypatch, "s1", [{"criterio": "x"}])

    assert TEXTO_SEM_SAIDA not in nota(t2[0])


def test_retorno_de_lista_nao_muda_de_formato(monkeypatch):
    # Mesma regra já medida na reinjeção de reminders: mexer no formato de um
    # retorno de lista confunde modelo pequeno, e o ganho não compensa.
    RESPOSTA["atual"] = []
    rodar(monkeypatch, "s1", [{"criterio": "x"}])
    t2 = rodar(monkeypatch, "s1", [{"criterio": "x"}])

    assert t2[0] == []


def test_retorno_com_numero_nunca_e_caminho_morto(monkeypatch):
    # Guarda contra o falso positivo caro: uma tool de saldo ou de escrita
    # confirma com números. Tratá-la como consulta morta ensinaria ao modelo a
    # desistir de um caminho vivo — inclusive de uma escrita legítima.
    RESPOSTA["atual"] = {"pontos": 12}
    rodar(monkeypatch, "s1", [{"criterio": "x"}])
    t2 = rodar(monkeypatch, "s1", [{"criterio": "x"}])

    assert TEXTO_SEM_SAIDA not in nota(t2[0])


# --- a medição do "não achou nada" --------------------------------------------

def test_a_marcacao_e_o_delta_da_chamada_e_nao_o_acumulado():
    # Se a medição fosse sobre o acumulado do turno, uma segunda consulta que
    # devolve itens JÁ VISTOS só sobrescreveria chaves em `itens_conhecidos`, o
    # acumulado não cresceria e ela seria marcada como morta — a memória
    # passaria a mentir sobre um caminho que funciona.
    obs = ObservacoesDoTurno()
    assert obs.registrar(("consultar", "a"), COM_ITEM) is False
    assert obs.registrar(("consultar", "b"), COM_ITEM) is False
    assert obs.sem_resultado == []


def test_a_marcacao_pega_o_retorno_vazio():
    obs = ObservacoesDoTurno()
    assert obs.registrar(("consultar", "a"), SEM_NADA) is True
    assert obs.sem_resultado == [("consultar", "a")]


# --- a chave: mesma consulta, escrita de jeitos diferentes ---------------------

def _sonda(criterio: str, quando: str = "hoje") -> dict:
    return {"itens": []}


def test_a_chave_e_o_conteudo_da_chamada_e_nao_a_forma_dela():
    # A chave é o que identifica "a mesma consulta". Ligada só à forma, `f("x")`
    # e `f(criterio="x")` viram consultas diferentes — e entre turnos a memória
    # nasceria inútil, porque um turno quase nunca reproduz a forma exata do
    # turno anterior.
    posicional = _args_canonicos(_sonda, ("x",), {})
    nomeado = _args_canonicos(_sonda, (), {"criterio": "x"})
    com_default_explicito = _args_canonicos(_sonda, (), {"criterio": "x", "quando": "hoje"})

    assert posicional == nomeado == com_default_explicito
    assert _args_canonicos(_sonda, (), {"criterio": "y"}) != posicional


def test_a_chave_estavel_tambem_comprime_dentro_do_turno(monkeypatch):
    # Consequência prática da chave por conteúdo, e a explicação candidata para
    # as cinco chamadas com o corpo inteiro que apareceram no log do baseline
    # mesmo com a compressão ligada.
    monkeypatch.setattr(config, "COMPRIMIR_REPETICOES", True)
    chamadas = []

    @observado
    def sondar(criterio: str, quando: str = "hoje") -> dict:
        chamadas.append(criterio)
        return {"itens": []}

    token = iniciar_turno()
    try:
        sondar("x")
        repetida = sondar(criterio="x", quando="hoje")
    finally:
        encerrar_turno(token)

    assert repetida == TEXTO_JA_CONSULTADO
    assert len(chamadas) == 1


def test_assinatura_nao_inspecionavel_nao_derruba_o_turno():
    # O fallback existe porque uma otimização não pode quebrar uma conversa:
    # `inspect.signature` estoura em objeto não chamável, e o motor precisa
    # seguir com a forma crua dos argumentos.
    assert _args_canonicos(object(), ("abc",), {"k": 1})


# --- os tetos da memória no processo ------------------------------------------

def test_teto_de_chaves_por_conversa_descarta_a_mais_antiga():
    for i in range(memoria.MAX_CHAVES_POR_CONVERSA + 5):
        memoria.registrar("s1", [("consultar", f"arg-{i}")])

    lembradas = memoria.lembrar("s1")
    assert len(lembradas) == memoria.MAX_CHAVES_POR_CONVERSA
    assert ("consultar", "arg-0") not in lembradas
    assert ("consultar", f"arg-{memoria.MAX_CHAVES_POR_CONVERSA + 4}") in lembradas


def test_teto_de_conversas_impede_crescimento_sem_fim():
    # O dicionário é indexado por um identificador que vem de fora, num processo
    # que fica de pé por dias. Sem teto, isso é vazamento de memória.
    for i in range(memoria.MAX_CONVERSAS + 10):
        memoria.registrar(f"s{i}", [("consultar", "x")])

    assert len(memoria._becos) == memoria.MAX_CONVERSAS


def test_esquecer_e_identificador_vazio():
    memoria.registrar("s1", [("consultar", "x")])
    memoria.esquecer("s1")
    assert memoria.lembrar("s1") == frozenset()

    memoria.registrar("", [("consultar", "x")])
    assert memoria.lembrar("") == frozenset()
    assert not memoria._becos


def test_a_memoria_guarda_a_chave_e_nunca_o_corpo(monkeypatch):
    # A razão de a solução ser barata: entre turnos viaja uma tupla de strings,
    # não o retorno das tools. Se um dia alguém guardar o corpo aqui, o custo de
    # todo turno seguinte cresce em silêncio.
    RESPOSTA["atual"] = {"itens": [], CHAVE_NOTA: "segredo-do-corpo"}
    rodar(monkeypatch, "s1", [{"criterio": "x"}])

    assert "segredo-do-corpo" not in repr(memoria._becos)
    for registros in memoria._becos.values():
        for nome, argumentos in registros:
            assert isinstance(nome, str) and isinstance(argumentos, str)
