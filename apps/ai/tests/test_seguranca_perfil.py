"""Segurança alimentar: o aviso viaja junto do prato, não depende da memória do modelo.

Medido na bateria `seguranca`: em 1 de 3 conversas a Lia recomendava a salada com
amendoim para quem tem alergia a amendoim no perfil. `filtrar_pratos` já devolvia
só o que era seguro — mas a regra contratual obriga mostrar o cardápio COMPLETO, e
o modelo às vezes escolhia a partir dessa lista crua.

Esconder o prato não é opção. O conserto é anotar o conflito no próprio item e ter
uma regra estrutural como última barreira.
"""

import app.agent.dominio.refeitorio.tools as t
from app.agent.dominio.refeitorio.filters import conflitos_com_perfil
from app.agent.dominio.refeitorio.validators import verificar_resposta
from app.agent.motor.observacao import ObservacoesDoTurno, encerrar_turno, iniciar_turno

AMENDOIM = {"id": 4, "nome": "Salada de grao-de-bico com amendoim", "categoria": "salada",
            "calorias": 150, "alergenos": ["amendoim"],
            "restricoes_atendidas": ["vegetariano", "vegano"], "nao_indicado_para": [],
            "ingredientes": ["grao-de-bico", "amendoim"]}
CARNE = {"id": 2, "nome": "Estrogonofe de carne", "categoria": "proteina", "calorias": 320,
         "alergenos": ["lactose"], "restricoes_atendidas": [],
         "nao_indicado_para": ["vegetariano"], "ingredientes": ["carne"]}
FRANGO = {"id": 1, "nome": "Frango grelhado", "categoria": "proteina", "calorias": 180,
          "alergenos": [], "restricoes_atendidas": ["sem gluten"], "nao_indicado_para": [],
          "ingredientes": ["frango"]}

PERFIL_ALERGICO = {"nome": "Larissa", "alergias": ["amendoim"], "restricoes": ["vegetariano"]}
# Só a alergia: isola o eixo, para provar que prato seguro NÃO recebe anotação.
PERFIL_SO_ALERGIA = {"nome": "Joao", "alergias": ["amendoim"], "restricoes": []}


# --- detecção de conflito ----------------------------------------------------

def test_detecta_alergia():
    # O texto é material de fala, não rótulo de sistema: precisa dizer QUEM
    # informou e QUAL ingrediente, para a Lia parafrasear sem prescrever.
    motivos = conflitos_com_perfil(AMENDOIM, PERFIL_ALERGICO)
    assert motivos
    assert any("você informou" in m and "alergia" in m for m in motivos)
    assert any("leva amendoim" in m for m in motivos)


def test_detecta_restricao():
    motivos = conflitos_com_perfil(CARNE, PERFIL_ALERGICO)
    assert any("você informou a restrição 'vegetariano'" in m for m in motivos)
    # O ingrediente entra para a Lia poder dizer "porque leva carne".
    assert any("leva carne" in m for m in motivos)


def test_prato_seguro_nao_gera_ruido():
    assert conflitos_com_perfil(FRANGO, {"alergias": [], "restricoes": []}) == []


def test_sem_perfil_nao_ha_conflito():
    assert conflitos_com_perfil(AMENDOIM, None) == []


# --- a anotação chega na listagem -------------------------------------------

def _turno(monkeypatch, perfil):
    monkeypatch.setattr(t.go_api, "get_pratos", lambda u, d: [dict(FRANGO), dict(AMENDOIM), dict(CARNE)])
    monkeypatch.setattr(t.go_api, "get_perfil", lambda uid: perfil)
    monkeypatch.setattr(t, "current_context", lambda: type("C", (), {"unidade_id": 1, "usuario_id": 7})())
    return iniciar_turno()


def test_listagem_marca_o_prato_perigoso(monkeypatch):
    token = _turno(monkeypatch, PERFIL_SO_ALERGIA)
    try:
        out = t.listar_pratos_do_dia.invoke({"dia": "hoje"})
    finally:
        encerrar_turno(token)

    # A regra contratual obriga listar TUDO — inclusive o perigoso.
    assert out["total"] == 3
    por_nome = {p["nome"]: p for p in out["pratos"]}
    assert "conflita_com_perfil" in por_nome["Salada de grao-de-bico com amendoim"]
    assert "conflita_com_perfil" not in por_nome["Frango grelhado"]


def test_anotacao_cobre_os_dois_eixos(monkeypatch):
    # Perfil vegetariano E alérgico: o estrogonofe cai pela restrição, a salada
    # pela alergia. Frango grelhado também é carne — cai pela restrição.
    token = _turno(monkeypatch, PERFIL_ALERGICO)
    try:
        out = t.listar_pratos_do_dia.invoke({"dia": "hoje"})
    finally:
        encerrar_turno(token)

    por_nome = {p["nome"]: p.get("conflita_com_perfil", []) for p in out["pratos"]}
    assert any("alergia" in m for m in por_nome["Salada de grao-de-bico com amendoim"])
    assert any("restrição" in m for m in por_nome["Estrogonofe de carne"])
    # E a instrução vai junto, no fim do contexto.
    assert "nunca os recomende" in out["nota_do_sistema"].lower()


def test_sem_usuario_nao_ha_anotacao(monkeypatch):
    monkeypatch.setattr(t.go_api, "get_pratos", lambda u, d: [dict(AMENDOIM)])
    monkeypatch.setattr(t, "current_context", lambda: type("C", (), {"unidade_id": 1, "usuario_id": None})())
    token = iniciar_turno()
    try:
        out = t.listar_pratos_do_dia.invoke({"dia": "hoje"})
    finally:
        encerrar_turno(token)
    assert "conflita_com_perfil" not in out["pratos"][0]


def test_perfil_indisponivel_nao_derruba_o_cardapio(monkeypatch):
    def explode(uid):
        raise RuntimeError("API fora")

    monkeypatch.setattr(t.go_api, "get_pratos", lambda u, d: [dict(FRANGO)])
    monkeypatch.setattr(t.go_api, "get_perfil", explode)
    monkeypatch.setattr(t, "current_context", lambda: type("C", (), {"unidade_id": 1, "usuario_id": 7})())
    token = iniciar_turno()
    try:
        assert t.listar_pratos_do_dia.invoke({"dia": "hoje"})["total"] == 1
    finally:
        encerrar_turno(token)


# --- R5: última barreira -----------------------------------------------------

def _obs_com_conflito():
    obs = ObservacoesDoTurno()
    obs.registrar(("listar_pratos_do_dia", "{}"), {
        "total": 2,
        "pratos": [
            {"id": 1, "nome": "Frango grelhado", "categoria": "proteina"},
            {"id": 4, "nome": "Salada de grao-de-bico com amendoim", "categoria": "salada",
             "conflita_com_perfil": ["ALERGIA: contém amendoim"]},
        ],
    })
    return obs


def _ids(resposta):
    return verificar_resposta(resposta, tools_chamadas=["listar_pratos_do_dia"],
                              observacoes=_obs_com_conflito()).ids


def test_r5_acusa_recomendacao_de_prato_conflitante():
    resposta = ("Cardápio de hoje: **Frango grelhado**, **Salada de grao-de-bico com amendoim**. "
                "Recomendo a **Salada de grao-de-bico com amendoim**, é bem leve.")
    assert "R5-prato-conflita-com-perfil" in _ids(resposta)


def test_r5_nao_acusa_o_prato_apenas_listado():
    # A regra contratual OBRIGA listar o prato perigoso. Listar não é recomendar —
    # acusar aqui tornaria impossível cumprir as duas regras ao mesmo tempo.
    resposta = ("Cardápio de hoje: **Frango grelhado**, **Salada de grao-de-bico com amendoim**. "
                "Recomendo o **Frango grelhado**, que não tem amendoim.")
    assert "R5-prato-conflita-com-perfil" not in _ids(resposta)


def test_r5_silencia_sem_conflito_conhecido():
    obs = ObservacoesDoTurno()
    obs.registrar(("t", "{}"), [{"id": 1, "nome": "Frango grelhado"}])
    v = verificar_resposta("Recomendo o **Frango grelhado**.",
                           tools_chamadas=["listar_pratos_do_dia"], observacoes=obs)
    assert "R5-prato-conflita-com-perfil" not in v.ids


# --- R5 bloqueia de verdade --------------------------------------------------

def test_r5_e_bloqueante_por_padrao():
    from app import config

    # É a única regra que nasce bloqueante: 100% estrutural, e o erro dela pode
    # mandar alguém para o hospital. Nas outras, bloquear troca uma resposta
    # provavelmente boa por uma mensagem de erro.
    assert "R5-prato-conflita-com-perfil" in config.VALIDACAO_BLOQUEANTE
    assert len(config.VALIDACAO_BLOQUEANTE) == 1, "bloquear demais degrada a experiência"


def test_veredicto_marca_bloqueio():
    resposta = ("Cardápio: **Frango grelhado**, **Salada de grao-de-bico com amendoim**. "
                "Recomendo a **Salada de grao-de-bico com amendoim**.")
    v = verificar_resposta(resposta, tools_chamadas=["listar_pratos_do_dia"],
                           observacoes=_obs_com_conflito())
    assert v.bloqueia and not v.ok


def test_resposta_segura_nao_bloqueia():
    v = verificar_resposta("Recomendo o **Frango grelhado**.",
                           tools_chamadas=["listar_pratos_do_dia"], observacoes=_obs_com_conflito())
    assert not v.bloqueia


def test_r5_pega_o_nome_abreviado_pelo_modelo():
    # Medido: o modelo escreve "Salada de grão-de-bico" sem o "com amendoim",
    # e a R5 exigindo o nome exato passava por cima do caso perigoso.
    resposta = ("Cardápio: **Frango grelhado**, **Salada de grao-de-bico com amendoim**. "
                "Recomendo a **Salada de grao-de-bico**, é leve e vegetariana.")
    assert "R5-prato-conflita-com-perfil" in _ids(resposta)


def test_r5_nao_confunde_pratos_que_comecam_igual():
    # O corte de qualificador nunca chega a uma palavra só: "salada" sozinha
    # casaria com "Salada verde", que é segura.
    obs = ObservacoesDoTurno()
    obs.registrar(("t", "{}"), {"pratos": [
        {"id": 4, "nome": "Salada de grao-de-bico com amendoim",
         "conflita_com_perfil": ["ALERGIA: contém amendoim"]},
        {"id": 5, "nome": "Salada verde", "categoria": "salada"},
    ]})
    v = verificar_resposta("Recomendo a **Salada verde**, bem fresquinha.",
                           tools_chamadas=["listar_pratos_do_dia"], observacoes=obs)
    assert "R5-prato-conflita-com-perfil" not in v.ids


def test_r5_nao_bloqueia_o_alerta_de_seguranca():
    # "posso comer X?" → a resposta CORRETA é "você não pode comer X". A marca
    # "pode comer" fazia a R5 tratar o alerta como recomendação e bloquear
    # justamente o aviso que ela existe para garantir.
    resposta = ("Olhei aqui: a **Salada de grao-de-bico com amendoim** tem amendoim, e você "
                "é alérgica — então não pode comer esse. Prefira o **Frango grelhado**.")
    assert "R5-prato-conflita-com-perfil" not in _ids(resposta)


def test_reminder_de_saude_traz_o_fecho_pronto():
    from app.agent.dominio.refeitorio.prompts import REMINDER_CONDICAO_DE_SAUDE

    # Modelo segue exemplar melhor que instrução: medimos 0/3 com a instrução
    # solta ("termine orientando a procurar profissional").
    assert "médico ou nutricionista" in REMINDER_CONDICAO_DE_SAUDE
    assert "ENCERRE" in REMINDER_CONDICAO_DE_SAUDE


# --- encaminhamento a profissional, garantido em código ----------------------

def test_encaminhamento_e_acrescentado_quando_falta():
    from app.agent.dominio.refeitorio.perfil import pos_processar
    from app.agent.motor.reminders import Gatilhos

    saida = pos_processar("Prefira pratos com proteína e evite frituras.", Gatilhos(),
                          "tenho diabetes, o que como?")
    assert "nutricionista" in saida


def test_nao_duplica_quando_a_lia_ja_encaminhou():
    from app.agent.dominio.refeitorio.perfil import pos_processar
    from app.agent.motor.reminders import Gatilhos

    original = "Prefira proteína. Vale confirmar com seu nutricionista, viu?"
    assert pos_processar(original, Gatilhos(), "sou diabético") == original


def test_conversa_comum_nao_ganha_rodape():
    from app.agent.dominio.refeitorio.perfil import pos_processar
    from app.agent.motor.reminders import Gatilhos

    assert pos_processar("O cardápio de hoje tem frango.", Gatilhos(), "o que tem hoje?") \
        == "O cardápio de hoje tem frango."


# --- a voz do aviso: reportar, não prescrever --------------------------------

PROIBITIVAS = ("voce nao pode", "você não pode", "proibido", "nao e permitido",
               "não é permitido", "evite comer", "nao coma", "não coma")


def test_motivo_nao_usa_linguagem_de_proibicao():
    """Recomendação nutricional individualizada é ato privativo de nutricionista.

    A diferença entre "você não pode comer isso" e "com base no que você me
    contou, esse prato não é indicado, porque leva amendoim" não é de educação:
    é de AUTORIDADE. A primeira determina, a segunda reporta — e só a segunda a
    Lia tem competência para dizer.
    """
    for prato in (AMENDOIM, CARNE):
        for motivo in conflitos_com_perfil(prato, PERFIL_ALERGICO):
            baixo = motivo.lower()
            for termo in PROIBITIVAS:
                assert termo not in baixo, f"linguagem de proibição em: {motivo!r}"


def test_motivo_atribui_a_origem_da_informacao():
    # Quem declarou foi a pessoa. Sem isso, a Lia soa como se tivesse
    # diagnosticado a alergia.
    for prato in (AMENDOIM, CARNE):
        for motivo in conflitos_com_perfil(prato, PERFIL_ALERGICO):
            assert "você informou" in motivo, motivo


def test_motivo_traz_o_fato_do_prato():
    # "porque leva X" é o que torna o aviso verificável em vez de opinião.
    assert "leva" in " ".join(conflitos_com_perfil(AMENDOIM, PERFIL_ALERGICO))
    assert "leva" in " ".join(conflitos_com_perfil(CARNE, PERFIL_ALERGICO))
