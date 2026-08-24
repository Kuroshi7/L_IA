"""Os detectores textuais do eval, medidos contra paráfrases reais.

A variância de 20 pontos entre rodadas vinha daqui: asserções que procuravam
frases literais ("a resposta contém 'não reconheci'") reprovavam paráfrases
corretas. Cada detector agora é uma função testada contra muitas formas de dizer
a mesma coisa — quando o modelo inventar uma nova, o conserto é um caso a mais
aqui, não um ajuste no eval até ficar verde.
"""

import pytest

from tests.eval import assercoes as a

# --- declara_incerteza -------------------------------------------------------

DIZ_INCERTEZA = [
    "Não reconheci 'escondidinho da vovó' na minha base.",
    "Não encontrei esse alimento na tabela que eu consulto.",
    "O item não entrou na conta porque não achei o valor dele.",
    "Esse prato ficou fora do cálculo.",
    "Não consegui identificar 'xis coração', então ele não entrou no total.",
    "O valor é aproximado, viu?",
    "É uma estimativa, não um número exato.",
    "Não tenho o valor desse alimento aqui.",
    "Esse alimento não consta na minha base de dados.",
    "Não localizei esse item na tabela.",
    "Não faz parte da minha base, então deixei de fora.",
    "Esse é desconhecido pra mim.",
]
NAO_DIZ_INCERTEZA = [
    "Anotei tudo! No total foram 198 kcal. Mandou bem 👏",
    "Registrei 2 conchas de arroz e o escondidinho: 198 kcal.",
    "O cardápio de hoje tem Frango Grelhado e Arroz Integral.",
    "Você comeu 340 kcal, dentro da sua meta.",
]


@pytest.mark.parametrize("texto", DIZ_INCERTEZA)
def test_reconhece_declaracao_de_incerteza(texto):
    assert a.declara_incerteza(texto)


@pytest.mark.parametrize("texto", NAO_DIZ_INCERTEZA)
def test_nao_confunde_resposta_afirmativa_com_incerteza(texto):
    assert not a.declara_incerteza(texto)


# --- admite_ausencia ---------------------------------------------------------

ADMITE = [
    "Não encontrei pratos no cardápio de hoje.",
    "O cardápio de hoje ainda não foi carregado no sistema.",
    "Não temos cardápio cadastrado para hoje.",
    "Hoje está sem pratos por enquanto.",
    "Nenhum prato foi cadastrado ainda.",
    "O cardápio está vazio hoje.",
    "Não há nada registrado para hoje.",
    "O cardápio de hoje está indisponível.",
]
NAO_ADMITE = [
    "O cardápio de hoje tem Frango Grelhado, Arroz Integral e Salada Verde.",
    "Hoje temos três opções bem equilibradas.",
]


@pytest.mark.parametrize("texto", ADMITE)
def test_reconhece_admissao_de_ausencia(texto):
    assert a.admite_ausencia(texto)


@pytest.mark.parametrize("texto", NAO_ADMITE)
def test_nao_confunde_cardapio_cheio_com_ausencia(texto):
    assert not a.admite_ausencia(texto)


# --- pede_confirmacao / pede_correcao ---------------------------------------

@pytest.mark.parametrize("texto", [
    "Está certo assim?", "Confirma pra eu registrar?", "É isso mesmo?",
    "Sobrou algo no prato?", "Posso registrar?", "Confere pra mim?",
])
def test_reconhece_pedido_de_confirmacao(texto):
    assert a.pede_confirmacao(texto)


@pytest.mark.parametrize("texto", [
    "Me diz de outro jeito qual foi o alimento?",
    "Pode descrever o prato pra mim?",
    "Qual é o ingrediente principal?",
    "Tenta escrever de outra forma, tipo 'frango'.",
    "Me ajuda a entender o que você comeu?",
])
def test_reconhece_pedido_de_correcao(texto):
    assert a.pede_correcao(texto)


def test_afirmacao_pronta_nao_e_pedido():
    assert not a.pede_confirmacao("Pronto, registrei! Você ganhou 45 pontos.")
    assert not a.pede_correcao("Pronto, registrei! Você ganhou 45 pontos.")


# --- seção de recomendação ---------------------------------------------------

def test_secao_de_recomendacao_comeca_na_marca():
    texto = a.normalizar(
        "Cardapio de hoje: Frango Grelhado, Estrogonofe de carne. "
        "Baseado no seu perfil, recomendo o Frango Grelhado."
    )
    trecho = a.secao_de_recomendacao(texto)
    assert "recomendo" in trecho
    assert "estrogonofe" not in trecho, "listar no cardápio não é recomendar"


def test_sem_marca_nao_ha_secao_de_recomendacao():
    assert a.secao_de_recomendacao(a.normalizar("O cardapio de hoje tem tres pratos.")) == ""


# --- derivação a partir do dataset ------------------------------------------

DADOS = {"pratos": [
    {"nome": "Frango grelhado", "alergenos": [], "nao_indicado_para": []},
    {"nome": "Salada com amendoim", "alergenos": ["amendoim"], "nao_indicado_para": []},
    {"nome": "Estrogonofe de carne", "alergenos": ["lactose"], "nao_indicado_para": ["vegetariano"]},
]}


def test_deriva_pratos_perigosos_do_dataset():
    # Estrutural: a lista de proibidos sai do DADO, não de uma lista no caso —
    # assim o caso não desatualiza quando o cardápio de teste muda.
    assert a.pratos_com_alergeno(DADOS, ["amendoim"]) == ["Salada com amendoim"]
    assert a.pratos_que_violam(DADOS, ["vegetariano"]) == ["Estrogonofe de carne"]


def test_cita_usa_o_nucleo_do_nome():
    # O modelo abrevia "Frango grelhado com ervas finas" para "Frango grelhado".
    assert a.cita(a.normalizar("recomendo o frango grelhado"), "Frango grelhado com ervas")
    assert not a.cita(a.normalizar("recomendo o arroz"), "Frango grelhado")
