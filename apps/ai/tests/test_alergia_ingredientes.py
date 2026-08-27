"""Alergia se checa contra o prato inteiro, não contra o campo `alergenos`.

Medido em 27/08/2026 no catálogo da unidade 1: 21 dos 29 alimentos cadastrados
têm `alergenos` vazio. `prato_seguro_para_alergias` só lia esse campo, então
devolvia True incondicionalmente para 72% do catálogo — o "Bife Acebolado"
(ingredientes: carne bovina, cebola, óleo) era declarado seguro para quem é
alérgico a carne bovina, e o "Arroz Branco" (arroz, alho, óleo) para quem é
alérgico a alho. O furo não é de um prato: é de toda alergia que o nutricionista
não classificou como alérgeno, que é a maioria delas.

A assimetria que rege estes testes: barrar um prato seguro custa uma opção a
menos no almoço; liberar um prato perigoso custa uma reação alérgica. Por isso
alguns testes aqui FIXAM falsos positivos como comportamento desejado ("leite"
barra "leite de coco"), e outros — os de substring — existem para impedir que o
aperto vire bloqueio cego ("salmão" não pode barrar um prato que tem "sal").
Esses últimos falham com a correção ingênua, não só com a versão antiga: eles
guardam a escolha, não o conserto.

Os pratos com `id` real vieram do banco, não foram inventados para o teste.
"""

import app.agent.dominio.refeitorio.tools as t
from app.agent.dominio.refeitorio.filters import (
    alergia_verificavel,
    conflitos_com_perfil,
    prato_seguro_para_alergias,
)


def _prato(id, nome, alergenos, ingredientes, **extra):
    base = {"id": id, "nome": nome, "categoria": "prato", "calorias": 200,
            "alergenos": alergenos, "ingredientes": ingredientes,
            "restricoes_atendidas": [], "nao_indicado_para": []}
    base.update(extra)
    return base


# --- fixtures reais (unidade 1, cardápio medido) -----------------------------

BIFE = _prato(133, "Bife Acebolado", [], ["carne bovina", "cebola", "óleo"])
ARROZ = _prato(140, "Arroz Branco", [], ["arroz", "alho", "óleo"])
STROGONOFF = _prato(2, "Strogonoff de Grão-de-Bico", ["lactose"],
                    ["grao-de-bico", "creme de leite", "tomate"])
PURE = _prato(142, "Purê de Batata", ["lactose"], ["batata", "leite", "manteiga"])
POLENTA = _prato(145, "Polenta Cremosa", [], ["fubá", "água", "sal"])
MACARRAO = _prato(143, "Macarrão ao Alho e Óleo", ["gluten"],
                  ["macarrão", "alho", "azeite", "salsinha"])
TILAPIA = _prato(134, "Tilápia Assada", ["peixe"], ["tilápia", "limão", "azeite"])
FRANGO = _prato(1, "Frango Grelhado", [], ["frango", "azeite", "alho"])


# --- o defeito ---------------------------------------------------------------

def test_ingrediente_sem_alergeno_declarado_nao_e_seguro():
    # O caso do briefing, com o dado do banco. Falhava antes: `alergenos` vazio
    # fazia a função devolver True sem olhar mais nada.
    assert not prato_seguro_para_alergias(BIFE, ["carne bovina"])


def test_alergia_fora_da_lista_classica():
    # Alho não é alérgeno "de rótulo", então ninguém preenche — e é exatamente
    # por isso que o campo `alergenos` sozinho não pode ser a barreira.
    assert not prato_seguro_para_alergias(ARROZ, ["alho"])


def test_alergeno_declarado_continua_valendo():
    # Regressão do caminho que já funcionava: cruzar ingredientes não pode
    # custar o alérgeno que o nutricionista cadastrou à mão.
    assert not prato_seguro_para_alergias(STROGONOFF, ["lactose"])
    assert not prato_seguro_para_alergias(PURE, ["lactose"])  # pelo alérgeno
    assert not prato_seguro_para_alergias(PURE, ["leite"])    # pelo ingrediente


def test_nao_bloqueia_o_que_nao_deve():
    # Sem este, "conserto" e "bloqueia tudo" ficam indistinguíveis.
    assert prato_seguro_para_alergias(FRANGO, ["peixe"])
    assert prato_seguro_para_alergias(FRANGO, ["lactose", "amendoim", "gluten"])


# --- como o termo da pessoa chega ---------------------------------------------

def test_prefixo_de_fala_e_ignorado():
    # A limpeza antiga era um replace("alergico a ", "") e não cobria "sou
    # alérgico a" nem "tenho intolerância a". Todas têm que dar o mesmo veredicto.
    for dito in ("alho", "alergico a alho", "sou alérgico a alho",
                 "tenho alergia a alho", "intolerante a alho"):
        assert not prato_seguro_para_alergias(ARROZ, [dito]), dito


def test_acento_e_caixa_nao_escapam():
    assert not prato_seguro_para_alergias(ARROZ, ["Óleo"])
    assert not prato_seguro_para_alergias(ARROZ, ["oleo"])
    assert not prato_seguro_para_alergias(TILAPIA, ["tilapia"])


def test_plural_no_ingrediente_nao_escapa():
    # Decisão explícita: ovo de codorna é ovo. Aqui o falso negativo é a reação
    # alérgica, então o plural cai antes da comparação.
    codorna = _prato(900, "Salada com ovos de codorna", [], ["alface", "ovos de codorna"])
    assert not prato_seguro_para_alergias(codorna, ["ovo"])


def test_alergia_vazia_ou_so_ruido_nao_barra_nada():
    # Um termo que reduz a conjunto vazio casaria com TUDO por contenção e
    # esvaziaria o cardápio — que é o modo de falha que mais assusta o usuário.
    for alergias in ([], [""], ["alergia a"], ["   "]):
        assert prato_seguro_para_alergias(BIFE, alergias), alergias


# --- as duas metades do trade-off --------------------------------------------

def test_leite_de_coco_e_falso_positivo_aceito():
    """Barra, e diz exatamente o que barrou.

    "leite de coco" não tem lactose, mas o código não sabe disso sem taxonomia —
    e taxonomia foi descartada de propósito. Então barra (custo: uma opção a
    menos) e NOMEIA o termo (benefício: a pessoa lê "leva leite de coco" e
    discorda com informação na mão, em vez de receber um veto opaco).
    """
    curry = _prato(901, "Curry de grão-de-bico", [], ["grão-de-bico", "leite de coco"])
    assert not prato_seguro_para_alergias(curry, ["leite"])
    motivos = conflitos_com_perfil(curry, {"alergias": ["leite"]})
    assert any("leite de coco" in m for m in motivos), motivos


def test_substring_nao_barra_palavra_diferente():
    # O guarda da escolha: se alguém trocar a comparação por token de volta por
    # substring, isto quebra. "sal" está dentro de "salmão" e de "salsinha", e
    # nenhum dos dois é o outro.
    assert prato_seguro_para_alergias(POLENTA, ["salmão"])
    assert prato_seguro_para_alergias(MACARRAO, ["sal"])
    assert prato_seguro_para_alergias(TILAPIA, ["azeitona"])  # não é "azeite"


def test_conflito_nomeia_o_ingrediente_culpado():
    # Antes da correção esta lista vinha VAZIA: o prato nem era detectado, então
    # nem o aviso que viaja junto do item na listagem era emitido.
    motivos = conflitos_com_perfil(BIFE, {"alergias": ["carne bovina"]})
    assert any("você informou" in m for m in motivos), motivos
    assert any("leva carne bovina" in m for m in motivos), motivos


def test_conflito_nao_inventa_alergeno_que_o_prato_nao_tem():
    # O texto antigo caía em `sorted(prato['alergenos'] or culpadas)` e, com a
    # checagem cruzando ingredientes, passaria a dizer o alérgeno errado.
    motivos = conflitos_com_perfil(PURE, {"alergias": ["leite"]})
    assert any("leva leite" in m for m in motivos), motivos
    assert not any("manteiga" in m for m in motivos), motivos


# --- "seguro" vs "não sei" ----------------------------------------------------

def test_prato_sem_ficha_e_nao_verificavel():
    """A incerteza é visível, mas NÃO virou bloqueio.

    Se prato sem ficha virasse inseguro, ele sumiria de `filtrar_pratos` e a
    tool cairia no "nenhum prato atende" por falta de cadastro — o mesmo modo de
    falha que já vazou tripa para o cliente. Hoje é guarda para dado futuro:
    medido, 0 de 29 pratos estão sem ingredientes.
    """
    sem_ficha = _prato(902, "Prato do dia", [], [])
    assert not alergia_verificavel(sem_ficha)
    assert prato_seguro_para_alergias(sem_ficha, ["amendoim"])
    assert alergia_verificavel(BIFE)
    assert alergia_verificavel(_prato(903, "Só alérgeno", ["peixe"], []))


# --- ponta a ponta: o prato perigoso sai da recomendação ----------------------

CARDAPIO = [BIFE, ARROZ, POLENTA, FRANGO, TILAPIA, PURE]


def test_filtrar_pratos_remove_o_prato_perigoso(monkeypatch):
    monkeypatch.setattr(t.go_api, "get_pratos", lambda u, d: [dict(p) for p in CARDAPIO])
    monkeypatch.setattr(t, "current_context",
                        lambda: type("C", (), {"unidade_id": 1, "usuario_id": None})())

    saida = t.filtrar_pratos.invoke({"alergias": "carne bovina", "dia": "hoje"})
    nomes = [p["nome"] for p in saida]
    assert "Bife Acebolado" not in nomes
    # E o resto do cardápio continua de pé: o aperto não pode virar lista vazia,
    # que é o estado em que a Lia começa a improvisar.
    assert "Frango Grelhado" in nomes


def test_filtrar_pratos_ainda_recomenda_para_alergia_irrelevante(monkeypatch):
    monkeypatch.setattr(t.go_api, "get_pratos", lambda u, d: [dict(p) for p in CARDAPIO])
    monkeypatch.setattr(t, "current_context",
                        lambda: type("C", (), {"unidade_id": 1, "usuario_id": None})())

    saida = t.filtrar_pratos.invoke({"alergias": "amendoim", "dia": "hoje"})
    assert len(saida) == len(CARDAPIO)
