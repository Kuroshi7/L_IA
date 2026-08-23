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


def carregar_casos() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CASOS.glob("*.json"))]


def instalar(monkeypatch, dados: dict) -> None:
    import app.agent.dominio.refeitorio.tools as t

    pratos = dados["pratos"]
    monkeypatch.setattr(t.go_api, "get_pratos", lambda unidade_id, dia: [dict(p) for p in pratos])
    monkeypatch.setattr(t.go_api, "get_perfil", lambda usuario_id: dict(dados["perfil"]))
    monkeypatch.setattr(t.go_api, "get_medidas_caseiras", lambda: list(dados["medidas"]))
    monkeypatch.setattr(t.go_api, "get_gamificacao", lambda usuario_id: dict(dados["gamificacao"]))
    monkeypatch.setattr(t.go_api, "calcular_consumo", lambda itens: dict(dados["consumo"]))
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
