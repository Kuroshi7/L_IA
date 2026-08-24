"""API Go falsificada, servindo um dataset fixo.

O eval mede o comportamento do MODELO, não a integração. Com a API real no meio,
uma falha viraria ambígua ("o modelo errou ou o cardápio mudou?") e o resultado
deixaria de servir como gate de regressão de prompt.
"""

import json
from pathlib import Path

DADOS = Path(__file__).parent / "dados"
CASOS = Path(__file__).parent / "casos"


def carregar_dados(nome: str) -> dict:
    return json.loads((DADOS / f"{nome}.json").read_text(encoding="utf-8"))


def carregar_casos(bateria: str | None = None) -> list[dict]:
    """Casos de todas as baterias. O diretório-pai vira o nome da bateria, então
    adicionar uma bateria é criar uma pasta — sem registro em lugar nenhum."""
    casos = []
    for arquivo in sorted(CASOS.rglob("*.json")):
        caso = json.loads(arquivo.read_text(encoding="utf-8"))
        caso["bateria"] = arquivo.parent.name if arquivo.parent != CASOS else "geral"
        caso["arquivo"] = arquivo.name
        if bateria and caso["bateria"] != bateria:
            continue
        casos.append(caso)
    return casos


def baterias() -> list[str]:
    return sorted({c["bateria"] for c in carregar_casos()})


# Gramas por medida caseira, o suficiente para o fake responder à ENTRADA.
# Sem isto ele devolvia o mesmo total para qualquer item, e "1 colher" saía do
# mesmo tamanho de "3 conchas" — o que anulava silenciosamente a checagem de
# sobra maior que consumo, e fazia o caso medir 0/3 com o produto correto.
_GRAMAS = {
    "concha": 90, "colher de sopa": 20, "colher": 20, "colher de arroz": 45,
    "file": 100, "filé": 100, "prato": 250, "prato raso": 250, "prato fundo": 300,
    "unidade": 80, "porcao": 100, "porção": 100, "pegador": 40, "fatia": 30,
    "escumadeira": 60, "pedaco": 70, "pedaço": 70,
}


def _gramas(itens) -> float:
    total = 0.0
    for i in itens or []:
        medida = str(i.get("medida", "")).strip().lower()
        total += _GRAMAS.get(medida, 60) * float(i.get("quantidade", 1) or 1)
    return total


def _consumo_proporcional(base: dict, itens) -> dict:
    """O total do dataset, reescalado pelo que foi de fato informado."""
    gramas = _gramas(itens)
    ref = float(base.get("gramas_totais") or 0) or gramas or 1.0
    fator = gramas / ref if ref else 1.0
    out = dict(base)
    out["gramas_totais"] = round(gramas, 1)
    for chave in ("kcal", "proteina_g", "carboidrato_g", "gordura_g"):
        if base.get(chave) is not None:
            out[chave] = round(float(base[chave]) * fator, 2)
    return out


def instalar(monkeypatch, dados: dict) -> None:
    import app.agent.dominio.refeitorio.tools as t

    pratos = dados["pratos"]
    monkeypatch.setattr(t.go_api, "get_pratos", lambda unidade_id, dia: [dict(p) for p in pratos])
    monkeypatch.setattr(t.go_api, "get_perfil", lambda usuario_id: dict(dados["perfil"]))
    monkeypatch.setattr(t.go_api, "get_medidas_caseiras", lambda: list(dados["medidas"]))
    monkeypatch.setattr(t.go_api, "get_gamificacao", lambda usuario_id: dict(dados["gamificacao"]))
    monkeypatch.setattr(t.go_api, "calcular_consumo",
                        lambda itens: _consumo_proporcional(dados["consumo"], itens))
    monkeypatch.setattr(
        t.go_api, "get_cardapio_semana",
        lambda unidade_id, inicio="": {
            "inicio": "2026-08-24",
            "dias": [{"data": "2026-08-24", "dia_semana": "segunda", "pratos": pratos}],
        },
    )
    monkeypatch.setattr(
        t.go_api, "registrar_consumo",
        lambda unidade_id, itens, usuario_id=None, sobras=None: {
            "consumo_id": 1, "consumido": dict(dados["consumo"]),
            "resto": {"itens": [], "kcal": 0, "gramas_totais": 0, "completo": True},
            "indice_resto_perc": 0.0,
        },
    )
    monkeypatch.setattr(t.retriever, "buscar", lambda consulta, unidade_id=None, k=4: list(dados.get("rag", [])))
