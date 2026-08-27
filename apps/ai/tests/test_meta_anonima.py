"""A meta dita na conversa vale para quem não tem cadastro.

Regressão da conversa de 27/08/2026, que é o caso de aceitação desta frente:

  T1 "o que temos no cardápio essa semana?"                            -> ok
  T2 "eu nao como carne vermelha, queria saber quais medidas coloco no
      meu prato, preciso todo dia de uns 22g de proteina animal e
      vegetal, uns 40g de carboidrato no minimo, oque me recomenda pra
      cada dia?"                                                       -> FALHOU
  T3 "isso como peixe e frango"                                        -> FALHOU de novo

A pessoa estava anônima e a única fonte de meta era `meu_perfil`, que exige
`usuario_id`. O pedido nunca foi respondido, e a Lia disse ao CLIENTE que "o
sistema está muito rigoroso" — vazou o mecanismo para o usuário final, 2x.

Os pratos da fixture são os SEIS medidos no cardápio da unidade 1 nesse dia, com
os macros que a API Go devolve. Dado real e não inventado de propósito: assim o
teste falha pelo mesmo motivo que a produção falhou, e fica registrado que 18,5 g
é o teto de proteína do dia sem carne vermelha com uma porção de cada.
"""

import pytest

from app.agent.dominio.refeitorio import porcionamento as pc

# Frase literal do T2. Não normalizada, sem acento — é como o usuário digitou.
FRASE_DO_USUARIO = (
    "eu nao como carne vermelha, queria saber quais medidas coloco no meu prato, "
    "preciso todo dia de uns 22g de proteina animal e vegetal, uns 40g de "
    "carboidrato no minimo, oque me recomenda pra cada dia?"
)


def _prato(id, nome, kcal, prot, carb, **extra):
    return {"id": id, "nome": nome, "calorias": kcal, "proteinas_g": prot,
            "carboidratos_g": carb, "gorduras_g": 0.0, **extra}


@pytest.fixture
def cardapio():
    return [
        _prato(1, "Arroz Branco", 130, 2.30, 32.30),
        _prato(2, "Feijão Preto", 110, 4.40, 12.20),
        _prato(3, "Bife Acebolado", 250, 28.00, 0.00, is_proteina_do_dia=True,
               ingredientes=["carne bovina", "cebola", "óleo"]),
        _prato(4, "Lentilha Refogada", 115, 7.10, 18.20),
        _prato(5, "Brócolis no Vapor", 35, 3.00, 5.50),
        _prato(6, "Salada de Beterraba", 45, 1.70, 9.50),
    ]


@pytest.fixture
def sem_carne_vermelha(cardapio):
    """O que sobra do cardápio depois do "eu nao como carne vermelha". Quem
    resolve restrição aberta é outra frente; aqui interessa o que o cálculo faz
    com o resultado dela."""
    return [p for p in cardapio if p["nome"] != "Bife Acebolado"]


# --- o defeito ----------------------------------------------------------------

def test_meta_dita_sem_usuario_chega_ao_calculo(sem_carne_vermelha):
    # A regressão: sem usuário, sem perfil, só a frase. Antes desta frente não
    # existia caminho nenhum da frase até um prato montado — `meu_perfil` era a
    # única fonte de meta e devolvia "usuário não identificado".
    meta = pc.combinar(pc.ler_meta(FRASE_DO_USUARIO), pc.meta_do_perfil(None))
    assert not meta.vazia()

    composicao = pc.montar(sem_carne_vermelha, meta)
    assert not composicao.vazia()
    nomes = {i["nome"] for i in composicao.itens}
    assert nomes <= {p["nome"] for p in sem_carne_vermelha}
    assert composicao.totais["proteinas_g"] > 0


def test_sem_meta_e_sem_perfil_nao_inventa_alvo(cardapio):
    # Sem alvo não se chuta alvo: prescrever quantidade é ato de nutricionista.
    vazia = pc.combinar(pc.ler_meta("o que tem hoje?"), pc.meta_do_perfil(None))
    assert vazia.vazia()

    composicao = pc.montar(cardapio, vazia)
    assert composicao.vazia()
    nota = pc.nota_para_o_modelo(composicao, vazia, todos=cardapio)
    assert "pergunte" in nota.lower()


# --- leitura da meta ----------------------------------------------------------

def test_ler_meta_extrai_a_frase_real_do_usuario():
    meta = pc.ler_meta(FRASE_DO_USUARIO)
    assert meta.proteinas_g.valor == 22.0
    assert meta.proteinas_g.piso is False      # "uns 22g" é aproximado
    assert meta.carboidratos_g.valor == 40.0
    assert meta.carboidratos_g.piso is True    # "no minimo" é piso
    assert meta.calorias is None               # ela não falou de caloria


@pytest.mark.parametrize("texto", [
    "comi 2 conchas de arroz",
    "tenho 40 anos",
    "tenho 22 pontos",
    "esse prato tem 228 kcal",
    "o feijão leva 12 g de carboidrato",
])
def test_ler_meta_ignora_numero_que_nao_e_meta(texto):
    # Risco número um do parser: número em português é ambíguo. Um falso positivo
    # aqui monta um prato inteiro mirando a idade da pessoa.
    assert pc.ler_meta(texto).vazia()


def test_ler_meta_aceita_a_meta_escrita_ao_contrario():
    meta = pc.ler_meta("minha meta: proteina 25g, carbo 60g")
    assert meta.proteinas_g.valor == 25.0
    assert meta.carboidratos_g.valor == 60.0


# --- perfil melhora, nunca habilita -------------------------------------------

def test_meta_dita_vence_a_do_perfil():
    dita = pc.ler_meta("preciso de 22g de proteina hoje")
    salva = pc.meta_do_perfil({"meta_calorica_kcal": 2000, "restricoes": []})
    meta = pc.combinar(dita, salva)

    assert meta.proteinas_g.valor == 22.0
    assert meta.proteinas_g.origem == "conversa"
    # A kcal do perfil só entrou porque ela não disse nenhuma.
    assert meta.calorias.origem == "perfil"


def test_perfil_so_preenche_o_que_nao_foi_dito():
    dita = pc.ler_meta("hoje quero no minimo 1500 kcal")
    salva = pc.meta_do_perfil({"meta_calorica_kcal": 2000})
    meta = pc.combinar(dita, salva)

    assert meta.calorias.valor == 1500.0
    assert meta.calorias.piso is True
    assert meta.calorias.origem == "conversa"


def test_fracao_da_refeicao_espelha_o_go():
    # Trava a constante duplicada: quem pontua o consumo é
    # apps/api/internal/domain/gamificacao.go:10 (FracaoRefeicaoAlmoco = 0.35).
    # Se os dois lados divergirem, recomendar e pontuar passam a discordar — a
    # mesma classe de bug do IA-20, e ninguém percebe sem este teste.
    assert pc.FRACAO_DA_REFEICAO == 0.35
    assert pc.meta_do_perfil({"meta_calorica_kcal": 2000}).calorias.valor == 700.0
    assert pc.meta_do_perfil({"meta_calorica_kcal": None}).vazia()


# --- o cálculo ----------------------------------------------------------------

def test_cardapio_de_hoje_sem_carne_vermelha_nao_alcanca_22g(sem_carne_vermelha):
    # O número que a Lia precisa dizer em vez de "o sistema está muito rigoroso".
    assert pc.maximo_alcancavel(sem_carne_vermelha, teto_porcoes=1.0)["proteinas_g"] == 18.50

    meta = pc.ler_meta(FRASE_DO_USUARIO)
    composicao = pc.montar(sem_carne_vermelha, meta, teto_porcoes=1.0)
    assert composicao.atingiu["proteinas_g"] is False
    assert composicao.atingiu["carboidratos_g"] is True
    assert composicao.para_tool()["maximo_no_cardapio"]["proteinas_g"] == 18.50


def test_repetir_porcao_alcanca_a_meta_que_uma_de_cada_nao_alcanca(sem_carne_vermelha):
    # Com o teto normal (2 porções por prato) a saída existe, e o guloso a acha.
    meta = pc.ler_meta(FRASE_DO_USUARIO)
    composicao = pc.montar(sem_carne_vermelha, meta)

    assert all(composicao.atingiu.values())
    assert max(i["porcoes"] for i in composicao.itens) > 1.0
    assert composicao.totais["carboidratos_g"] >= 40.0  # piso não admite folga


def test_totais_batem_com_a_soma_dos_itens(cardapio):
    # A conta é o produto desta frente. Se ela estiver errada, todo o resto é
    # cosmético — e é justamente a conta que o modelo errava fazendo de cabeça.
    composicao = pc.montar(cardapio, pc.ler_meta("preciso de 30g de proteina"))
    for macro in pc.MACROS:
        soma = round(sum(i[macro] for i in composicao.itens), 2)
        assert composicao.totais[macro] == pytest.approx(soma, abs=0.02)


def test_proteina_do_dia_limitada_a_uma_porcao(cardapio):
    # Regra 6 do refeitório, que vivia só no prompt: a proteína do dia é 1 porção
    # por pessoa. Com meta alta o guloso quereria duas — a fila não serve duas.
    composicao = pc.montar(cardapio, pc.Meta.de_argumentos(proteinas_g=60))
    bife = [i for i in composicao.itens if i["nome"] == "Bife Acebolado"]
    assert bife and bife[0]["porcoes"] <= 1.0


def test_prato_com_conflita_com_perfil_fica_fora_da_composicao(cardapio):
    # A composição é uma RECOMENDAÇÃO e cai sob a mesma barreira da R5. Em código,
    # não em prompt: recomendar o prato que machuca não pode depender de memória.
    perigoso = dict(cardapio[2], conflita_com_perfil=["você informou alergia a amendoim"])
    pratos = cardapio[:2] + [perigoso] + cardapio[3:]

    composicao = pc.montar(pratos, pc.Meta.de_argumentos(proteinas_g=60))
    assert "Bife Acebolado" not in {i["nome"] for i in composicao.itens}
    assert pc.maximo_alcancavel(pratos)["proteinas_g"] == 18.50


def test_nao_estoura_a_bandeja_quando_a_meta_e_inalcancavel(cardapio):
    composicao = pc.montar(cardapio, pc.Meta.de_argumentos(proteinas_g=500))
    assert sum(i["porcoes"] for i in composicao.itens) <= pc.TETO_TOTAL_PORCOES
    assert all(i["porcoes"] <= pc.TETO_POR_PRATO for i in composicao.itens)


def test_montar_e_deterministico(cardapio):
    # O desempate estável é o que sustenta todos os testes acima — e o que impede
    # a mesma pergunta devolver pratos diferentes a cada turno.
    meta = pc.ler_meta(FRASE_DO_USUARIO)
    primeira = pc.montar(cardapio, meta)
    segunda = pc.montar(list(reversed(cardapio)), meta)
    assert primeira.itens == segunda.itens
    assert primeira.totais == segunda.totais


# --- a nota que a Lia parafraseia ---------------------------------------------

_TRIPA_DO_SISTEMA = ("sistema", "filtro", "critério", "criterio", "rigoroso",
                     "tool", "consulta", "parâmetro", "parametro")


def _notas_possiveis(cardapio, sem_carne_vermelha):
    meta = pc.ler_meta(FRASE_DO_USUARIO)
    return [
        pc.nota_para_o_modelo(pc.montar(cardapio, meta), meta, todos=cardapio),
        pc.nota_para_o_modelo(
            pc.montar(sem_carne_vermelha, meta, teto_porcoes=1.0), meta, todos=cardapio),
        pc.nota_para_o_modelo(pc.montar([], meta), meta, todos=cardapio),
        pc.nota_para_o_modelo(pc.montar(cardapio, pc.Meta()), pc.Meta(), todos=cardapio),
    ]


def test_nota_nao_vaza_tripa_do_sistema(cardapio, sem_carne_vermelha):
    # Regressão direta do que o cliente leu duas vezes no baseline: "o sistema
    # está muito rigoroso", "parece que não está funcionando". A nota é material
    # para a Lia parafrasear — se o mecanismo estiver escrito nela, ele sai na
    # boca dela.
    for nota in _notas_possiveis(cardapio, sem_carne_vermelha):
        baixa = nota.lower()
        for palavra in _TRIPA_DO_SISTEMA:
            assert palavra not in baixa, f"vazou '{palavra}' em: {nota}"


def test_nota_diz_o_maximo_do_dia_quando_nao_atinge(sem_carne_vermelha, cardapio):
    meta = pc.ler_meta(FRASE_DO_USUARIO)
    nota = pc.nota_para_o_modelo(
        pc.montar(sem_carne_vermelha, meta, teto_porcoes=1.0), meta, todos=cardapio)
    # É o que transforma "parece que não está funcionando" em "hoje o cardápio
    # chega a 18,5 g de proteína".
    assert "18,5 g" in nota


def test_nota_declara_que_a_conta_e_desta_refeicao(cardapio):
    # A pessoa disse "todo dia" e o refeitório serve um almoço. Calar sobre a
    # premissa faria a Lia parecer estar montando o dia inteiro.
    meta = pc.ler_meta(FRASE_DO_USUARIO)
    nota = pc.nota_para_o_modelo(pc.montar(cardapio, meta), meta, todos=cardapio)
    assert "refeição" in nota and "dia inteiro" in nota


def test_nota_diz_a_origem_de_cada_alvo():
    # "como você me disse" só é dizível porque `Alvo` guarda a procedência — e é
    # essa frase que faz a resposta ao anônimo soar pessoal sem cadastro nenhum.
    meta = pc.combinar(pc.ler_meta("preciso de 22g de proteina"),
                       pc.meta_do_perfil({"meta_calorica_kcal": 2000}))
    nota = pc.nota_para_o_modelo(pc.montar([], meta), meta)
    assert "que você me disse" in nota and "do seu perfil" in nota


# --- o que quebrou quando tentei quebrar --------------------------------------
# Os quatro abaixo saíram da passada de "tentar provar que está errado" depois que
# a suíte passou de primeira. Todos falhavam na primeira versão do módulo.

def test_ler_meta_entende_numero_como_brasileiro_escreve():
    # "1.800" é mil e oitocentos, e a vírgula de "1,5" não é fim de oração —
    # a primeira versão lia 1,8 kcal e 5 g de proteína.
    assert pc.ler_meta("quero 1.800 kcal por dia").calorias.valor == 1800.0
    assert pc.ler_meta("quero 1,5 g de proteina").proteinas_g.valor == 1.5


def test_zero_nao_e_meta():
    # "0 g de gordura" é rótulo, não alvo. Aceitar zero fazia a nota anunciar
    # uma meta que a pessoa nunca pediu.
    assert pc.ler_meta("quero 0g de carboidrato").vazia()


def test_prato_sem_nome_fica_fora(cardapio):
    # Dado incompleto vindo da API não pode derrubar a recomendação — e prato sem
    # nome a Lia não teria como citar sem a R2 acusar nome inventado.
    pratos = cardapio + [{"id": 99, "calorias": 500, "proteinas_g": 40.0}]
    composicao = pc.montar(pratos, pc.Meta.de_argumentos(proteinas_g=30))
    assert all(i["nome"] for i in composicao.itens)


def test_nota_separa_nada_que_ela_coma_de_nada_que_ajude():
    # Duas causas, dois conselhos opostos: flexibilizar o que não come, ou rever
    # o número. A primeira versão dizia a primeira frase nos dois casos.
    meta = pc.Meta.de_argumentos(proteinas_g=10)
    sem_candidato = pc.nota_para_o_modelo(pc.montar([], meta), meta)
    sem_ajuda = pc.nota_para_o_modelo(
        pc.montar([_prato(1, "Chá", 0, 0.0, 0.0)], meta), meta)

    assert "flexibilizar" in sem_candidato
    assert "rever o número" in sem_ajuda
