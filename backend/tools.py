"""Tools LangChain expostas ao agent. Args usam CSV string (mais robusto para LLMs pequenos
que tendem a enviar tipos errados quando recebem list[str]). Lógica de filtragem é determinística
em Python, garantindo que vegetariano nunca veja prato com carne."""

from typing import Literal

from langchain_core.tools import tool

from cardapio import (
    formatar_pratos_resumido,
    get_pratos_do_dia,
    get_prato_por_id,
    prato_atende_restricao,
    prato_combina_preferencia,
    prato_seguro_para_alergias,
)


def _csv_para_lista(s: str | None) -> list[str]:
    if not s:
        return []
    return [item.strip() for item in s.split(",") if item.strip()]


@tool
def listar_pratos_do_dia(dia: str = "hoje") -> list[dict]:
    """Lista os pratos disponíveis num dia. `dia` aceita 'hoje', 'segunda-feira',
    'terca-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira' ou data ISO '2026-04-27'.
    Retorna [{id, nome, categoria}, ...]. Use SEMPRE esta tool quando o usuário perguntar
    o que tem no cardápio sem informar restrições."""
    pratos = get_pratos_do_dia(dia or "hoje")
    return formatar_pratos_resumido(pratos)


@tool
def filtrar_pratos(
    restricoes: str = "",
    alergias: str = "",
    preferencias: str = "",
    dia: str = "hoje",
) -> list[dict]:
    """Filtra pratos do dia que atendem TODAS as restrições, são seguros para TODAS as alergias
    e combinam com as preferências. Use SEMPRE quando o usuário mencionar restrição/alergia.

    Args (todos como CSV string, vírgula-separado):
      restricoes: ex. "vegetariano,sem gluten" ou "vegano" ou "celiaco,low carb"
      alergias:   ex. "amendoim,peixe" ou "lactose"
      preferencias: ex. "proteico,frango" ou "salada"
      dia: ex. "hoje" (default), "segunda-feira", "terca-feira", "sexta-feira"

    Retorna lista de pratos completos compatíveis. Lista vazia = nenhum prato atende."""
    rest_list = _csv_para_lista(restricoes)
    alerg_list = _csv_para_lista(alergias)
    pref_list = _csv_para_lista(preferencias)

    pratos = get_pratos_do_dia(dia or "hoje")
    compativeis = []
    for prato in pratos:
        if not all(prato_atende_restricao(prato, r) for r in rest_list):
            continue
        if not prato_seguro_para_alergias(prato, alerg_list):
            continue
        if pref_list and not any(prato_combina_preferencia(prato, p) for p in pref_list):
            continue
        compativeis.append(prato)
    return compativeis


@tool
def detalhar_prato(prato_id: int) -> dict | str:
    """Retorna detalhes completos de um prato (ingredientes, alérgenos, nutrição, restrições).
    Use depois que o usuário escolher um prato específico ou pedir mais detalhes."""
    prato = get_prato_por_id(prato_id)
    if prato is None:
        return f"Prato com id {prato_id} não encontrado."
    return prato


@tool
def comparar_pratos(
    criterio: Literal["proteinas", "calorias", "carboidratos", "gorduras"] = "proteinas",
    prato_ids: str = "",
    dia: str = "hoje",
) -> list[dict]:
    """Compara pratos por critério nutricional, ordenando do maior para o menor valor.
    Use SEMPRE quando o usuário perguntar "qual tem mais/menos X?" (proteína, caloria, etc).

    Args:
      criterio: "proteinas" (default) | "calorias" | "carboidratos" | "gorduras"
      prato_ids: CSV de ids para comparar, ex. "101,102". Se vazio, compara TODOS os pratos do `dia`.
      dia: "hoje" (default) ou nome do dia. Usado quando prato_ids está vazio.

    Retorna [{id, nome, criterio, valor}, ...] ordenado decrescente."""
    chave = {
        "proteinas": "proteinas_g",
        "calorias": "calorias",
        "carboidratos": "carboidratos_g",
        "gorduras": "gorduras_g",
    }.get(criterio, "proteinas_g")

    ids = []
    for x in _csv_para_lista(prato_ids):
        try:
            ids.append(int(x))
        except ValueError:
            continue

    pratos_a_comparar: list[dict] = []
    if ids:
        for pid in ids:
            p = get_prato_por_id(pid)
            if p is not None:
                pratos_a_comparar.append(p)
    else:
        pratos_a_comparar = get_pratos_do_dia(dia or "hoje")

    resultado = [
        {
            "id": p["id"],
            "nome": p["nome"],
            "criterio": criterio,
            "valor": p.get("nutricao", {}).get(chave, 0),
            "nutricao_completa": p.get("nutricao", {}),
            "ingredientes": p.get("ingredientes", []),
        }
        for p in pratos_a_comparar
    ]
    resultado.sort(key=lambda x: x["valor"], reverse=True)
    return resultado


TOOLS = [listar_pratos_do_dia, filtrar_pratos, detalhar_prato, comparar_pratos]
