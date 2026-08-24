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
        assert t.listar_pratos_do_dia.invoke({"dia": "hoje"})["total"] == 1
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


# --- reminder por assunto (condição de saúde) --------------------------------

def test_reminder_de_saude_dispara_pelo_assunto():
    # A regra 6c está no system prompt e media 0/3 de aderência: no meio de um
    # prompt longo ela se perde. Aqui ela chega colada ao ponto de geração.
    r = reminders_do_turno(rem.Gatilhos(), "sou diabético, o que é melhor pra mim?")
    assert any(x.nome == "condicao_de_saude" for x in r)


def test_reminder_de_saude_nao_dispara_em_conversa_comum():
    assert reminders_do_turno(rem.Gatilhos(), "o que tem hoje?") == ()


def test_reminder_de_saude_reconhece_variacoes():
    for texto in ["tenho pressao alta", "estou gravida", "meu colesterol ta alto",
                  "sou hipertenso", "tenho problema renal"]:
        assert reminders_do_turno(rem.Gatilhos(), texto), texto


def test_reminders_acumulam():
    r = reminders_do_turno(rem.Gatilhos(primeira_interacao_do_dia=True), "sou diabético")
    assert {x.nome for x in r} == {"primeira_do_dia", "condicao_de_saude"}


def test_invariante_vale_para_o_reminder_de_saude():
    for r in reminders_do_turno(rem.Gatilhos(True), "sou diabético"):
        assert r.regra_de_origem in PERFIL.system_prompt


# --- reinjeção contínua do reminder -----------------------------------------

def test_reminder_volta_no_resultado_da_tool(monkeypatch):
    # O reminder entra no fim da mensagem do usuário, mas deixa de ser a última
    # coisa do contexto assim que a tool responde — e é DEPOIS disso que a
    # resposta é gerada. Sem reinjeção, a instrução se perde exatamente no
    # momento em que ela precisa valer.
    from app.agent.motor.observacao import CHAVE_NOTA

    monkeypatch.setattr(t.go_api, "get_pratos", lambda u, d: [{"id": 1, "nome": "X", "categoria": "c"}])
    monkeypatch.setattr(t, "current_context", lambda: type("C", (), {"unidade_id": 1, "usuario_id": None})())

    token = iniciar_turno(reminders=("LEMBRETE DE TESTE",))
    try:
        out = t.listar_pratos_do_dia.invoke({"dia": "hoje"})
    finally:
        encerrar_turno(token)

    # A nota da própria tool tem precedência: ela sabe da situação concreta.
    assert "CARDÁPIO" in out[CHAVE_NOTA]
    assert "LEMBRETE DE TESTE" not in out[CHAVE_NOTA]


def test_reinjecao_nao_altera_retorno_de_lista(monkeypatch):
    monkeypatch.setattr(t.go_api, "get_pratos", lambda u, d: [
        {"id": 1, "nome": "X", "categoria": "c", "restricoes_atendidas": [], "alergenos": [], "ingredientes": []}])
    monkeypatch.setattr(t, "current_context", lambda: type("C", (), {"unidade_id": 1, "usuario_id": None})())

    token = iniciar_turno(reminders=("LEMBRETE",))
    try:
        out = t.filtrar_pratos.invoke({"dia": "hoje"})
    finally:
        encerrar_turno(token)
    assert isinstance(out, list)


def test_reinjecao_so_atua_onde_a_tool_nao_falou():
    # Medido: empilhar reminder genérico sobre a nota concreta da tool derrubou
    # a regra contratual de 89% para 61% (texto mais longo dilui) e chegou a
    # produzir instruções contraditórias no cardápio vazio.
    from app.agent.motor.observacao import _reinjetar, CHAVE_NOTA

    com_nota = _reinjetar({"x": 1, CHAVE_NOTA: "instrução da tool"}, ("reminder",))
    assert com_nota[CHAVE_NOTA] == "instrução da tool"

    sem_nota = _reinjetar({"x": 1}, ("reminder",))
    assert sem_nota[CHAVE_NOTA] == "reminder"


# --- a obrigatoriedade de listar o cardápio foi removida ---------------------

def test_prompt_nao_exige_mais_cardapio_completo_antes_de_recomendar():
    """Decisão de produto de 23/08/2026 (docs/regras-de-negocio.md §3.1).

    A listagem obrigatória empurrava a resposta para formato de catálogo e
    competia com a qualidade da recomendação: era cumprida em 3/3 quando pediam
    o cardápio e ficava instável quando pediam recomendação.
    """
    prompt = PERFIL.system_prompt
    assert "REGRA CONTRATUAL" not in prompt
    assert "MOSTRE PRIMEIRO o cardápio COMPLETO" not in prompt
    # O que entrou no lugar: recomendação com motivo, porção e alternativa.
    assert "RECOMENDAR É ESCOLHER POR ALGUÉM" in prompt
    assert "OUTRAS OPÇÕES" in prompt


def test_reminder_do_dia_virou_onboarding():
    # A flag `primeira_do_dia` continua sendo calculada no Go; sem novo uso ela
    # viraria encanamento morto.
    r = reminders_do_turno(rem.Gatilhos(primeira_interacao_do_dia=True), "oi")
    assert any(x.nome == "primeira_do_dia" for x in r)
    texto = next(x.texto for x in r if x.nome == "primeira_do_dia")
    assert "restrições" in texto and "pergunte" in texto.lower()
    assert "COMPLETO" not in texto
