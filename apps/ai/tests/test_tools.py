"""Tools: parsing tolerante de itens e o contrato de confirmação em duas etapas."""

from app.agent.dominio.refeitorio.tools import _parse_itens, registrar_consumo


def test_parse_itens_aceita_lista():
    itens = [{"alimento": "arroz", "medida": "concha", "quantidade": 2}]
    assert _parse_itens(itens) == itens


def test_parse_itens_tolera_string_json():
    assert _parse_itens('[{"alimento":"arroz","medida":"concha","quantidade":2}]') == [
        {"alimento": "arroz", "medida": "concha", "quantidade": 2}
    ]


def test_parse_itens_rejeita_lixo():
    assert _parse_itens("nao é json") is None
    assert _parse_itens('{"nao": "é lista"}') is None
    assert _parse_itens(None) is None


def test_registrar_consumo_exige_itens():
    # tool do LangChain: invocar via .invoke com args
    resultado = registrar_consumo.invoke({"itens": []})
    assert isinstance(resultado, str)
    assert "ao menos um item" in resultado


def test_registrar_consumo_tem_parametro_confirmado():
    # Regressão IA-07: o registro deve ser em duas etapas (prévia → confirmado).
    campos = registrar_consumo.args_schema.model_json_schema()["properties"]
    assert "confirmado" in campos
    assert campos["confirmado"].get("default") is False


def test_previa_inclui_sobras(monkeypatch):
    # Regressão do review: a prévia (confirmado=False) precisa calcular também as
    # sobras — são elas que alimentam o índice de resto-ingesta que o usuário confirma.
    import app.agent.dominio.refeitorio.tools as t

    chamadas = []

    def fake_calcular(itens):
        chamadas.append(itens)
        return {"itens": itens, "kcal_total": 100 * len(itens)}

    monkeypatch.setattr(t.go_api, "calcular_consumo", fake_calcular)
    monkeypatch.setattr(t, "current_context", lambda: type("C", (), {"unidade_id": 1, "usuario_id": 1})())

    out = registrar_consumo.invoke({
        "itens": [{"alimento": "arroz", "medida": "concha", "quantidade": 2}],
        "sobras": [{"alimento": "arroz", "medida": "colher", "quantidade": 1}],
        "confirmado": False,
    })
    assert "previa" in out
    assert "consumido" in out["previa"] and "resto" in out["previa"]
    # calcular_consumo foi chamado para itens E para sobras
    assert len(chamadas) == 2
