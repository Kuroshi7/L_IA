"""O casamento de alergia não pode punir quem escreveu certo.

Três defeitos medidos em 27/08/2026, na revisão da mudança que trocou substring
por palavra inteira. Todos LIBERAM prato perigoso, que é o lado caro da
assimetria declarada no topo de `filters.py`:

1. PLURAL IRREGULAR. Cortar um "s" final resolve "ovos"→"ovo" e mais nada. A
   ANVISA (RDC 26/2015) manda imprimir o alérgeno no rótulo no plural — "nozes",
   "castanhas", "amêndoas" —, e é essa a grafia que a nutricionista copia para a
   ficha, enquanto a pessoa digita o singular no perfil. "nozes" virava "noze" e
   não encontrava "noz". Era regressão: por substring, o código antigo barrava.

2. CONTENÇÃO NÃO MONOTÔNICA. Exigindo que um conjunto de palavras contivesse o
   outro, declarar a alergia com MAIS detalhe protegia MENOS: "leite" barrava o
   ingrediente "creme de leite", "leite de vaca" não barrava nada.

3. GRUPO SEM MEMBRO. "frutos do mar" é uma das quatro alergias que o próprio
   formulário do perfil oferece num clique (`ALERGIAS_COMUNS` em Perfil.tsx),
   sob a promessa literal "A Lia nunca sugere um prato com algo desta lista". A
   palavra não aparece em ficha nenhuma: o que está escrito lá é "camarão".

Os testes de "não bloqueia demais" vivem em `test_alergia_ingredientes.py` e
continuam valendo: o aperto aqui não pode virar bloqueio cego.
"""

import pytest

from app.agent.dominio.refeitorio.filters import (
    conflitos_com_perfil,
    prato_seguro_para_alergias,
)


def _prato(nome, alergenos, ingredientes):
    return {"id": 1, "nome": nome, "categoria": "prato", "calorias": 200,
            "alergenos": alergenos, "ingredientes": ingredientes,
            "restricoes_atendidas": [], "nao_indicado_para": []}


# --- 1. plural irregular ------------------------------------------------------

# Cada par é (o que a ficha do prato diz, o que a pessoa escreveu no perfil).
# Os dois sentidos entram porque nenhum dos dois lados é a fonte canônica: a
# ficha copia o rótulo, o perfil é texto livre.
PARES_DE_PLURAL = [
    ("nozes", "noz"), ("noz", "nozes"),
    ("camarões", "camarão"), ("camarão", "camarões"),
    ("amendoins", "amendoim"), ("amendoim", "amendoins"),
    ("pães", "pão"), ("pão", "pães"),
    ("castanhas", "castanha"),
    ("açúcares", "açúcar"),
    ("ovos de codorna", "ovo"),
]


@pytest.mark.parametrize("na_ficha,no_perfil", PARES_DE_PLURAL)
def test_plural_irregular_nao_libera_o_prato(na_ficha, no_perfil):
    prato = _prato("Prato do dia", [], ["farinha", na_ficha])
    assert not prato_seguro_para_alergias(prato, [no_perfil])


def test_plural_no_campo_alergenos_tambem_conta():
    # O caminho do briefing: a nutricionista cadastra a grafia do rótulo em
    # `alergenos` e a pessoa declara o singular. Antes: prato LIBERADO.
    bolo = _prato("Bolo de nozes", ["nozes"], ["farinha", "nozes", "ovo"])
    assert not prato_seguro_para_alergias(bolo, ["noz"])
    assert conflitos_com_perfil(bolo, {"alergias": ["noz"]})


# --- 2. quanto mais precisa a declaração, não menos proteção ------------------

def test_declaracao_mais_especifica_nao_protege_menos():
    """A monotonicidade, que é a propriedade e não o exemplo.

    "leite de vaca" é como se declara APLV, a alergia alimentar mais comum do
    país, e o campo do perfil é texto livre. Se acrescentar palavra pudesse
    desligar o bloqueio, o formulário estaria punindo quem responde direito.
    """
    strogonoff = _prato("Strogonoff de Grão-de-Bico", ["lactose"],
                        ["grao-de-bico", "creme de leite", "tomate"])
    for declarada in ("leite", "leite de vaca", "proteína do leite de vaca",
                      "alergia a leite de vaca", "lactose"):
        assert not prato_seguro_para_alergias(strogonoff, [declarada]), declarada


def test_nome_composto_casa_pela_palavra_que_importa():
    # "castanha de caju" × "castanha do pará": nenhum dos dois contém o outro, e
    # os dois são castanha. Com contenção, a pessoa mais específica passava.
    bolo = _prato("Bolo", [], ["farinha", "castanha do pará"])
    assert not prato_seguro_para_alergias(bolo, ["castanha de caju"])


# --- 3. o chip que o produto entrega pronto ------------------------------------

@pytest.mark.parametrize("ingrediente", ["camarão", "camarões", "lula", "marisco", "polvo"])
def test_frutos_do_mar_casa_com_os_frutos_do_mar(ingrediente):
    # A promessa está escrita na tela do perfil; até esta correção ela casava
    # com NADA, porque nenhuma ficha escreve "frutos do mar".
    risoto = _prato("Risoto", [], ["arroz", ingrediente, "manteiga"])
    assert not prato_seguro_para_alergias(risoto, ["frutos do mar"])


def test_frutos_do_mar_pega_o_alergeno_peixe():
    peixe = _prato("Peixe Assado", ["peixe"], ["tilápia", "limão"])
    assert not prato_seguro_para_alergias(peixe, ["frutos do mar"])


def test_grupo_reconhecido_dentro_de_frase_livre():
    # O campo é texto livre e a Lia também escreve nele.
    risoto = _prato("Risoto", [], ["arroz", "camarão"])
    assert not prato_seguro_para_alergias(risoto, ["sou alérgica a frutos do mar"])


def test_grupo_nao_arrasta_prato_sem_relacao():
    # O outro lado: expandir grupo não pode virar bloqueio cego do cardápio.
    frango = _prato("Frango Grelhado", [], ["frango", "azeite", "alho"])
    assert prato_seguro_para_alergias(frango, ["frutos do mar"])


# --- o motivo continua honesto -------------------------------------------------

def test_motivo_cita_o_termo_do_prato_e_nao_o_do_grupo():
    """A expansão é interna; o que a pessoa lê é o que o prato realmente leva.

    Dizer "este prato leva frutos do mar" quando a ficha diz "camarão" é
    inventar dado — e é a mentira que `culpados_por_alergia` foi escrita para
    não contar, porque mentira sobre alergia queima a confiança onde ela é vital.
    """
    risoto = _prato("Risoto", [], ["arroz", "camarão"])
    motivos = conflitos_com_perfil(risoto, {"alergias": ["frutos do mar"]})

    assert any("você informou alergia a frutos do mar" in m for m in motivos), motivos
    assert any("leva camarão" in m for m in motivos), motivos


def test_motivo_comeca_pelo_termo_que_a_pessoa_escreveu():
    # O sinônimo técnico entra depois, nunca no lugar: quem declarou "leite"
    # precisa ler "leva leite" antes de "lactose", senão o aviso parece de outro
    # prato.
    pure = _prato("Purê de Batata", ["lactose"], ["batata", "leite", "manteiga"])
    motivos = conflitos_com_perfil(pure, {"alergias": ["leite"]})
    assert any("leva leite" in m for m in motivos), motivos
