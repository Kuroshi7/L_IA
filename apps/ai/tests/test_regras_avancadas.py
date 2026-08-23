"""Regras R2/R3/R4 e compressão de repetição."""


import pytest
import app.agent.dominio.refeitorio.tools as t
from app.agent.dominio.refeitorio.perfil import PERFIL
from app.agent.dominio.refeitorio.validators import verificar_resposta
from app.agent.motor.observacao import (
    TEXTO_JA_CONSULTADO,
    ObservacoesDoTurno,
    encerrar_turno,
    iniciar_turno,
    observacoes_do_turno,
)

CARDAPIO = [
    {"id": 1, "nome": "Frango grelhado", "categoria": "proteina", "calorias": 180, "proteinas_g": 31},
    {"id": 2, "nome": "Arroz integral", "categoria": "acompanhamento", "calorias": 110, "proteinas_g": 2.5},
]
TOOLS_CARDAPIO = ["filtrar_pratos"]


def _obs(*retornos, avisos=()):
    o = ObservacoesDoTurno()
    for i, r in enumerate(retornos):
        o.registrar((f"tool{i}", "{}"), r)
    o.avisos.extend(avisos)
    return o


def _ids(resposta, obs, tools=TOOLS_CARDAPIO):
    return verificar_resposta(resposta, tools_chamadas=tools, observacoes=obs).ids


# --- R2: prato citado precisa ter vindo de alguma tool -----------------------

def test_r2_pega_prato_inventado():
    ids = _ids("Recomendo **Lasanha de forno** hoje.", _obs(CARDAPIO))
    assert "R2-prato-fora-do-cardapio" in ids


def test_r2_aceita_prato_do_cardapio():
    ids = _ids("Recomendo **Frango grelhado**.", _obs(CARDAPIO))
    assert "R2-prato-fora-do-cardapio" not in ids


def test_r2_aceita_nome_abreviado_pelo_modelo():
    # O modelo encurta nome com frequência; exigir string exata geraria
    # falso positivo constante e a regra viraria ruído ignorado.
    obs = _obs([{"id": 9, "nome": "Frango grelhado com ervas finas", "calorias": 200}])
    assert "R2-prato-fora-do-cardapio" not in _ids("Sugiro **Frango grelhado**.", obs)


def test_r2_ignora_rotulos_em_negrito():
    resposta = "Recomendo **Arroz integral**\n- **Nutrição**: 110 kcal\n- **Porção sugerida**: 1 concha"
    assert "R2-prato-fora-do-cardapio" not in _ids(resposta, _obs(CARDAPIO))


def test_r2_silencia_quando_nada_foi_lido():
    # Sem nada lido no turno, quem acusa é a R1 — a R2 não tem base de comparação.
    assert "R2-prato-fora-do-cardapio" not in _ids("Recomendo **Qualquer coisa**.", _obs(), tools=[])


# --- R3: número citado precisa ter sido exposto ------------------------------

def test_r3_pega_numero_inventado():
    assert "R3-numero-nao-exposto" in _ids("O **Frango grelhado** tem 999 kcal.", _obs(CARDAPIO))


def test_r3_aceita_numero_da_tool():
    assert "R3-numero-nao-exposto" not in _ids("O **Frango grelhado** tem 180 kcal.", _obs(CARDAPIO))


def test_r3_tolera_arredondamento():
    obs = _obs([{"id": 1, "nome": "Arroz", "calorias": 182.4}])
    assert "R3-numero-nao-exposto" not in _ids("São 182 kcal.", obs)


def test_r3_pega_kcal_que_a_listagem_nao_mostrou():
    # `listar_pratos_do_dia` devolve só {id, nome, categoria}: a kcal nunca foi
    # exposta. É o caso que a separação itens_conhecidos/valores_expostos existe
    # para cobrir — sem ela, o número passaria por "o prato é conhecido".
    obs = _obs([{"id": 1, "nome": "Frango grelhado", "categoria": "proteina"}])
    assert "R3-numero-nao-exposto" in _ids("O **Frango grelhado** tem 180 kcal.", obs)


# --- R4: incerteza precisa ser declarada -------------------------------------

def test_r4_pega_total_incompleto_apresentado_como_final():
    obs = _obs(CARDAPIO, avisos=["NÃO reconheci na base: xyzabc."])
    assert "R4-incompleto-sem-ressalva" in _ids("No total foram 180 kcal. Ficou ótimo!", obs)


def test_r4_aceita_resposta_que_ressalva():
    obs = _obs(CARDAPIO, avisos=["NÃO reconheci na base: xyzabc."])
    resposta = "Não reconheci 'xyzabc', então ele não entrou na conta. O resto deu 180 kcal."
    assert "R4-incompleto-sem-ressalva" not in _ids(resposta, obs)


def test_r4_silencia_sem_aviso():
    assert "R4-incompleto-sem-ressalva" not in _ids("Foram 180 kcal.", _obs(CARDAPIO))


# --- veredicto ----------------------------------------------------------------

def test_resposta_limpa_passa_em_tudo():
    v = verificar_resposta("Recomendo **Frango grelhado** — 180 kcal.",
                           tools_chamadas=TOOLS_CARDAPIO, observacoes=_obs(CARDAPIO))
    assert v and v.ok and v.violacoes == ()


def test_veredicto_nao_bloqueia_por_padrao():
    # Default log-only: nenhuma regra tem taxa de falso positivo medida ainda.
    v = verificar_resposta("Recomendo **Lasanha inventada** com 999 kcal.",
                           tools_chamadas=TOOLS_CARDAPIO, observacoes=_obs(CARDAPIO))
    assert not v.ok
    assert not v.bloqueia


def test_todas_as_regras_do_perfil_tem_id_unico():
    ids = [rid for rid, _ in PERFIL.regras]
    assert len(ids) == len(set(ids)) == 4


# --- compressão ---------------------------------------------------------------

def test_repeticao_exata_devolve_marcador(monkeypatch):
    chamadas = []
    monkeypatch.setattr(t.go_api, "get_pratos", lambda u, d: chamadas.append(1) or list(CARDAPIO))
    monkeypatch.setattr(t, "current_context", lambda: type("C", (), {"unidade_id": 1, "usuario_id": None})())

    token = iniciar_turno()
    try:
        primeira = t.listar_pratos_do_dia.invoke({"dia": "hoje"})
        segunda = t.listar_pratos_do_dia.invoke({"dia": "hoje"})
    finally:
        encerrar_turno(token)

    assert isinstance(primeira, list) and len(primeira) == 2
    assert segunda == TEXTO_JA_CONSULTADO


def test_argumentos_diferentes_nao_sao_comprimidos(monkeypatch):
    monkeypatch.setattr(t.go_api, "get_pratos", lambda u, d: list(CARDAPIO))
    monkeypatch.setattr(t, "current_context", lambda: type("C", (), {"unidade_id": 1, "usuario_id": None})())

    token = iniciar_turno()
    try:
        a = t.filtrar_pratos.invoke({"restricoes": "vegetariano", "dia": "hoje"})
        b = t.filtrar_pratos.invoke({"restricoes": "vegano", "dia": "hoje"})
    finally:
        encerrar_turno(token)

    assert a != TEXTO_JA_CONSULTADO and b != TEXTO_JA_CONSULTADO


def test_nota_do_sistema_vira_aviso_do_turno():
    obs = ObservacoesDoTurno()
    obs.registrar(("registrar_consumo", "{}"), {"consumo_id": 1, "nota_do_sistema": "NÃO reconheci: xyz"})
    assert obs.avisos == ["NÃO reconheci: xyz"]


def test_r3_nao_acusa_quando_o_turno_so_trouxe_prosa():
    # `buscar_informacao` (RAG) devolve texto corrido, que pode conter números
    # legítimos impossíveis de conferir. Acusar aqui geraria falso positivo e a
    # regra viraria ruído que ninguém lê.
    obs = _obs("Uma concha média de arroz tem cerca de 110 kcal segundo o guia.")
    assert "R3-numero-nao-exposto" not in _ids("O guia diz 110 kcal por concha.", obs, tools=["buscar_informacao"])


# --- IA-11: falso positivos MEDIDOS em turnos reais viram regressão ----------
# Cada string abaixo saiu de um log `VALIDACAO | regra=...` de uma conversa real
# com Haiku. São todos negritos que o modelo usa para título, rótulo, data ou
# frase — nenhum é nome de prato.

FALSO_POSITIVOS_R2 = [
    "**Recomendação para você:** o frango está ótimo hoje.",
    "**Nutrição da combinação:** 235 kcal no total.",
    "Você comeu **235 kcal** no almoço.",
    "**Segunda-feira (17/08)** tem frango.",
    "**Terça a domingo:** o cardápio ainda não foi divulgado.",
    "**Você quer que eu recomende como montar o prato de amanhã?**",
    "**Minha sugestão:** monte com arroz.",
    "**Resultado:** o frango lidera em proteína.",
    "**Porção sugerida:** 2 conchas.",
    "**Segunda opção:** arroz com salada.",
    "O frango tem **31g de proteína**.",
]


@pytest.mark.parametrize("resposta", FALSO_POSITIVOS_R2)
def test_r2_nao_acusa_negrito_que_nao_e_nome_de_prato(resposta):
    # Antes do conserto, todos estes disparavam R2 e afogavam o sinal real.
    assert "R2-prato-fora-do-cardapio" not in _ids(resposta, _obs(CARDAPIO))


def test_r2_continua_pegando_prato_inventado_de_verdade():
    # A precisão não pode ter custado a detecção — este é o caso que importa.
    assert "R2-prato-fora-do-cardapio" in _ids("Recomendo a **Feijoada Completa**.", _obs(CARDAPIO))
    assert "R2-prato-fora-do-cardapio" in _ids("Sugiro **Lasanha de Berinjela** hoje.", _obs(CARDAPIO))


def test_r3_aceita_soma_dos_pratos_recomendados():
    # 110 + 95 + 30 = 235: aritmética legítima do prato montado, não invenção.
    obs = _obs([
        {"id": 1, "nome": "Arroz Integral", "calorias": 110},
        {"id": 2, "nome": "Feijão Carioca", "calorias": 95},
        {"id": 3, "nome": "Salada Verde", "calorias": 30},
    ])
    assert "R3-numero-nao-exposto" not in _ids("No total dá 235 kcal.", obs)
    assert "R3-numero-nao-exposto" not in _ids("Arroz e feijão somam 205 kcal.", obs)


def test_r3_continua_pegando_numero_inventado():
    obs = _obs([
        {"id": 1, "nome": "Arroz Integral", "calorias": 110},
        {"id": 2, "nome": "Feijão Carioca", "calorias": 95},
    ])
    assert "R3-numero-nao-exposto" in _ids("Esse prato tem 780 kcal.", obs)
