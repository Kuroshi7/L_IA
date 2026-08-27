"""IA-20 — o mesmo prato com dois valores na mesma conversa.

No teste de usabilidade a Lia disse "Frango Grelhado — 165 kcal" na
recomendação e "1 filé de frango — ~121 kcal" no registro, três turnos depois.
Mesmo prato, mesma conversa, dois números e nenhuma explicação.
"""

from app.agent.dominio.refeitorio.tools import _divergencia_de_procedencia


def _item(nome, kcal, declarada=None):
    it = {"alimento_resolvido": nome, "kcal": kcal, "entrada": {"alimento": nome}}
    if declarada is not None:
        it["kcal_declarada_cardapio"] = declarada
    return it


def test_divergencia_grande_gera_nota():
    nota = _divergencia_de_procedencia({"itens": [_item("Frango Grelhado", 121, 165)]})
    assert "PROCEDÊNCIA DIFERENTE" in nota
    assert "121" in nota and "165" in nota


def test_nota_orienta_a_explicar_em_vez_de_escolher():
    """O erro a evitar não é divergir — é apresentar como se um estivesse errado."""
    nota = _divergencia_de_procedencia({"itens": [_item("Frango", 121, 165)]})
    assert "NÃO apresente os dois números como se um deles estivesse errado" in nota


def test_diferenca_pequena_nao_vira_ruido():
    """Arredondamento não é divergência. Nota para tudo treina o modelo a ignorar."""
    assert _divergencia_de_procedencia({"itens": [_item("Arroz", 160, 165)]}) == ""


def test_sem_valor_declarado_nao_ha_o_que_comparar():
    assert _divergencia_de_procedencia({"itens": [_item("Lasanha", 300)]}) == ""


def test_item_zerado_nao_gera_nota():
    """Item que não resolveu já tem o aviso de incompleto; somar outro é ruído."""
    assert _divergencia_de_procedencia({"itens": [_item("xyz", 0, 165)]}) == ""


def test_varios_itens_divergentes_entram_juntos():
    nota = _divergencia_de_procedencia({"itens": [
        _item("Frango", 121, 165),
        _item("Arroz", 328, 110),
    ]})
    assert "Frango" in nota and "Arroz" in nota
    assert nota.count(";") == 1  # um separador para dois itens


def test_lista_vazia():
    assert _divergencia_de_procedencia({}) == ""
