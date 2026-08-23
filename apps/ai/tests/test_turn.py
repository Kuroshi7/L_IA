"""Turn Controller: posição dos reminders, invariante de segurança e prazo."""

import time

import pytest
from langchain_core.messages import AIMessage, HumanMessage

import app.agent.dominio.refeitorio.tools as t
from app.agent.dominio.refeitorio.perfil import PERFIL, reminders_do_turno
from app.agent.motor import reminders as rem
from app.agent.motor.observacao import PrazoEsgotado, encerrar_turno, iniciar_turno
from app.agent.motor.turn import montar_mensagens, prazo_a_partir_de, texto_da_resposta

HISTORICO = [
    {"papel": "user", "conteudo": "oi"},
    {"papel": "assistant", "conteudo": "olá!"},
]


# --- posição do reminder ------------------------------------------------------

def test_reminder_fica_no_fim_de_tudo():
    # O motivo de existir deste módulo: instrução colada no ponto de geração é
    # obedecida muito mais do que a mesma instrução no meio do system prompt.
    msgs = montar_mensagens(
        HISTORICO, "quero algo proteico",
        reminders_do_turno(rem.Gatilhos(primeira_interacao_do_dia=True)),
    )
    ultimo = msgs[-1].content
    assert ultimo.endswith(PERFIL.reminders(rem.Gatilhos(True))[0].texto)
    assert "quero algo proteico" in ultimo
    assert rem.CABECALHO in ultimo


def test_sem_gatilho_a_mensagem_fica_intacta():
    msgs = montar_mensagens(HISTORICO, "quero algo proteico", reminders_do_turno(rem.Gatilhos()))
    assert msgs[-1].content == "quero algo proteico"
    assert rem.CABECALHO not in msgs[-1].content


def test_historico_vira_papeis_corretos():
    msgs = montar_mensagens(HISTORICO, "e agora?")
    assert isinstance(msgs[0], HumanMessage)
    assert isinstance(msgs[1], AIMessage)
    assert isinstance(msgs[2], HumanMessage)
    assert len(msgs) == 3


# --- invariante de segurança --------------------------------------------------

@pytest.mark.parametrize("gatilhos", [rem.Gatilhos(True), rem.Gatilhos(False)])
def test_todo_reminder_apenas_repete_regra_do_system_prompt(gatilhos):
    # É esta invariante que torna seguro entregar o reminder pelo canal do
    # usuário (spoofável): ele nunca concede nada que o system já não autorize.
    # Quebrar isto reabre o IA-08.
    for r in PERFIL.reminders(gatilhos):
        assert r.regra_de_origem in PERFIL.system_prompt, (
            f"reminder {r.nome!r} ancora em {r.regra_de_origem!r}, que não existe "
            "no system prompt — ele estaria introduzindo regra nova"
        )


# --- prazo --------------------------------------------------------------------

def test_prazo_vencido_impede_a_tool_de_executar(monkeypatch):
    chamadas = []
    monkeypatch.setattr(t.go_api, "get_pratos", lambda u, d: chamadas.append(1) or [])
    monkeypatch.setattr(t, "current_context", lambda: type("C", (), {"unidade_id": 1, "usuario_id": None})())

    token = iniciar_turno(prazo=time.monotonic() - 1)  # já venceu
    try:
        with pytest.raises(PrazoEsgotado):
            t.listar_pratos_do_dia.invoke({"dia": "hoje"})
    finally:
        encerrar_turno(token)

    assert chamadas == [], "a tool não deveria ter chegado a consultar a API"


def test_sem_prazo_o_comportamento_e_o_de_sempre(monkeypatch):
    monkeypatch.setattr(t.go_api, "get_pratos", lambda u, d: [{"id": 1, "nome": "X", "categoria": "c"}])
    monkeypatch.setattr(t, "current_context", lambda: type("C", (), {"unidade_id": 1, "usuario_id": None})())

    token = iniciar_turno(prazo=None)
    try:
        assert len(t.listar_pratos_do_dia.invoke({"dia": "hoje"})) == 1
    finally:
        encerrar_turno(token)


def test_prazo_desconta_o_tempo_ja_gasto_na_fila():
    # A mensagem foi publicada há 50s de um orçamento de 60s: sobram ~10s.
    prazo = prazo_a_partir_de(time.time() - 50, 60)
    restante = prazo - time.monotonic()
    assert 8 < restante < 12


def test_mensagem_sem_timestamp_nao_ganha_prazo():
    assert prazo_a_partir_de(None, 60) is None


def test_orcamento_ja_estourado_vira_prazo_no_passado():
    prazo = prazo_a_partir_de(time.time() - 120, 60)
    assert prazo <= time.monotonic()


# --- extração de texto --------------------------------------------------------

def test_texto_da_resposta_aceita_blocos_do_anthropic():
    blocos = [{"type": "text", "text": "olá"}, {"type": "tool_use"}, {"type": "text", "text": " tudo bem"}]
    assert texto_da_resposta(blocos) == "olá tudo bem"
    assert texto_da_resposta("simples") == "simples"
