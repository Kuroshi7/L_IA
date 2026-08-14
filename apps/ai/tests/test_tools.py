"""Tools: parsing tolerante de itens e o contrato de confirmação em duas etapas."""

from app.agent.tools import _parse_itens, registrar_consumo


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
