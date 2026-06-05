"""Tools LangChain expostas ao agente.

Os dados vêm da API interna do serviço Go (fonte da verdade), sempre filtrados
pela UNIDADE do contexto da requisição. Args usam CSV string (mais robusto para
LLMs pequenos). A filtragem por restrição/alergia é determinística em Python.
"""

import json as _json
from typing import Literal

from langchain_core.tools import tool

from app.agent import filters
from app.agent.context import current_context
from app.clients import go_api
from app.rag import retriever


def _csv(s: str | None) -> list[str]:
    if not s:
        return []
    return [item.strip() for item in s.split(",") if item.strip()]


@tool
def listar_pratos_do_dia(dia: str = "hoje") -> list[dict]:
    """Lista TODOS os pratos do cardápio do dia da unidade atual. `dia` aceita 'hoje'
    ou data ISO '2026-05-28'. Retorna [{id, nome, categoria}, ...]. Use SEMPRE quando o
    usuário pedir o cardápio — mostre a lista completa antes de recomendar."""
    ctx = current_context()
    pratos = go_api.get_pratos(ctx.unidade_id, dia or "hoje")
    return [filters.resumir(p) for p in pratos]


@tool
def filtrar_pratos(restricoes: str = "", alergias: str = "", preferencias: str = "", dia: str = "hoje") -> list[dict]:
    """Filtra os pratos do dia (da unidade atual) que atendem TODAS as restrições, são
    seguros para TODAS as alergias e combinam com as preferências. Use ao recomendar.

    Args (CSV string): restricoes ex "vegetariano,sem gluten"; alergias ex "peixe,lactose";
    preferencias ex "proteico,frango"; dia "hoje" (default) ou data ISO.
    Retorna pratos completos compatíveis. Lista vazia = nenhum atende."""
    ctx = current_context()
    rest, alerg, pref = _csv(restricoes), _csv(alergias), _csv(preferencias)
    pratos = go_api.get_pratos(ctx.unidade_id, dia or "hoje")

    compativeis = []
    for p in pratos:
        if not all(filters.prato_atende_restricao(p, r) for r in rest):
            continue
        if not filters.prato_seguro_para_alergias(p, alerg):
            continue
        if pref and not any(filters.prato_combina_preferencia(p, x) for x in pref):
            continue
        compativeis.append(p)
    return compativeis


@tool
def detalhar_prato(prato_id: int, dia: str = "hoje") -> dict | str:
    """Detalhes completos de um prato do cardápio do dia (ingredientes, alérgenos, nutrição)."""
    ctx = current_context()
    for p in go_api.get_pratos(ctx.unidade_id, dia or "hoje"):
        if p["id"] == prato_id:
            return p
    return f"Prato com id {prato_id} não encontrado no cardápio de hoje."


@tool
def comparar_pratos(
    criterio: Literal["proteinas", "calorias", "carboidratos", "gorduras"] = "proteinas",
    prato_ids: str = "",
    dia: str = "hoje",
) -> list[dict]:
    """Compara pratos do dia por critério nutricional (decrescente). Use para "qual tem mais/menos X?".
    prato_ids: CSV de ids; vazio = compara todos do dia."""
    ctx = current_context()
    chave = {"proteinas": "proteinas_g", "calorias": "calorias",
             "carboidratos": "carboidratos_g", "gorduras": "gorduras_g"}.get(criterio, "proteinas_g")

    pratos = go_api.get_pratos(ctx.unidade_id, dia or "hoje")
    ids = {int(x) for x in _csv(prato_ids) if x.isdigit()}
    if ids:
        pratos = [p for p in pratos if p["id"] in ids]

    resultado = [{"id": p["id"], "nome": p["nome"], "criterio": criterio, "valor": p.get(chave, 0)} for p in pratos]
    resultado.sort(key=lambda x: x["valor"], reverse=True)
    return resultado


@tool
def meu_perfil() -> dict | str:
    """Retorna o perfil do usuário atual (restrições, preferências, alergias, IMC e meta
    calórica diária), quando disponível. Use para personalizar recomendações e porções."""
    ctx = current_context()
    if not ctx.usuario_id:
        return "Usuário não identificado nesta sessão — peça as restrições/preferências diretamente."
    try:
        return go_api.get_perfil(ctx.usuario_id)
    except Exception:
        return "Não foi possível carregar o perfil do usuário agora."


@tool
def consultar_medidas_caseiras() -> list[dict]:
    """Tabela de medidas caseiras (medida → gramas → kcal) para traduzir recomendações em
    porções práticas no self-service (ex.: '2 colheres de arroz')."""
    try:
        return go_api.get_medidas_caseiras()
    except Exception:
        return []


@tool
def buscar_informacao(consulta: str) -> str:
    """Busca semântica (RAG) em guias de medidas caseiras e referência nutricional da unidade.
    Use para dúvidas sobre porções, cálculo calórico/IMC e orientações gerais de consumo."""
    ctx = current_context()
    trechos = retriever.buscar(consulta, unidade_id=ctx.unidade_id, k=4)
    if not trechos:
        return "Sem informações adicionais indexadas para esta consulta."
    return "\n\n".join(trechos)


@tool
def registrar_consumo(itens: list[dict]) -> dict | str:
    """Calcula calorias e macronutrientes do que o usuário consumiu (refeição self-service).

    `itens` é uma LISTA de objetos, cada um com:
      - alimento: nome (ex: "arroz", "frango grelhado", "feijao", "salada de legumes")
      - medida: medida caseira (ex: "concha", "colher de sopa", "file", "prato raso", "escumadeira")
      - quantidade: número (ex: 2)
    Exemplo:
      [{"alimento":"arroz","medida":"concha","quantidade":2},{"alimento":"frango grelhado","medida":"file","quantidade":1}]

    Retorna os totais (kcal, proteína, carboidrato, gordura) e o detalhamento por item,
    com o nível de confiança da resolução. Os NÚMEROS vêm da base nutricional — não invente.
    """
    # tolera o caso de o modelo mandar uma string JSON em vez de lista
    if isinstance(itens, str):
        try:
            itens = _json.loads(itens)
        except Exception:
            return "Envie `itens` como lista de {alimento, medida, quantidade}."
    if not isinstance(itens, list) or not itens:
        return "Envie ao menos um item {alimento, medida, quantidade}."
    try:
        return go_api.calcular_consumo(itens)
    except Exception:
        return "Não foi possível calcular o consumo agora."


TOOLS = [
    listar_pratos_do_dia,
    filtrar_pratos,
    detalhar_prato,
    comparar_pratos,
    meu_perfil,
    consultar_medidas_caseiras,
    buscar_informacao,
    registrar_consumo,
]
