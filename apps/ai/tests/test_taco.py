"""Casamento com a referência TACO: precisão antes de cobertura.

Uma auditoria que compara alimentos errados é pior que auditoria nenhuma — ela
gera alarme falso, a nutricionista perde a confiança no relatório e para de
olhar. Estes testes travam as decisões que garantem a precisão.
"""

import pytest

from app.nutrition import taco


def test_referencia_carrega():
    refs = taco.carregar()
    assert len(refs) > 500, "a referência TACO encolheu"
    assert all(r.kcal is not None for r in refs)


@pytest.mark.parametrize("nome, esperado", [
    ("Arroz Integral Cozido", "Arroz, integral, cozido"),
    ("Feijao Carioca Cozido", "Feijão, carioca, cozido"),
    ("Batata-Inglesa Frita", "Batata, inglesa, frita"),
])
def test_casa_pontuacao_e_acento_diferentes(nome, esperado):
    ref, score = taco.procurar(nome)
    assert ref is not None and ref.nome == esperado
    assert score >= 0.65


def test_casa_quando_a_taco_acrescenta_a_variedade():
    # "Abobrinha, italiana, cozida" é o mesmo alimento com a variedade explícita.
    # É por isso que o piso é 0.65 e não 0.75: dobra a cobertura sem perder par.
    ref, _ = taco.procurar("Abobrinha Cozida")
    assert ref is not None and "Abobrinha" in ref.nome and "cozida" in ref.nome


def test_nao_casa_alimentos_diferentes_com_prefixo_igual():
    # "Arroz Doce" e "Arroz Cozido" compartilham a primeira palavra e são
    # nutricionalmente muito diferentes. Casamento por substring erraria aqui.
    ref, _ = taco.procurar("Arroz-Doce")
    assert ref is None or "doce" in taco.normalizar(ref.nome)


# --- incompatibilidade de preparo -------------------------------------------

@pytest.mark.parametrize("a, b, compativel", [
    ("Batata Cozida", "Batata, inglesa, cozida", True),
    ("Batata Cozida", "Batata, inglesa, frita", False),
    ("Repolho Cru", "Repolho, branco, cru", True),
    # Nome sem preparo declarado é prato SERVIDO, nunca cru.
    ("Croquete de Carne", "Croquete, de carne, cru", False),
    ("Croquete de Carne", "Croquete, de carne, frito", True),
])
def test_preparos_compativeis(a, b, compativel):
    assert taco.preparos_compativeis(a, b) is compativel


def test_croquete_casa_com_o_frito_e_nao_com_o_cru():
    # Regressão do achado real: sem a assimetria do "cru", a auditoria
    # comparava o croquete servido com o croquete cru e acusava divergência
    # que era só a água/óleo do preparo.
    ref, _ = taco.procurar("Croquete de Carne")
    assert ref is not None and "frito" in taco.normalizar(ref.nome)


# --- o caso que motivou tudo -------------------------------------------------

def test_arroz_integral_da_base_diverge_da_taco():
    """O valor do livro-fonte (257 kcal/100 g) é ~2x o da TACO.

    Não é erro de extração: a página 7 do PDF diz 257,00 mesmo, com fonte `*`
    (cálculo dos autores). É a fonte primária que não sobrevive à conferência —
    e o produto passou a tratar esse número como aproximação em vez de fato.
    """
    ref, _ = taco.procurar("Arroz Integral Cozido")
    assert ref is not None
    assert 115 < ref.kcal < 135, f"referência TACO mudou: {ref.kcal}"
    assert abs(257.0 - ref.kcal) / ref.kcal > 0.40
