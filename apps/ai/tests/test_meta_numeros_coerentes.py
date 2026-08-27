"""O prato servido e o "máximo de hoje" anunciado precisam ser o mesmo mundo.

Defeitos achados na revisão de `porcionamento.py`. O módulo ainda não está ligado
a nenhuma tool; estes testes existem para que ele não seja ligado com eles dentro.

1. O teto anunciado era calculado com 1 porção por prato, enquanto `montar`
   compõe com 2 e limita a bandeja em 5. Nos dois sentidos o número saía errado:
   menor que o prato servido (a Lia entrega 26 g e diz que hoje o máximo é 18,5)
   ou maior que a meta que a mesma frase declara inalcançável. É a classe do
   IA-20 — o mesmo número saindo com dois valores na mesma resposta — que o
   cabeçalho do módulo cita como motivação.

2. A nota tratava três fracassos como dois. Cardápio não publicado virava culpa
   das restrições da pessoa ("hoje não tem nada sem X" sobre um cardápio que
   ninguém cadastrou), e prato excluído por conflito virava convite a
   flexibilizar — o que, quando o motivo é alergia, é o movimento contrário a
   toda a assimetria de `filters.py`.
"""

import pytest

from app.agent.dominio.refeitorio import porcionamento as pc


def _prato(id, nome, kcal, prot, carb, **extra):
    return {"id": id, "nome": nome, "calorias": kcal, "proteinas_g": prot,
            "carboidratos_g": carb, "gorduras_g": 0.0, **extra}


@pytest.fixture
def cardapio():
    # Os cinco pratos do cardápio medido da unidade 1 sem o Bife Acebolado — o
    # cenário do T2, em que a meta de 22 g não cabe numa porção de cada.
    return [
        _prato(1, "Arroz Branco", 130, 2.30, 32.30),
        _prato(2, "Feijão Preto", 110, 4.40, 12.20),
        _prato(4, "Lentilha Refogada", 115, 7.10, 18.20),
        _prato(5, "Brócolis no Vapor", 35, 3.00, 5.50),
        _prato(6, "Salada de Beterraba", 45, 1.70, 9.50),
    ]


# --- 1. número com procedência ------------------------------------------------

def test_o_maximo_anunciado_nunca_e_menor_que_o_prato_servido(cardapio):
    """O defeito, medido: com o teto de produção (2 porções), `montar` chega a
    26 g de proteína e a nota anunciava 18,5 g como o máximo do dia."""
    meta = pc.Meta.de_argumentos(proteinas_g=30)
    composicao = pc.montar(cardapio, meta)

    assert not all(composicao.atingiu.values()), "o cenário exige uma meta inalcançável"
    teto = composicao.para_tool()["maximo_no_cardapio"]
    for macro in pc.MACROS:
        assert teto[macro] + 0.01 >= composicao.totais[macro], (
            f"{macro}: prato servido {composicao.totais[macro]} > máximo anunciado {teto[macro]}"
        )


def test_o_maximo_anunciado_respeita_a_bandeja():
    # Oito pratos iguais: somar uma porção de cada dá 24 g, mas a bandeja só
    # comporta 5 porções, então 15 g é o que existe de verdade. Anunciar 24 g é
    # dizer que a meta de 22 g está ao alcance na mesma frase em que se diz que
    # não está.
    pratos = [_prato(i, f"Prato {i}", 100, 3.0, 10.0) for i in range(1, 9)]
    teto = pc.maximo_alcancavel(pratos, pc.TETO_POR_PRATO, pc.TETO_TOTAL_PORCOES)
    assert teto["proteinas_g"] == 15.0


def test_o_maximo_e_estavel_na_ordem_do_cardapio():
    # Com corte de bandeja a escolha passa a importar; sem desempate, o mesmo
    # cardápio em outra ordem devolveria outro número.
    pratos = [_prato(1, "A", 100, 5.0, 1.0), _prato(2, "B", 100, 5.0, 1.0),
              _prato(3, "C", 100, 1.0, 9.0)]
    assert (pc.maximo_alcancavel(pratos, 2.0, 4.0)
            == pc.maximo_alcancavel(list(reversed(pratos)), 2.0, 4.0))


def test_a_nota_cita_o_maximo_que_o_payload_expoe(cardapio):
    # Número citado precisa ter sido exposto (é o que impede a R3 de acusar o
    # total certo) — e precisa ser o MESMO dos dois lados.
    meta = pc.Meta.de_argumentos(proteinas_g=30)
    composicao = pc.montar(cardapio, meta)
    exposto = composicao.para_tool()["maximo_no_cardapio"]["proteinas_g"]

    nota = pc.nota_para_o_modelo(composicao, meta)
    assert f"{exposto:.1f}".replace(".", ",") in nota


# --- 2. cada fracasso com a sua frase -----------------------------------------

def test_cardapio_nao_publicado_nao_vira_culpa_da_pessoa():
    # Segunda-feira, 10h, cardápio ainda não publicado. Antes, a nota pedia à
    # pessoa que flexibilizasse restrições que ela nem declarou e se oferecia
    # para mostrar um cardápio inexistente — o convite direto a citar prato de
    # memória que as outras duas tools proíbem em voz alta.
    meta = pc.Meta.de_argumentos(proteinas_g=22)
    nota = pc.nota_para_o_modelo(pc.montar([], meta, total_do_dia=0), meta)

    assert "não foi publicado" in nota
    assert "NÃO sugira nem cite nenhum prato" in nota
    assert "flexibilizar" not in nota


def test_excluido_por_conflito_nao_vira_convite_a_flexibilizar():
    # O motivo da exclusão costuma ser alergia. "Pergunte o que dá para
    # flexibilizar" pede à pessoa que abra mão dela.
    perigosos = [
        _prato(1, "Strogonoff", 300, 12.0, 20.0,
               conflita_com_perfil=["você informou alergia a leite — e este prato leva creme de leite"]),
        _prato(2, "Purê", 200, 4.0, 30.0,
               conflita_com_perfil=["você informou alergia a leite — e este prato leva leite"]),
    ]
    meta = pc.Meta.de_argumentos(proteinas_g=22)
    nota = pc.nota_para_o_modelo(pc.montar(perigosos, meta, total_do_dia=2), meta)

    assert "flexibilizar" not in nota
    assert "NÃO peça para ela abrir mão" in nota


def test_sem_informacao_do_dia_a_nota_nao_afirma_a_causa():
    # `montar` só enxerga os sobreviventes do filtro de quem chamou: lista vazia
    # tanto pode ser "não publicado" quanto "nada passou". Sem `total_do_dia`, a
    # nota não pode escolher — e escolher errado é pior do que a frase genérica.
    meta = pc.Meta.de_argumentos(proteinas_g=22)
    nota = pc.nota_para_o_modelo(pc.montar([], meta), meta)
    assert "não foi publicado" not in nota
    assert "flexibilizar" in nota
