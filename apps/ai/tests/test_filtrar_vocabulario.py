"""`filtrar_pratos` conhece o próprio vocabulário e não mente quando não sabe filtrar.

Conversa real medida em 27/08/2026: a pessoa disse "eu nao como carne vermelha" e o
modelo chamou `filtrar_pratos(restricoes='sem carne vermelha')`. O campo `restricoes`
tem vocabulário FECHADO — só casa com o que o cardápio declarou em `restricoes_atendidas`
—, então nenhum prato passou e o tool devolveu "Nenhum prato do cardápio atende a esses
critérios. NÃO sugira nada fora do cardápio…". Um falso negativo com voz de autoridade.
O modelo obedeceu, corretamente, e ficou preso: 5 chamadas mortas no turno, e mais 5 no
turno seguinte. A Lia acabou dizendo ao CLIENTE "o sistema está muito rigoroso" e "parece
que não está funcionando".

O conserto é o tool declarar o vocabulário que ele filtra e devolver a decisão ao modelo,
com os `ingredientes` na mão. Metade dos testes abaixo protege contra o conserto EXAGERAR:
rotear um termo que o código sabe filtrar é entregar ao modelo uma decisão que hoje é
determinística — que é como esta mudança abriria um buraco de segurança novo.
"""

import pytest

import app.agent.dominio.refeitorio.tools as t
from app.agent.dominio.refeitorio import prompts
from app.agent.motor.observacao import encerrar_turno, iniciar_turno

# Cardápio no formato que a API Go devolve. O vocabulário declarado aqui é
# {vegetariano, sem lactose}: "sem carne vermelha" está fora dele, e o Bife é o
# prato que só os INGREDIENTES denunciam.
VEGGIE = {"id": 1, "nome": "Arroz integral com legumes", "categoria": "acompanhamento",
          "calorias": 180, "proteinas_g": 5,
          "restricoes_atendidas": ["vegetariano", "sem lactose"], "nao_indicado_para": [],
          "alergenos": [], "ingredientes": ["arroz integral", "cenoura", "abobrinha"]}
BIFE = {"id": 2, "nome": "Bife Acebolado", "categoria": "proteina",
        "calorias": 320, "proteinas_g": 28,
        "restricoes_atendidas": [], "nao_indicado_para": ["vegetariano"],
        "alergenos": [], "ingredientes": ["carne bovina", "cebola", "óleo"]}
PEIXE = {"id": 3, "nome": "Filé de tilápia grelhado", "categoria": "proteina",
         "calorias": 210, "proteinas_g": 30,
         "restricoes_atendidas": ["sem lactose"], "nao_indicado_para": [],
         "alergenos": ["peixe"], "ingredientes": ["tilápia", "limão"]}
AMENDOIM = {"id": 4, "nome": "Salada de grão-de-bico com amendoim", "categoria": "salada",
            "calorias": 150, "proteinas_g": 9,
            "restricoes_atendidas": ["vegetariano", "sem lactose"], "nao_indicado_para": [],
            "alergenos": ["amendoim"], "ingredientes": ["grão-de-bico", "amendoim"]}

CARDAPIO = [VEGGIE, BIFE, PEIXE]


def _cardapio(monkeypatch, pratos, usuario_id=None):
    monkeypatch.setattr(t.go_api, "get_pratos", lambda u, d: [dict(p) for p in pratos])
    monkeypatch.setattr(
        t, "current_context",
        lambda: type("C", (), {"unidade_id": 1, "usuario_id": usuario_id})(),
    )


@pytest.fixture
def cardapio(monkeypatch):
    _cardapio(monkeypatch, CARDAPIO)
    return CARDAPIO


# --- o defeito medido --------------------------------------------------------

def test_termo_fora_do_vocabulario_nao_devolve_vazio(cardapio):
    # O T2 da conversa real, virado teste. Sem a correção, isto é a string
    # "Nenhum prato do cardápio atende a esses critérios."
    out = t.filtrar_pratos.invoke({"restricoes": "sem carne vermelha", "dia": "hoje"})

    assert not isinstance(out, str), out
    assert "Nenhum prato do cardápio atende" not in str(out)
    assert out["pratos"], "o cardápio tem pratos: nenhum deles podia sumir"


def test_roteamento_diz_o_vocabulario_e_entrega_os_ingredientes(cardapio):
    # A instrução sozinha é palavra solta: o modelo só consegue decidir "isso é
    # carne vermelha?" se os ingredientes vierem na mesma resposta.
    out = t.filtrar_pratos.invoke({"restricoes": "sem carne vermelha", "dia": "hoje"})

    assert "sem carne vermelha" in out["nao_filtrei_por"]
    assert {"vegetariano", "sem lactose"} == set(out["vocabulario_de_restricoes"])
    assert all(p.get("ingredientes") for p in out["pratos"])

    nota = out["nota_do_sistema"]
    assert "sem carne vermelha" in nota and "ingredientes" in nota
    # O tool precisa dizer que NÃO filtrou — e que isso não é o mesmo que "nada serve".
    assert "NÃO filtrei por" in nota
    # E precisa proibir explicitamente o que a Lia fez com o cliente.
    assert "sistema" in nota and "falhou" in nota


def test_nota_de_roteamento_manda_usar_preferencias_e_nao_repetir(cardapio):
    # As 5 chamadas idênticas no mesmo turno vieram de o modelo não ter para onde
    # ir depois do resultado morto. A nota fecha as duas saídas: repetir e insistir.
    nota = t.filtrar_pratos.invoke({"restricoes": "sem carne vermelha"})["nota_do_sistema"]
    assert "preferencias" in nota
    assert "não repita" in nota.lower()


# --- guardas contra rotear DEMAIS --------------------------------------------

def test_termo_do_vocabulario_sem_prato_ainda_diz_nenhum_atende(monkeypatch):
    # Vocabulário {vegetariano} vindo APENAS de `nao_indicado_para`. Aqui a
    # resposta certa continua sendo "filtrei e nada atende": rotear soltaria para
    # o modelo justamente o prato marcado como não indicado.
    _cardapio(monkeypatch, [BIFE, PEIXE])
    out = t.filtrar_pratos.invoke({"restricoes": "vegetariano", "dia": "hoje"})

    assert isinstance(out, str)
    assert "Nenhum prato do cardápio atende" in out


def test_equivalencia_continua_filtrando(monkeypatch):
    # 'celiaco' → 'sem gluten' é equivalência de `filters`. Se a checagem de
    # vocabulário fosse literal, celíaco viraria roteamento e a barreira
    # determinística do glúten viraria decisão do modelo.
    sem_gluten = {**PEIXE, "restricoes_atendidas": ["sem gluten"]}
    _cardapio(monkeypatch, [BIFE, sem_gluten])

    out = t.filtrar_pratos.invoke({"restricoes": "celiaco", "dia": "hoje"})
    assert isinstance(out, list)
    assert [p["id"] for p in out] == [sem_gluten["id"]]


def test_acento_e_caixa_nao_viram_termo_desconhecido(monkeypatch):
    sem_gluten = {**PEIXE, "restricoes_atendidas": ["sem gluten"]}
    _cardapio(monkeypatch, [BIFE, sem_gluten])

    out = t.filtrar_pratos.invoke({"restricoes": "Sem Glúten", "dia": "hoje"})
    assert isinstance(out, list) and [p["id"] for p in out] == [sem_gluten["id"]]


def test_cardapio_vazio_nao_vira_roteamento(monkeypatch):
    # Sem pratos o vocabulário é vazio, logo TODO termo pareceria desconhecido —
    # e o roteamento mandaria o modelo escolher pelos ingredientes de uma lista
    # que não existe. Cardápio não publicado tem mensagem própria.
    _cardapio(monkeypatch, [])
    out = t.filtrar_pratos.invoke({"restricoes": "sem carne vermelha", "dia": "hoje"})

    assert out["pratos"] == []
    assert "não foi publicado" in out["nota_do_sistema"]
    assert "NÃO sugira" in out["nota_do_sistema"]
    assert "nao_filtrei_por" not in out


def test_sucesso_continua_devolvendo_lista(cardapio):
    # Contrato do caminho feliz, do qual tests/test_turn.py depende.
    out = t.filtrar_pratos.invoke({"restricoes": "vegetariano", "dia": "hoje"})
    assert isinstance(out, list)
    assert [p["id"] for p in out] == [VEGGIE["id"]]


# --- a assimetria decidida: alergia é código, restrição aberta é modelo -------

def test_termo_conhecido_e_desconhecido_na_mesma_chamada(cardapio):
    # O conhecido TEM de continuar valendo. Rotear a chamada inteira porque um
    # termo é aberto jogaria fora o filtro que o código sabe fazer.
    out = t.filtrar_pratos.invoke({"restricoes": "vegetariano,sem carne vermelha"})

    assert out["nao_filtrei_por"] == ["sem carne vermelha"]
    assert out["restricoes_aplicadas"] == ["vegetariano"]
    assert [p["id"] for p in out["pratos"]] == [VEGGIE["id"]]


def test_alergia_continua_deterministica_no_roteamento(monkeypatch):
    # Alergia nunca é delegada ao modelo: errar aqui machuca. O roteamento vale
    # para restrição aberta, e só.
    _cardapio(monkeypatch, [VEGGIE, BIFE, AMENDOIM])
    out = t.filtrar_pratos.invoke({"restricoes": "sem carne vermelha", "alergias": "amendoim"})

    assert AMENDOIM["id"] not in [p["id"] for p in out["pratos"]]
    assert out["pratos"], "só o prato com amendoim devia ter saído"


def test_conflito_com_perfil_sobrevive_ao_roteamento(monkeypatch):
    # `conflita_com_perfil` é o insumo da regra bloqueante de segurança alimentar.
    # Ele é anotado dentro do turno; o ramo de roteamento não pode perdê-lo.
    _cardapio(monkeypatch, CARDAPIO, usuario_id=7)
    monkeypatch.setattr(t.go_api, "get_perfil",
                        lambda uid: {"nome": "Joao", "alergias": ["peixe"], "restricoes": []})

    token = iniciar_turno()
    try:
        out = t.filtrar_pratos.invoke({"restricoes": "sem carne vermelha", "dia": "hoje"})
    finally:
        encerrar_turno(token)

    anotados = [p for p in out["pratos"] if p.get("conflita_com_perfil")]
    assert [p["id"] for p in anotados] == [PEIXE["id"]]


def test_nota_de_roteamento_nao_dispara_a_r4(cardapio):
    # A R4 se ancora em MARCA_INCERTEZA. Se a nota de roteamento carregasse esse
    # prefixo, toda recomendação filtrada passaria a exigir ressalva de incerteza.
    out = t.filtrar_pratos.invoke({"restricoes": "sem carne vermelha"})
    assert t.MARCA_INCERTEZA not in out["nota_do_sistema"]


# --- o vocabulário é dado, não código ----------------------------------------

def test_vocabulario_vem_do_dado(monkeypatch):
    # Rótulo inventado por uma unidade qualquer: se ele está no cardápio, o tool
    # filtra por ele. É o que permite cada unidade (e amanhã cada tenant)
    # cadastrar o próprio vocabulário sem tocar em código.
    picante = {**BIFE, "restricoes_atendidas": ["sem pimenta"], "nao_indicado_para": []}
    _cardapio(monkeypatch, [VEGGIE, picante])

    out = t.filtrar_pratos.invoke({"restricoes": "sem pimenta", "dia": "hoje"})
    assert isinstance(out, list) and [p["id"] for p in out] == [picante["id"]]


def test_cardapios_diferentes_produzem_vocabularios_diferentes():
    de_hoje = t._vocabulario_de_restricoes([VEGGIE, BIFE])
    de_outra_unidade = t._vocabulario_de_restricoes(
        [{"restricoes_atendidas": ["low carb", "proteico"], "nao_indicado_para": []}]
    )
    assert set(de_hoje) == {"vegetariano", "sem lactose"}
    assert set(de_outra_unidade) == {"low carb", "proteico"}


def test_vocabulario_devolve_a_grafia_cadastrada():
    # O texto vai para o modelo, e ele repete o que lê: "sem gluten" cru na fala
    # da Lia soa a dado de sistema. Deduplicar não pode custar o acento.
    vocab = t._vocabulario_de_restricoes([
        {"restricoes_atendidas": ["Sem Glúten"], "nao_indicado_para": []},
        {"restricoes_atendidas": ["sem gluten"], "nao_indicado_para": []},
    ])
    assert vocab == ["Sem Glúten"]


# --- âncoras de contrato -----------------------------------------------------

def test_docstring_declara_os_dois_vocabularios():
    # A description é o schema que o modelo lê ANTES de escolher o campo — é o
    # primeiro ponto onde o erro do T2 podia ter sido evitado. Antes, ela
    # descrevia `restricoes` e `preferencias` como se fossem simétricos.
    desc = t.filtrar_pratos.description
    assert "FECHADO" in desc and "ABERTO" in desc
    assert "sem carne vermelha" in desc


def test_prompt_proibe_relatar_falha_interna_ao_cliente():
    # A Lia disse ao usuário final "o sistema está muito rigoroso" e "parece que
    # não está funcionando". É cinto, não o conserto: a causa (o falso negativo)
    # morre no tool.
    regra = prompts.SYSTEM_AGENT
    assert "funcionamento interno" in regra
    assert "rigoroso" in regra


def test_prompt_diz_onde_vai_o_pedido_aberto():
    assert "sem carne vermelha" in prompts.SYSTEM_AGENT
