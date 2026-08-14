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


def _parse_itens(itens) -> list[dict] | None:
    """Tolera o modelo mandar string JSON em vez de lista."""
    if isinstance(itens, str):
        try:
            itens = _json.loads(itens)
        except Exception:
            return None
    if not isinstance(itens, list):
        return None
    return itens


@tool
def registrar_consumo(itens: list[dict], sobras: list[dict] | None = None, confirmado: bool = False) -> dict | str:
    """Registra a refeição que o usuário consumiu, em DUAS ETAPAS:
    1) SEM `confirmado` (default): retorna uma PRÉVIA calculada (itens interpretados +
       kcal/macros), SEM salvar nada. Apresente a prévia ao usuário e PERGUNTE se está
       correto (ex.: "Entendi: 2 conchas de arroz (~180 kcal)… confirma?").
    2) Com `confirmado=true` (só após o usuário confirmar): SALVA o registro, PONTUA
       (gamificação: proximidade da meta calórica + bônus prato limpo + streak) e
       alimenta o controle de desperdício da unidade.

    `itens` = o que a pessoa COMEU. `sobras` (opcional) = o que ela DEIXOU NO PRATO
    (pergunta se sobrou algo — é assim que medimos desperdício). Ambos são listas de:
      - alimento: nome (ex: "arroz", "frango grelhado", "feijao")
      - medida: medida caseira (ex: "concha", "colher de sopa", "file", "prato raso")
      - quantidade: número (ex: 2)
    Exemplo:
      itens=[{"alimento":"arroz","medida":"concha","quantidade":2}], sobras=[{"alimento":"arroz","medida":"colher de sopa","quantidade":1}]

    Retorno confirmado: consumido (totais/itens), resto, indice_resto_perc, pontuacao
    {pontos, pontos_base, bonus_prato_limpo, bonus_streak, meta_kcal_refeicao, desvio_perc}
    e gamificacao {pontos acumulados, nivel, streak_dias}. Os NÚMEROS vêm da base — não invente.
    """
    itens = _parse_itens(itens)
    if not itens:
        return "Envie ao menos um item {alimento, medida, quantidade}."
    sobras = _parse_itens(sobras) if sobras else []
    ctx = current_context()

    if not confirmado:
        # Prévia determinística, sem efeito colateral: erro de extração da LLM é
        # corrigido pelo usuário ANTES de virar pontuação e métrica de desperdício.
        try:
            previa = go_api.calcular_consumo(itens)
        except Exception:
            return "Não foi possível calcular a prévia agora."
        return {
            "previa": previa,
            "instrucao": (
                "PRÉVIA — nada foi salvo. Mostre os itens interpretados e as calorias ao "
                "usuário e pergunte se está correto. Só depois da confirmação dele, chame "
                "registrar_consumo de novo com os MESMOS itens/sobras e confirmado=true."
            ),
        }

    try:
        return go_api.registrar_consumo(ctx.unidade_id, itens, ctx.usuario_id, sobras)
    except Exception:
        return "Não foi possível registrar o consumo agora."


@tool
def cardapio_da_semana(inicio: str = "") -> dict | str:
    """Cardápio da SEMANA (segunda a sexta) da unidade atual. Use quando o usuário
    perguntar sobre outros dias ("o que tem amanhã/na quarta?", "qual o cardápio da semana?").
    `inicio` = segunda-feira em ISO (ex: "2026-07-06"); vazio usa a semana atual.
    Retorna {inicio, dias: [{data, dia_semana, pratos: [{nome, categoria}]}]}."""
    ctx = current_context()
    try:
        semana = go_api.get_cardapio_semana(ctx.unidade_id, inicio or "")
    except Exception:
        return "Não foi possível carregar o cardápio da semana agora."
    return {
        "inicio": semana.get("inicio"),
        "dias": [
            {
                "data": d.get("data"),
                "dia_semana": d.get("dia_semana"),
                "pratos": [filters.resumir(p) for p in (d.get("pratos") or [])],
            }
            for d in (semana.get("dias") or [])
        ],
    }


@tool
def meus_pontos() -> dict | str:
    """Pontuação de gamificação do usuário atual: pontos acumulados, nível, streak de
    dias registrando consumo e os últimos eventos de pontuação. Use quando perguntarem
    "quantos pontos eu tenho?", "qual meu nível?", "como funciona a pontuação?"."""
    ctx = current_context()
    if not ctx.usuario_id:
        return ("Usuário não identificado nesta sessão — para acumular pontos é preciso "
                "criar um perfil (no site) e conversar identificado.")
    try:
        return go_api.get_gamificacao(ctx.usuario_id)
    except Exception:
        return "Não foi possível carregar sua pontuação agora."


TOOLS = [
    listar_pratos_do_dia,
    cardapio_da_semana,
    filtrar_pratos,
    detalhar_prato,
    comparar_pratos,
    meu_perfil,
    meus_pontos,
    consultar_medidas_caseiras,
    buscar_informacao,
    registrar_consumo,
]
