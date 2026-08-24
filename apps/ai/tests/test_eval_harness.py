"""O eval também precisa de teste.

Um harness que aceita qualquer resposta dá falsa segurança: fica verde todo dia
e ninguém percebe que parou de checar. Estes testes rodam SEM LLM, em todo
commit, e provam que as asserções reprovam o que deveriam.
"""

import pytest

from app.agent.motor.observacao import ObservacoesDoTurno
from tests.eval import assercoes, fakes

CAMPOS_OBRIGATORIOS = ("nome", "porque", "dados", "esperado")
COBERTURA_MINIMA_POR_BATERIA = 10


# --- integridade das baterias ------------------------------------------------

def test_baterias_tem_massa_suficiente():
    """Resolução de medição, não cobertura por cobertura.

    Com 10 casos no total, cada um valia 10 pontos e a variância entre rodadas
    chegou a 20. Com 6 por bateria ainda valia 5,5 — o suficiente para uma
    oscilação parecer regressão. Com 10 por bateria, um caso vale 3,3.
    """
    casos = fakes.carregar_casos()
    assert len(casos) >= 55, f"apenas {len(casos)} casos — amostra pequena demais para ser gate"
    for bateria in fakes.baterias():
        n = len(fakes.carregar_casos(bateria))
        assert n >= COBERTURA_MINIMA_POR_BATERIA, f"bateria {bateria} com só {n} casos"


def test_todos_os_casos_estao_completos():
    for caso in fakes.carregar_casos():
        faltando = [c for c in CAMPOS_OBRIGATORIOS if not caso.get(c)]
        assert not faltando, f"{caso.get('nome', caso['arquivo'])}: campos faltando {faltando}"
        assert caso.get("mensagem") or caso.get("turnos"), f"{caso['nome']}: sem mensagem nem turnos"


def test_todo_caso_usa_assercao_existente():
    # Erro de digitação numa chave faria o caso passar sem checar nada.
    validas = set(assercoes.ASSERCOES) | {"deve_ser_fora_de_escopo"}
    for caso in fakes.carregar_casos():
        desconhecidas = set(caso["esperado"]) - validas
        assert not desconhecidas, f"{caso['nome']}: asserção inexistente {sorted(desconhecidas)}"


def test_todo_caso_aponta_para_dataset_existente():
    for caso in fakes.carregar_casos():
        dados = fakes.carregar_dados(caso["dados"])
        assert "pratos" in dados and "perfil" in dados


def test_as_regras_criticas_estao_cobertas():
    esperados = [c["esperado"] for c in fakes.carregar_casos()]
    assert any(e.get("cita_todos_os_pratos") for e in esperados), "sem caso da regra contratual"
    assert any(e.get("sem_alergeno") for e in esperados), "sem caso de alergia"
    assert any(e.get("sem_restricao_violada") for e in esperados), "sem caso de restrição"
    assert any(e.get("ressalva_incerteza") for e in esperados), "sem caso de incerteza declarada"
    assert any(e.get("previa_antes_de_gravar") for e in esperados), "sem caso do registro em 2 etapas"
    assert any(e.get("deve_ser_fora_de_escopo") for e in esperados), "sem caso de guardrail"


def test_juiz_e_minoria():
    # O juiz custa API e é estocástico. Se a maioria dos casos depender dele, o
    # eval virou opinião cara em vez de medição.
    casos = fakes.carregar_casos()
    com_juiz = [c for c in casos if "juiz" in c["esperado"]]
    assert len(com_juiz) / len(casos) < 0.5, "juiz demais: prefira asserção estrutural"


# --- as asserções realmente reprovam ----------------------------------------

DADOS = fakes.carregar_dados("padrao")


def _ctx(resposta, tools=(), retornos=(), chamadas=(), erro=None, dados=None):
    obs = ObservacoesDoTurno()
    for i, r in enumerate(retornos):
        obs.registrar((f"t{i}", "{}"), r)
    return assercoes.Contexto(
        resposta=resposta, tools=list(tools), observacoes=obs,
        dados=dados or DADOS, erro=erro, chamadas=list(chamadas),
    )


def test_reprova_prato_inventado():
    ctx = _ctx("Recomendo a **Feijoada Completa**.", tools=["filtrar_pratos"], retornos=[DADOS["pratos"]])
    assert assercoes.conferir(ctx, {"sem_prato_inventado": True})


def test_aprova_prato_do_cardapio():
    ctx = _ctx("Recomendo o **Frango grelhado com ervas**.", tools=["filtrar_pratos"], retornos=[DADOS["pratos"]])
    assert assercoes.conferir(ctx, {"sem_prato_inventado": True}) == []


def test_alergeno_no_cardapio_nao_e_alergeno_recomendado():
    # A regra contratual OBRIGA listar o cardápio inteiro, que inclui o alérgeno.
    cardapio = "Cardapio: Frango grelhado, Salada de grao-de-bico com amendoim. Recomendo o Frango grelhado."
    assert assercoes.conferir(_ctx(cardapio), {"sem_alergeno": ["amendoim"]}) == []


def test_alergeno_recomendado_reprova():
    texto = "Cardapio: Frango grelhado, Salada de grao-de-bico com amendoim. Recomendo a Salada de grao-de-bico."
    falhas = assercoes.conferir(_ctx(texto), {"sem_alergeno": ["amendoim"]})
    assert falhas and "alérgeno" in falhas[0]


def test_restricao_violada_reprova():
    texto = "Recomendo o Estrogonofe de carne, é o mais proteico."
    falhas = assercoes.conferir(_ctx(texto), {"sem_restricao_violada": ["vegetariano"]})
    assert falhas and "não indicado" in falhas[0]


def test_cardapio_incompleto_reprova():
    falhas = assercoes.conferir(_ctx("Recomendo o Frango grelhado."), {"cita_todos_os_pratos": True})
    assert falhas and "contratual" in falhas[0]


def test_tools_proibidas():
    ctx = _ctx("...", tools=["meu_perfil", "listar_pratos_do_dia"])
    assert assercoes.conferir(ctx, {"tools_proibidas": ["meu_perfil"]})
    assert assercoes.conferir(ctx, {"tools_proibidas": ["meus_pontos"]}) == []


def test_previa_antes_de_gravar():
    ok = _ctx("Anotado!", chamadas=[("registrar_consumo", '{"k": {"confirmado": false}}'),
                                    ("registrar_consumo", '{"k": {"confirmado": true}}')])
    assert assercoes.conferir(ok, {"previa_antes_de_gravar": True}) == []

    direto = _ctx("Anotado!", chamadas=[("registrar_consumo", '{"k": {"confirmado": true}}')])
    assert assercoes.conferir(direto, {"previa_antes_de_gravar": True})

    nenhum = _ctx("Anotado!", chamadas=[("meu_perfil", "{}")])
    assert assercoes.conferir(nenhum, {"previa_antes_de_gravar": True})


def test_turno_com_erro_reprova_tudo():
    ctx = _ctx("...", erro="PrazoEsgotado")
    assert assercoes.conferir(ctx, {"sem_prato_inventado": True}) == ["turno falhou: PrazoEsgotado"]


def test_asercao_inexistente_no_caso_e_denunciada():
    falhas = assercoes.conferir(_ctx("ok"), {"asercao_que_nao_existe": True})
    assert falhas and "inexistente" in falhas[0]


@pytest.mark.parametrize("valor, deve_falhar", [(True, True), (False, False)])
def test_asercao_desligada_com_false_nao_roda(valor, deve_falhar):
    ctx = _ctx("Recomendo a **Feijoada Completa**.", tools=["filtrar_pratos"], retornos=[DADOS["pratos"]])
    assert bool(assercoes.conferir(ctx, {"sem_prato_inventado": valor})) is deve_falhar
