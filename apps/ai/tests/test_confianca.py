"""Confiança: o produto declara incerteza em vez de fingir precisão."""

import app.agent.dominio.refeitorio.tools as t
from app.agent.dominio.refeitorio.prompts import SYSTEM_AGENT
from app.agent.dominio.refeitorio.tools import _qualidade, registrar_consumo

ITENS = [{"alimento": "arroz", "medida": "concha", "quantidade": 2}]


def _totais(itens, ignorados=None, completo=True):
    return {"itens": itens, "kcal": 220.0, "itens_ignorados": ignorados or [], "completo": completo}


def _item(entrada, resolvido=None, confianca="alta", obs=""):
    return {
        "entrada": {"alimento": entrada, "medida": "concha", "quantidade": 1},
        "alimento_resolvido": resolvido or "",
        "confianca": confianca,
        "obs": obs,
        "kcal": 110.0 if resolvido else 0.0,
    }


# --- classificação ------------------------------------------------------------

def test_item_nao_resolvido_conta_como_ignorado():
    q = _qualidade(_totais([_item("xyzabc")], ignorados=["xyzabc"], completo=False))
    assert q.ignorados == ["xyzabc"]
    assert q.ha_incerteza and q.tudo_ignorado


def test_shape_antigo_sem_itens_ignorados_ainda_e_detectado():
    # Compatibilidade: se a API Go ainda não expõe `itens_ignorados`, o sintoma
    # continua legível item a item. Sem isso, a IA depende da ordem do deploy.
    q = _qualidade({"itens": [_item("xyzabc")]})
    assert q.ignorados == ["xyzabc"]


def test_confianca_media_e_imprecisao_nao_ignorada():
    q = _qualidade(_totais([_item("arroz", "Arroz cozido", confianca="media")]))
    assert not q.ignorados
    assert q.imprecisos and q.ha_incerteza and not q.tudo_ignorado


def test_tudo_alto_nao_gera_ruido():
    q = _qualidade(_totais([_item("arroz", "Arroz cozido")]))
    assert not q.ha_incerteza
    assert t._nota_de_incerteza(q) == ""


def test_obs_preenchida_marca_imprecisao_mesmo_com_confianca_alta():
    q = _qualidade(_totais([_item("arroz", "Arroz cozido", obs="usando 100g como referência")]))
    assert q.imprecisos


# --- prévia -------------------------------------------------------------------

def test_previa_avisa_o_que_ficou_de_fora(monkeypatch):
    monkeypatch.setattr(t.go_api, "calcular_consumo",
                        lambda itens: _totais([_item("xyzabc")], ignorados=["xyzabc"], completo=False))
    monkeypatch.setattr(t, "current_context", lambda: type("C", (), {"unidade_id": 1, "usuario_id": 7})())

    out = registrar_consumo.invoke({"itens": ITENS, "confirmado": False})
    assert "nota_do_sistema" in out
    assert "xyzabc" in out["nota_do_sistema"]
    assert "NÃO entraram no total" in out["nota_do_sistema"]


def test_previa_limpa_nao_ganha_nota(monkeypatch):
    monkeypatch.setattr(t.go_api, "calcular_consumo",
                        lambda itens: _totais([_item("arroz", "Arroz cozido")]))
    monkeypatch.setattr(t, "current_context", lambda: type("C", (), {"unidade_id": 1, "usuario_id": 7})())

    out = registrar_consumo.invoke({"itens": ITENS, "confirmado": False})
    assert "nota_do_sistema" not in out


# --- portão da escrita --------------------------------------------------------

def test_confirmado_com_tudo_ignorado_nao_grava(monkeypatch):
    # Gravar 0 kcal produz desvio máximo na pontuação e índice de resto sem
    # sentido — dado corrompido, e sem desfazer.
    gravou = []
    monkeypatch.setattr(t.go_api, "calcular_consumo",
                        lambda itens: _totais([_item("xyzabc")], ignorados=["xyzabc"], completo=False))
    monkeypatch.setattr(t.go_api, "registrar_consumo",
                        lambda *a, **k: gravou.append(1) or {})
    monkeypatch.setattr(t, "current_context", lambda: type("C", (), {"unidade_id": 1, "usuario_id": 7})())

    out = registrar_consumo.invoke({"itens": ITENS, "confirmado": True})
    assert gravou == [], "não deveria ter gravado"
    assert isinstance(out, str) and "não salvei nada" in out.lower()


def test_confirmado_parcial_grava_e_avisa(monkeypatch):
    # Parcial continua gravando: travar o usuário por causa de um item seria pior.
    # Mas a ressalva é obrigatória.
    gravou = []
    monkeypatch.setattr(
        t.go_api, "calcular_consumo",
        lambda itens: _totais([_item("arroz", "Arroz cozido"), _item("xyzabc")],
                              ignorados=["xyzabc"], completo=False),
    )

    def fake_registrar(unidade_id, itens, usuario_id=None, sobras=None):
        gravou.append(1)
        return {
            "consumo_id": 1,
            "consumido": _totais([_item("arroz", "Arroz cozido"), _item("xyzabc")],
                                 ignorados=["xyzabc"], completo=False),
            "pontuacao_pendente": {"motivo": "total incompleto"},
        }

    monkeypatch.setattr(t.go_api, "registrar_consumo", fake_registrar)
    monkeypatch.setattr(t, "current_context", lambda: type("C", (), {"unidade_id": 1, "usuario_id": 7})())

    out = registrar_consumo.invoke({"itens": ITENS, "confirmado": True})
    assert gravou == [1]
    assert "nota_do_sistema" in out and "xyzabc" in out["nota_do_sistema"]


# --- a nota só repete o que o system prompt já manda --------------------------

def test_system_prompt_tem_a_regra_de_confianca():
    # A nota entregue no retorno da tool não pode conceder nada novo; ela repete
    # esta regra. Se a regra sumir do prompt, a nota vira instrução órfã.
    assert "confianca" in SYSTEM_AGENT
    assert "itens_ignorados" in SYSTEM_AGENT


# --- IA-13: confiança "média" também precisa virar sinal ---------------------

def test_qualidade_registra_aproximados_no_cache_do_turno(monkeypatch):
    from app.agent.motor.observacao import cache_do_turno, encerrar_turno, iniciar_turno
    from app.agent.dominio.refeitorio.tools import CACHE_APROXIMADOS, CACHE_NAO_RECONHECIDOS

    monkeypatch.setattr(
        t.go_api, "calcular_consumo",
        lambda itens: _totais([
            _item("arroz", "Arroz Integral Cozido", confianca="media",
                  obs="valor da tabela marcado para revisão nutricional"),
            _item("xyzabc"),
        ], ignorados=["xyzabc"], completo=False),
    )
    monkeypatch.setattr(t, "current_context", lambda: type("C", (), {"unidade_id": 1, "usuario_id": 7})())

    token = iniciar_turno()
    try:
        registrar_consumo.invoke({"itens": ITENS, "confirmado": False})
        cache = cache_do_turno()
    finally:
        encerrar_turno(token)

    # Os dois eixos são distintos: um saiu da conta, o outro entrou impreciso.
    assert cache[CACHE_NAO_RECONHECIDOS] == ["xyzabc"]
    assert cache[CACHE_APROXIMADOS] == ["arroz"]


def test_aproximado_sozinho_ja_gera_sinal(monkeypatch):
    # Antes do IA-13 este caso não gerava nota nenhuma: tudo entrou na conta,
    # então a resposta saía com cara de exata mesmo com casamento incerto.
    from app.agent.motor.observacao import cache_do_turno, encerrar_turno, iniciar_turno
    from app.agent.dominio.refeitorio.tools import CACHE_APROXIMADOS

    monkeypatch.setattr(
        t.go_api, "calcular_consumo",
        lambda itens: _totais([_item("arroz", "Arroz Integral Cozido", confianca="media")]),
    )
    monkeypatch.setattr(t, "current_context", lambda: type("C", (), {"unidade_id": 1, "usuario_id": 7})())

    token = iniciar_turno()
    try:
        out = registrar_consumo.invoke({"itens": ITENS, "confirmado": False})
        cache = cache_do_turno()
    finally:
        encerrar_turno(token)

    assert cache[CACHE_APROXIMADOS] == ["arroz"]
    assert "nota_do_sistema" in out and "aproxima" in out["nota_do_sistema"].lower()
