"""A tese de reaproveitamento, verificada — não prometida.

Monta um domínio COMPLETAMENTE diferente (uma agenda de manutenção, sem nada de
comida) sobre o mesmo motor. Se algum dia isto exigir mudar uma linha de
`motor/`, a fronteira está errada — e o produto futuro herdaria um motor que só
serve para refeitório.

O oposto também é medido aqui: campo do `PerfilDeDominio` que este domínio
consegue deixar vazio sem quebrar nada é candidato a ser cortado. Interface que
ninguém preenche é interface artificial.
"""

from langchain_core.tools import tool

from app.agent.motor.observacao import (
    encerrar_turno,
    iniciar_turno,
    observacoes_do_turno,
    observado,
)
from app.agent.motor.perfil import PerfilDeDominio
from app.agent.motor.registry import CATALOGO, ToolSpec, nomes_com_capacidade, tools_do_turno
from app.agent.motor.reminders import Gatilhos, Reminder
from app.agent.motor.turn import montar_mensagens
from app.agent.motor.validacao import Achado, verificar

SYSTEM = (
    "Você é o assistente de manutenção da frota. REGRA DE OFICINA: só agende "
    "serviço que apareça na lista de ordens abertas."
)

EQUIPAMENTOS = [
    {"id": 1, "nome": "Empilhadeira 07", "horas_uso": 1240},
    {"id": 2, "nome": "Compressor B", "horas_uso": 380},
]


@tool
@observado
def listar_ordens_abertas() -> list[dict]:
    """Ordens de manutenção abertas."""
    return [dict(e) for e in EQUIPAMENTOS]


@tool
@observado
def meu_turno() -> dict:
    """Turno do técnico logado."""
    return {"turno": "noturno"}


def _tem_tecnico(contexto) -> bool:
    return getattr(contexto, "tecnico_id", None) is not None


REGISTRO = (
    ToolSpec(listar_ordens_abertas, capacidades=frozenset({CATALOGO})),
    ToolSpec(meu_turno, disponivel=_tem_tecnico),
)

REMINDER = Reminder(
    nome="ordens_primeiro",
    texto="REGRA DE OFICINA: liste as ordens abertas antes de agendar qualquer serviço.",
    regra_de_origem="REGRA DE OFICINA",
)


def _regra_agendou_sem_listar(a: Achado) -> str | None:
    if "agendei" not in a.resposta.lower():
        return None
    if set(a.tools_chamadas) & nomes_com_capacidade(REGISTRO, CATALOGO):
        return None
    return "agendou sem consultar as ordens abertas"


PERFIL_OFICINA = PerfilDeDominio(
    nome="oficina",
    system_prompt=SYSTEM,
    registro=REGISTRO,
    esta_no_escopo=lambda texto, tem_historico: "manutencao" in texto.lower() or tem_historico,
    resposta_fora_de_escopo="Só falo de manutenção da frota.",
    resposta_erro_transiente="Sistema da oficina indisponível, tente de novo.",
    resposta_bloqueada="Vou conferir a ordem antes de agendar. Pode pedir de novo?",
    reminders=lambda g, _m="": (REMINDER,) if g.primeira_interacao_do_dia else (),
    regras=(("OF1-agendou-sem-listar", _regra_agendou_sem_listar),),
    pos_processar=lambda r, _g, m: r + "\n\n(Ordem sujeita à disponibilidade de peça.)"
    if "revisao" in m else r,
)


# --- o motor aceita o domínio estrangeiro inteiro ----------------------------

def test_registry_seleciona_tools_do_outro_dominio():
    anonimo = type("C", (), {"tecnico_id": None})()
    logado = type("C", (), {"tecnico_id": 3})()
    assert {s.nome for s in tools_do_turno(REGISTRO, anonimo)} == {"listar_ordens_abertas"}
    assert len({s.nome for s in tools_do_turno(REGISTRO, logado)}) == 2


def test_dominio_estrangeiro_define_a_propria_mensagem_de_bloqueio():
    # O motor bloqueia; a frase é do produto. Sem isso, um domínio de oficina
    # responderia com texto de refeitório quando uma regra reprovasse.
    assert "ordem" in PERFIL_OFICINA.resposta_bloqueada


def test_pos_processamento_e_do_dominio():
    # O motor chama; o que é acrescentado é regra do produto. Num refeitório é
    # encaminhamento a nutricionista; numa oficina, ressalva de peça.
    assert "peça" in PERFIL_OFICINA.pos_processar("Agendei.", Gatilhos(), "quero revisao")
    assert PERFIL_OFICINA.pos_processar("Agendei.", Gatilhos(), "oi") == "Agendei."


def test_reminder_do_outro_dominio_vai_para_o_fim():
    msgs = montar_mensagens(
        [{"papel": "user", "conteudo": "oi"}],
        "preciso agendar uma revisão",
        PERFIL_OFICINA.reminders(Gatilhos(primeira_interacao_do_dia=True)),
    )
    assert msgs[-1].content.endswith(REMINDER.texto)


def test_invariante_de_reminder_vale_para_qualquer_dominio():
    # A mesma checagem que roda no refeitório, sem uma linha de motor mudada.
    for r in PERFIL_OFICINA.reminders(Gatilhos(True)):
        assert r.regra_de_origem in PERFIL_OFICINA.system_prompt


def test_observacoes_colhem_itens_de_outro_dominio():
    token = iniciar_turno()
    try:
        listar_ordens_abertas.invoke({})
        obs = observacoes_do_turno()
    finally:
        encerrar_turno(token)

    assert "empilhadeira 07" in obs.itens_conhecidos
    assert 1240.0 in obs.valores_expostos    # horas_uso, não kcal
    assert 1.0 not in obs.valores_expostos   # id continua fora


def test_validacao_roda_as_regras_do_outro_dominio():
    ruim = verificar(PERFIL_OFICINA.regras, "Agendei a revisão pra terça.", tools_chamadas=[])
    boa = verificar(PERFIL_OFICINA.regras, "Agendei a revisão pra terça.",
                    tools_chamadas=["listar_ordens_abertas"])
    assert not ruim.ok and ruim.ids == ("OF1-agendou-sem-listar",)
    assert boa.ok


def test_guardrail_do_outro_dominio():
    assert PERFIL_OFICINA.esta_no_escopo("preciso de manutencao", False)
    assert not PERFIL_OFICINA.esta_no_escopo("qual o cardapio de hoje?", False)


def test_nenhum_campo_do_perfil_ficou_sem_consumidor():
    # Se um campo puder ser omitido por um domínio real sem nada quebrar, ele é
    # candidato a ser cortado — este teste é o lembrete de reavaliar.
    usados = {"nome", "system_prompt", "registro", "esta_no_escopo",
              "resposta_fora_de_escopo", "resposta_erro_transiente", "resposta_bloqueada",
              # consumido em motor/turn.py: quando motor/erros.py classifica a
              # falha como permanente, "tente de novo" seria mentira.
              "resposta_erro_permanente",
              "reminders", "regras", "pos_processar"}
    declarados = set(PerfilDeDominio.__dataclass_fields__)
    assert declarados == usados, f"campo sem consumidor neste teste: {declarados - usados}"
