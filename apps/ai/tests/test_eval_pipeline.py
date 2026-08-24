"""O eval inteiro, ponta a ponta, sem gastar API.

A bateria completa com 3 repetições custa cerca de US$ 2,30 em Haiku. Um erro
que quebre o próprio harness — asserção com nome errado, caso apontando para
dataset inexistente, contrato de tool alterado — não deveria aparecer depois de
gastar isso.

Estes testes trocam o modelo por um roteirizado e rodam o caminho de verdade:
seleção de tools, montagem de contexto, execução das tools contra os fakes da
API Go, pós-processamento do domínio, validação e conferência das asserções.

O que eles NÃO fazem é dizer qualquer coisa sobre a qualidade do modelo. Aqui o
"modelo" faz o que o roteiro manda.
"""

import pytest

from app.agent.context import RequestContext, reset_context, set_context
from app.agent.dominio.refeitorio.perfil import PERFIL
from app.agent.motor import turn
from app.agent.motor.reminders import Gatilhos
from tests.eval import assercoes, fakes, modelo_scriptado


def _rodar(monkeypatch, roteiro, mensagem, dados="padrao", usuario_id=7, primeira=False):
    dados_ = fakes.carregar_dados(dados)
    fakes.instalar(monkeypatch, dados_)
    modelo_scriptado.instalar(monkeypatch, roteiro)

    contexto = RequestContext(unidade_id=1, usuario_id=usuario_id)
    token = set_context(contexto)
    try:
        return turn.executar_turno(
            PERFIL, mensagem, contexto=contexto,
            gatilhos=Gatilhos(primeira_interacao_do_dia=primeira),
            session_id="pipeline",
        ), dados_
    finally:
        reset_context(token)


# --- o caminho feliz percorre tudo -------------------------------------------

def test_turno_completo_chama_tool_e_responde(monkeypatch):
    resultado, _ = _rodar(
        monkeypatch,
        [("listar_pratos_do_dia", {"dia": "hoje"}),
         "Cardápio de hoje: **Frango grelhado com ervas**, **Estrogonofe de carne**."],
        "o que tem hoje?",
    )
    assert resultado.erro is None
    assert "listar_pratos_do_dia" in resultado.tools_chamadas
    assert "Frango grelhado" in resultado.resposta
    assert resultado.veredicto is not None, "a validação faz parte do turno"


def test_observacoes_alimentam_a_validacao(monkeypatch):
    resultado, _ = _rodar(
        monkeypatch,
        [("listar_pratos_do_dia", {"dia": "hoje"}), "Recomendo a **Feijoada Completa**."],
        "me indica algo",
    )
    # O prato não veio de tool nenhuma: a R2 tem que pegar.
    assert "R2-prato-fora-do-cardapio" in resultado.veredicto.ids


# --- as barreiras de segurança funcionam no caminho real ---------------------

def test_regra_bloqueante_substitui_a_resposta(monkeypatch):
    resultado, _ = _rodar(
        monkeypatch,
        [("listar_pratos_do_dia", {"dia": "hoje"}),
         "Recomendo a **Salada de grao-de-bico com amendoim**, é bem leve."],
        "o que eu como?",
        dados="vegetariano_alergico",
    )
    assert resultado.erro == "ValidacaoBloqueou"
    assert "amendoim" not in resultado.resposta.lower(), "a resposta insegura não pode vazar"
    assert resultado.resposta == PERFIL.resposta_bloqueada


def test_pos_processamento_acrescenta_o_encaminhamento(monkeypatch):
    resultado, _ = _rodar(
        monkeypatch,
        ["Prefira pratos com mais proteína e menos açúcar."],
        "tenho diabetes, o que como?",
    )
    assert "nutricionista" in resultado.resposta


def test_prazo_esgotado_aborta_o_turno(monkeypatch):
    import time
    dados = fakes.carregar_dados("padrao")
    fakes.instalar(monkeypatch, dados)
    modelo_scriptado.instalar(monkeypatch, [("listar_pratos_do_dia", {"dia": "hoje"}), "ok"])

    contexto = RequestContext(unidade_id=1, usuario_id=7)
    token = set_context(contexto)
    try:
        r = turn.executar_turno(PERFIL, "o que tem hoje?", contexto=contexto,
                                prazo=time.monotonic() - 1, session_id="prazo")
    finally:
        reset_context(token)
    assert r.erro == "PrazoEsgotado"


# --- o harness de eval roda sobre o resultado real ---------------------------

def test_assercoes_rodam_sobre_um_turno_de_verdade(monkeypatch):
    resultado, dados = _rodar(
        monkeypatch,
        [("listar_pratos_do_dia", {"dia": "hoje"}),
         ("meu_perfil", {}),
         "Cardápio: **Frango grelhado com ervas**, **Estrogonofe de carne**, "
         "**Arroz integral**, **Salada de grao-de-bico com amendoim**, **Abobrinha refogada**."],
        "o que tem hoje?", primeira=True,
    )
    ctx = assercoes.Contexto(
        resposta=resultado.resposta, tools=resultado.tools_chamadas,
        observacoes=resultado.observacoes, dados=dados, erro=resultado.erro,
        chamadas=list(resultado.observacoes.chamadas),
    )
    assert assercoes.conferir(ctx, {"cita_todos_os_pratos": True,
                                    "tools_obrigatorias": ["listar_pratos_do_dia"]}) == []


@pytest.mark.parametrize("caso", fakes.carregar_casos(), ids=lambda c: c["arquivo"])
def test_todo_caso_carrega_e_instala_seus_fakes(caso, monkeypatch):
    """Percorre os 60 casos sem gastar API: dataset existe, fakes instalam,
    guardrail decide como o caso espera.

    É a checagem que separa "o eval quebrou" de "o modelo piorou" — e roda de
    graça, antes de qualquer rodada paga.

    O classificador do guardrail é roteirizado porque ele é um LLM: sem isso o
    guardrail falha aberto (comportamento correto em produção, inútil aqui) e
    todo caso de fora-de-escopo passaria.
    """
    dados = fakes.carregar_dados(caso["dados"])
    fakes.instalar(monkeypatch, dados)

    fora = bool(caso["esperado"].get("deve_ser_fora_de_escopo"))
    consultas = modelo_scriptado.instalar_classificador(monkeypatch, "nao" if fora else "sim")

    mensagens = caso.get("turnos") or [caso["mensagem"]]
    barrado = not PERFIL.esta_no_escopo(mensagens[0], bool(caso.get("historico")))

    if fora:
        assert barrado, "o caso espera bloqueio do guardrail e ele deixou passar"
        assert consultas, "nenhuma keyword decidiu — o classificador tinha que ter sido consultado"
    else:
        assert not barrado, "o guardrail barrou um caso que deveria seguir"


def test_keyword_do_dominio_decide_sem_chamar_o_classificador(monkeypatch):
    """O fast-path existe por LATÊNCIA: a pergunta mais comum do produto não
    pode pagar uma inferência extra só para ser autorizada."""
    consultas = modelo_scriptado.instalar_classificador(monkeypatch, "nao")
    assert PERFIL.esta_no_escopo("qual o cardápio de hoje?", False)
    assert consultas == [], "keyword do domínio não pode custar uma chamada de modelo"


def test_mensagem_ambigua_paga_uma_chamada_de_classificador(monkeypatch):
    consultas = modelo_scriptado.instalar_classificador(monkeypatch, "nao")
    PERFIL.esta_no_escopo("me explica o teorema de Pitágoras", False)
    assert len(consultas) == 1
