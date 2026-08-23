"""Estado do turno: cache de leitura, colheita de observações e a guarda do decorator."""

import pytest
from langchain_core.tools import tool

import app.agent.dominio.refeitorio.tools as t
from app.agent.motor.observacao import (
    ObservacoesDoTurno,
    encerrar_turno,
    iniciar_turno,
    observacoes_do_turno,
    observado,
)

PRATOS = [
    {"id": 1, "nome": "Frango grelhado", "categoria": "proteina", "calorias": 180,
     "proteinas_g": 31, "restricoes_atendidas": [], "alergenos": [], "ingredientes": []},
    {"id": 2, "nome": "Arroz integral", "categoria": "acompanhamento", "calorias": 110,
     "proteinas_g": 2.5, "restricoes_atendidas": ["vegetariano"], "alergenos": [], "ingredientes": []},
]


@pytest.fixture
def turno(monkeypatch):
    """Um turno ativo com a API Go falsificada, contando as chamadas HTTP."""
    chamadas = []

    def fake_get_pratos(unidade_id, dia):
        chamadas.append((unidade_id, dia))
        return [dict(p) for p in PRATOS]

    monkeypatch.setattr(t.go_api, "get_pratos", fake_get_pratos)
    monkeypatch.setattr(t, "current_context", lambda: type("C", (), {"unidade_id": 1, "usuario_id": 7})())

    token = iniciar_turno()
    try:
        yield chamadas
    finally:
        encerrar_turno(token)


def test_quatro_tools_de_cardapio_fazem_uma_leitura_so(turno):
    # O motivo de existir do cache: as 4 tools consultam o mesmo dia no mesmo
    # turno, e cada GET a mais come o orçamento de 60s do Go.
    t.listar_pratos_do_dia.invoke({"dia": "hoje"})
    t.filtrar_pratos.invoke({"restricoes": "vegetariano", "dia": "hoje"})
    t.detalhar_prato.invoke({"prato_id": 1, "dia": "hoje"})
    t.comparar_pratos.invoke({"criterio": "proteinas", "dia": "hoje"})

    assert len(turno) == 1, f"esperava 1 leitura do cardápio, houve {len(turno)}: {turno}"


def test_dia_diferente_e_leitura_diferente(turno):
    t.listar_pratos_do_dia.invoke({"dia": "hoje"})
    t.listar_pratos_do_dia.invoke({"dia": "2026-08-24"})
    assert len(turno) == 2


def test_tools_funcionam_fora_de_turno(monkeypatch):
    # Sem estado de turno as tools seguem utilizáveis (teste, script, REPL).
    # É o que mantém a suíte existente válida sem montar contexto.
    monkeypatch.setattr(t.go_api, "get_pratos", lambda u, d: [dict(p) for p in PRATOS])
    monkeypatch.setattr(t, "current_context", lambda: type("C", (), {"unidade_id": 1, "usuario_id": None})())

    assert observacoes_do_turno() is None
    assert len(t.listar_pratos_do_dia.invoke({"dia": "hoje"})) == 2


def test_observacoes_colhem_itens_e_valores(turno):
    t.filtrar_pratos.invoke({"restricoes": "vegetariano", "dia": "hoje"})
    obs = observacoes_do_turno()

    assert "arroz integral" in obs.itens_conhecidos           # normalizado, sem acento
    assert 110.0 in obs.valores_expostos                       # kcal exposta ao modelo
    assert obs.nomes_chamados == ["filtrar_pratos"]


def test_listagem_nao_expoe_numeros_que_nao_mostrou(turno):
    # `listar_pratos_do_dia` devolve só {id, nome, categoria} — a kcal NUNCA foi
    # mostrada ao modelo. Se ela entrasse em valores_expostos, um número
    # inventado passaria batido na validação.
    t.listar_pratos_do_dia.invoke({"dia": "hoje"})
    obs = observacoes_do_turno()

    assert "frango grelhado" in obs.itens_conhecidos
    assert 180.0 not in obs.valores_expostos


def test_id_nao_vira_valor_exposto(turno):
    t.listar_pratos_do_dia.invoke({"dia": "hoje"})
    obs = observacoes_do_turno()
    assert 1.0 not in obs.valores_expostos and 2.0 not in obs.valores_expostos


# --- guarda do decorator -----------------------------------------------------

def _exemplo(dia: str = "hoje", quantidade: int = 1) -> list[dict]:
    """Docstring que vira a description da tool."""
    return [{"nome": "x"}]


def test_observado_nao_altera_o_schema_visto_pelo_modelo():
    # A ordem `@tool` por fora / `@observado` por dentro só funciona porque
    # functools.wraps preserva __wrapped__ para o inspect.signature do @tool.
    # Inverter a ordem ou perder o wraps quebra o schema em silêncio — e o
    # modelo passa a receber `(*args, **kwargs)`.
    nu = tool(_exemplo)
    envolvida = tool(observado(_exemplo))

    assert nu.name == envolvida.name
    assert nu.description == envolvida.description
    assert nu.args_schema.model_json_schema() == envolvida.args_schema.model_json_schema()


def test_tools_reais_mantiveram_nome_e_schema():
    campos = t.listar_pratos_do_dia.args_schema.model_json_schema()["properties"]
    assert t.listar_pratos_do_dia.name == "listar_pratos_do_dia"
    assert "dia" in campos
    assert "cardápio" in t.listar_pratos_do_dia.description.lower()


def test_colheita_ignora_booleanos():
    # bool é subclasse de int; sem tratamento, `confirmado=True` viraria 1.0 na
    # lista de números que a resposta pode citar.
    obs = ObservacoesDoTurno()
    obs.registrar(("x", "{}"), {"nome": "a", "ok": True, "kcal": 42})
    assert 1.0 not in obs.valores_expostos
    assert 42.0 in obs.valores_expostos
