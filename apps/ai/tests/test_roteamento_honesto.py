"""O roteamento de restrição aberta não pode virar carta branca.

`filtrar_pratos` passou a devolver os pratos ao modelo quando o termo pedido não
está no vocabulário do cardápio do dia — o conserto do T2 de 27/08/2026, em que
"sem carne vermelha" zerava o cardápio e a Lia culpava o sistema na frente do
cliente. A revisão achou dois furos no conserto, e os dois têm o mesmo formato:
a nota do roteamento é a ÚLTIMA coisa do contexto antes da inferência, e ela
estava afirmando mais do que o código tinha verificado.

1. VOCABULÁRIO VAZIO não é o mesmo que "termo aberto". Quando nenhum prato do
   dia declara rótulo — o dia 1 de qualquer unidade nova, e o estado esperado
   "com 300 lojas" —, TODO termo cai em desconhecido, nada é filtrado e o
   cardápio inteiro volta com "decida por eles". A nota ainda saía com a lista
   literalmente vazia: "os rótulos que o cardápio declara ()".

2. A nota mandava recomendar sem nunca mencionar `conflita_com_perfil`, embora a
   lista roteada comprovadamente carregue pratos anotados. A nota irmã de
   `listar_pratos_do_dia` diz "Nunca os recomende"; a do roteamento empurrava
   para o lado contrário, e da posição de maior obediência.

O que este arquivo NÃO defende: que o roteamento pare. Parar era o defeito.
"""

import pytest

import app.agent.dominio.refeitorio.tools as t
from app.agent.motor.observacao import encerrar_turno, iniciar_turno

SEM_ROTULO_1 = {"id": 1, "nome": "Bife Acebolado", "categoria": "proteina",
                "calorias": 320, "proteinas_g": 28,
                "restricoes_atendidas": [], "nao_indicado_para": [],
                "alergenos": [], "ingredientes": ["carne bovina", "cebola", "óleo"]}
SEM_ROTULO_2 = {"id": 2, "nome": "Feijoada", "categoria": "proteina",
                "calorias": 400, "proteinas_g": 22,
                "restricoes_atendidas": [], "nao_indicado_para": [],
                "alergenos": [], "ingredientes": ["carne suina", "feijao", "linguica"]}
VEGGIE = {"id": 3, "nome": "Arroz integral com legumes", "categoria": "acompanhamento",
          "calorias": 180, "proteinas_g": 5,
          "restricoes_atendidas": ["vegetariano"], "nao_indicado_para": [],
          "alergenos": [], "ingredientes": ["arroz integral", "cenoura"]}
PEIXE = {"id": 4, "nome": "Filé de tilápia grelhado", "categoria": "proteina",
         "calorias": 210, "proteinas_g": 30,
         "restricoes_atendidas": ["vegetariano"], "nao_indicado_para": [],
         "alergenos": ["peixe"], "ingredientes": ["tilápia", "limão"]}


def _cardapio(monkeypatch, pratos, usuario_id=None):
    monkeypatch.setattr(t.go_api, "get_pratos", lambda u, d: [dict(p) for p in pratos])
    monkeypatch.setattr(
        t, "current_context",
        lambda: type("C", (), {"unidade_id": 1, "usuario_id": usuario_id})(),
    )


# --- 1. cadastro incompleto -----------------------------------------------------

@pytest.fixture
def sem_vocabulario(monkeypatch):
    """O cardápio existe e NENHUM prato foi classificado.

    É o default do schema (`TEXT[] NOT NULL DEFAULT '{}'`, 0001_init.sql) e o do
    admin, onde só `nome` é obrigatório.
    """
    _cardapio(monkeypatch, [SEM_ROTULO_1, SEM_ROTULO_2])


def test_nota_nao_lista_um_vocabulario_vazio(sem_vocabulario):
    # O texto ia para o modelo com um parêntese vazio, afirmando um material de
    # decisão inexistente. Ele repete o que lê.
    nota = t.filtrar_pratos.invoke({"restricoes": "vegetariano"})["nota_do_sistema"]
    assert "declara ()" not in nota
    assert "não classificou prato nenhum" in nota


def test_nota_nao_afirma_que_os_pratos_atendem_o_termo(sem_vocabulario):
    # A frase antiga era "os N pratos abaixo passaram pelos demais critérios…
    # DECIDA por eles — recomende". Para um vegetariano, com feijoada na lista, é
    # uma afirmação de segurança que ninguém verificou.
    nota = t.filtrar_pratos.invoke({"restricoes": "vegetariano"})["nota_do_sistema"]

    assert "NÃO significa que estes" in nota
    assert "NUNCA afirme que um prato atende 'vegetariano'" in nota
    # E o que sustenta a decisão continua na mão do modelo.
    assert "ingredientes" in nota


def test_o_conserto_do_t2_continua_de_pe(sem_vocabulario):
    # A guarda contra consertar o furo desfazendo a correção anterior: o tool não
    # pode voltar a dizer "nenhum prato atende" com voz de autoridade.
    out = t.filtrar_pratos.invoke({"restricoes": "sem carne vermelha"})
    assert not isinstance(out, str), out
    assert len(out["pratos"]) == 2
    assert out["vocabulario_de_restricoes"] == []


# --- 2. o prato anotado não pode ser oferecido em silêncio ----------------------

def test_nota_do_roteamento_avisa_do_conflito_com_o_perfil(monkeypatch):
    # A lista roteada CARREGA o prato anotado (é o contrato de
    # `test_conflito_com_perfil_sobrevive_ao_roteamento`). Sem esta frase, a
    # última mensagem do contexto pede uma escolha entre pratos sem dizer que um
    # deles é o que machuca — contradizendo a regra 6b, que está no topo do
    # system, a posição de MENOR obediência.
    _cardapio(monkeypatch, [VEGGIE, PEIXE], usuario_id=7)
    monkeypatch.setattr(t.go_api, "get_perfil",
                        lambda uid: {"nome": "Joao", "alergias": ["peixe"], "restricoes": []})

    token = iniciar_turno()
    try:
        out = t.filtrar_pratos.invoke({"restricoes": "sem carne vermelha"})
    finally:
        encerrar_turno(token)

    nota = out["nota_do_sistema"]
    assert "conflita_com_perfil" in nota
    assert "Nunca os recomende" in nota
    assert "Filé de tilápia grelhado" in nota


def test_sem_conflito_a_nota_nao_inventa_aviso(monkeypatch):
    # Aviso que aparece sempre vira ruído e o modelo aprende a ignorá-lo.
    _cardapio(monkeypatch, [VEGGIE, PEIXE])
    nota = t.filtrar_pratos.invoke({"restricoes": "sem carne vermelha"})["nota_do_sistema"]
    assert "ATENÇÃO" not in nota
