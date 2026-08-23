"""O eval também precisa de teste.

Um harness de eval que aceita qualquer resposta dá falsa segurança: fica verde
todo dia e ninguém percebe que ele parou de checar. Estes testes rodam SEM LLM,
em todo commit, e provam que as asserções realmente reprovam o que deveriam.
"""

import pytest

from app.agent.motor.observacao import ObservacoesDoTurno
from app.agent.motor.turn import ResultadoDeTurno
from tests.eval import fakes
from tests.eval.test_eval_llm import _conferir

CAMPOS_OBRIGATORIOS = ("nome", "porque", "dados", "mensagem", "esperado")


# --- integridade dos casos ----------------------------------------------------

def test_todos_os_casos_estao_completos():
    casos = fakes.carregar_casos()
    assert len(casos) >= 10, "cobertura mínima do eval encolheu"
    for caso in casos:
        faltando = [c for c in CAMPOS_OBRIGATORIOS if not caso.get(c)]
        assert not faltando, f"{caso.get('nome', '?')}: campos faltando {faltando}"


def test_todo_caso_aponta_para_um_dataset_existente():
    for caso in fakes.carregar_casos():
        dados = fakes.carregar_dados(caso["dados"])  # levanta se não existir
        assert "pratos" in dados and "perfil" in dados


def test_os_casos_cobrem_as_regras_criticas():
    # Se alguém apagar o caso da regra contratual ou o da incerteza, o eval
    # continuaria verde sem cobrir o que mais importa no produto.
    esperados = [c["esperado"] for c in fakes.carregar_casos()]
    assert any(e.get("cita_todos_os_pratos") for e in esperados), "sem caso da regra contratual"
    assert any(e.get("ressalva_incerteza") for e in esperados), "sem caso de incerteza declarada"
    assert any(e.get("nao_deve_recomendar") for e in esperados), "sem caso de restrição/alergia"
    assert any(e.get("deve_ser_fora_de_escopo") for e in esperados), "sem caso de guardrail"


# --- as asserções realmente reprovam -----------------------------------------

DADOS = fakes.carregar_dados("padrao")


def _resultado(resposta, tools=(), retornos=()):
    obs = ObservacoesDoTurno()
    for i, r in enumerate(retornos):
        obs.registrar((f"t{i}", "{}"), r)
    return ResultadoDeTurno(resposta=resposta, tools_chamadas=list(tools), observacoes=obs)


def test_reprova_prato_inventado():
    caso = {"nome": "x", "porque": "x", "esperado": {"sem_prato_inventado": True}}
    r = _resultado("Recomendo **Feijoada completa**.", tools=["filtrar_pratos"],
                   retornos=[DADOS["pratos"]])
    assert any("R2" in f for f in _conferir(caso, r, DADOS))


def test_aprova_prato_do_cardapio():
    caso = {"nome": "x", "porque": "x", "esperado": {"sem_prato_inventado": True}}
    r = _resultado("Recomendo **Frango grelhado com ervas**.", tools=["filtrar_pratos"],
                   retornos=[DADOS["pratos"]])
    assert _conferir(caso, r, DADOS) == []


def test_reprova_alergeno_recomendado():
    caso = {"nome": "x", "porque": "x",
            "esperado": {"nao_deve_recomendar": ["Salada de grao-de-bico com amendoim"]}}
    r = _resultado("Sugiro a Salada de grao-de-bico com amendoim.", tools=["filtrar_pratos"])
    falhas = _conferir(caso, r, DADOS)
    assert falhas and "proíbe" in falhas[0]


def test_reprova_cardapio_incompleto_na_primeira_do_dia():
    caso = {"nome": "x", "porque": "x", "esperado": {"cita_todos_os_pratos": True}}
    r = _resultado("Recomendo o Frango grelhado.", tools=["listar_pratos_do_dia"])
    falhas = _conferir(caso, r, DADOS)
    assert falhas and "regra contratual" in falhas[0]


def test_reprova_tool_obrigatoria_ausente():
    caso = {"nome": "x", "porque": "x", "esperado": {"tools_obrigatorias": ["registrar_consumo"]}}
    falhas = _conferir(caso, _resultado("Anotado!", tools=["meu_perfil"]), DADOS)
    assert falhas and "não chamou registrar_consumo" in falhas[0]


def test_reprova_incerteza_nao_declarada():
    caso = {"nome": "x", "porque": "x", "esperado": {"ressalva_incerteza": True}}
    falhas = _conferir(caso, _resultado("Total de 198 kcal. Mandou bem!"), DADOS)
    assert falhas and "não ressalvou" in falhas[0]


def test_aprova_incerteza_declarada():
    caso = {"nome": "x", "porque": "x", "esperado": {"ressalva_incerteza": True}}
    r = _resultado("Não reconheci 'escondidinho da vovó', então ele não entrou na conta: deu 198 kcal.")
    assert _conferir(caso, r, DADOS) == []


def test_reprova_turno_que_falhou():
    caso = {"nome": "x", "porque": "x", "esperado": {"sem_prato_inventado": True}}
    r = ResultadoDeTurno(resposta="...", erro="PrazoEsgotado")
    assert _conferir(caso, r, DADOS) == ["turno falhou: PrazoEsgotado"]


@pytest.mark.parametrize("esperado_fora, resultado_nulo, deve_falhar", [
    (True, True, False),    # esperava barrar e barrou
    (True, False, True),    # esperava barrar e passou
    (False, True, True),    # não esperava barrar e barrou
])
def test_guardrail_e_conferido_nos_dois_sentidos(esperado_fora, resultado_nulo, deve_falhar):
    caso = {"nome": "x", "porque": "x", "esperado": {"deve_ser_fora_de_escopo": esperado_fora}}
    r = None if resultado_nulo else _resultado("resposta qualquer")
    assert bool(_conferir(caso, r, DADOS)) is deve_falhar
