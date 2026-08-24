"""Tools LangChain expostas ao agente.

Os dados vêm da API interna do serviço Go (fonte da verdade), sempre filtrados
pela UNIDADE do contexto da requisição. Args usam CSV string (mais robusto para
LLMs pequenos). A filtragem por restrição/alergia é determinística em Python.
"""

import json as _json
import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from dataclasses import dataclass, field
from typing import Literal

from langchain_core.tools import tool

from app.agent.dominio.refeitorio import filters
from app.agent.context import current_context
from app.agent.motor.observacao import cache_do_turno, observado
from app.agent.motor.reminders import anexar_ao_resultado
from app.clients import go_api
from app.rag import retriever

log = logging.getLogger("agent")


def _csv(s: str | None) -> list[str]:
    if not s:
        return []
    return [item.strip() for item in s.split(",") if item.strip()]


@dataclass
class Qualidade:
    """Cobertura do cálculo devolvido pela API Go.

    A base nutricional não cobre tudo o que uma pessoa diz ter comido. Quando um
    termo não resolve, o item entra na resposta ZERADO e fica de fora do total —
    ou seja, o número sai menor que o real. Apresentar esse número como final é
    exatamente o comportamento de um LLM genérico que "chuta calorias"; declarar
    a incerteza é o que diferencia este produto.
    """

    ignorados: list[str] = field(default_factory=list)   # não entraram na conta
    imprecisos: list[str] = field(default_factory=list)  # entraram, com ressalva
    total_itens: int = 0

    @property
    def tudo_ignorado(self) -> bool:
        return self.total_itens > 0 and len(self.ignorados) == self.total_itens

    @property
    def ha_incerteza(self) -> bool:
        return bool(self.ignorados or self.imprecisos)


def _qualidade(*totais: dict) -> Qualidade:
    q = Qualidade()
    for tot in totais:
        if not isinstance(tot, dict):
            continue
        itens = tot.get("itens") or []
        q.total_itens += len(itens)

        # Caminho normal: a API Go informa o que ficou de fora.
        ignorados = list(tot.get("itens_ignorados") or [])

        for item in itens:
            entrada = (item.get("entrada") or {}).get("alimento") or "?"
            resolvido = item.get("alimento_resolvido")
            if not resolvido:
                # Compatibilidade: se a API ainda não manda `itens_ignorados`,
                # o sintoma continua visível item a item.
                if entrada not in ignorados:
                    ignorados.append(entrada)
            elif item.get("confianca") != "alta" or item.get("obs"):
                q.imprecisos.append(f"{entrada} → {resolvido}")

        q.ignorados.extend(ignorados)
    return q


# Chave do cache do turno onde guardamos os termos que a base não reconheceu.
# É o cache genérico do motor: o domínio guarda o que quiser, sem o motor
# precisar de um campo novo para isso.
CACHE_NAO_RECONHECIDOS = "nao_reconhecidos"
# Itens que a base reconheceu, mas cujo número é aproximado (casamento
# incerto ou porção marcada para revisão nutricional).
CACHE_APROXIMADOS = "aproximados"


def _registrar_qualidade(q: Qualidade) -> None:
    """Leva a qualidade do cálculo para o log E para a resposta do chat."""
    _logar_nao_resolvidos(q)
    if q.imprecisos:
        # Só o termo que a pessoa escreveu — é o que ela reconhece e pode
        # reescrever; "Arroz Integral Cozido → concha M" não diz nada a ela.
        _acumular(CACHE_APROXIMADOS, [i.split(" → ")[0] for i in q.imprecisos])


def _logar_nao_resolvidos(q: Qualidade) -> None:
    """Os termos que o usuário usou e a base não conhece são exatamente os
    aliases que faltam em `nutri_alimentos`. Logar em WARNING transforma cada
    falha de reconhecimento em insumo de melhoria da base."""
    if not q.ignorados:
        return
    termos = sorted(set(q.ignorados))
    log.warning("CONSUMO | itens_nao_resolvidos | termos=%s", termos)

    # Também sobe para a resposta do chat: é o sinal de incerteza que o usuário
    # precisa ver. Sem isto, o produto se comporta como um LLM genérico — dá o
    # número com a mesma cara de certeza, tenha reconhecido tudo ou não.
    _acumular(CACHE_NAO_RECONHECIDOS, termos)


def _acumular(chave: str, termos) -> None:
    cache = cache_do_turno()
    if cache is None:
        return
    acumulado = cache.setdefault(chave, [])
    for termo in termos:
        if termo not in acumulado:
            acumulado.append(termo)


# Prefixo estável nas notas que falam de INCERTEZA. A R4 se ancora nele: sem
# isso ela dispararia em qualquer `nota_do_sistema`, inclusive a instrução
# operacional que a listagem de cardápio passou a carregar.
MARCA_INCERTEZA = "INCERTEZA:"


def _nota_de_incerteza(q: Qualidade) -> str:
    partes = []
    if q.ignorados:
        partes.append(
            "NÃO reconheci na base: " + ", ".join(sorted(set(q.ignorados))) + ". "
            "Esses itens NÃO entraram no total — diga isso ao usuário com estas "
            "palavras, NÃO apresente o total como final e peça que ele descreva o "
            "item de outro jeito (ex.: 'file de frango grelhado' → 'frango')."
        )
    if q.imprecisos:
        partes.append(
            "Interpretei por APROXIMAÇÃO: " + "; ".join(sorted(set(q.imprecisos))) + ". "
            "Diga ao usuário, com a palavra \"aproximado\" ou \"estimativa\", que esses "
            "números não são exatos, e confirme com ele antes de tratá-los como certos."
        )
    return f"{MARCA_INCERTEZA} " + " ".join(partes) if partes else ""


def _perfil_do_turno() -> dict | None:
    """Perfil do usuário, uma leitura por turno. Silencioso em caso de erro:
    perfil indisponível não pode derrubar o cardápio."""
    ctx = current_context()
    if not getattr(ctx, "usuario_id", None):
        return None
    cache = cache_do_turno()
    if cache is not None and "perfil" in cache:
        return cache["perfil"]
    try:
        perfil = go_api.get_perfil(ctx.usuario_id)
    except Exception:
        perfil = None
    if cache is not None:
        cache["perfil"] = perfil
    return perfil


def _anotar_conflitos(pratos: list[dict]) -> list[dict]:
    """Marca cada prato incompatível com o perfil, sem removê-lo da lista.

    A regra contratual obriga mostrar o cardápio COMPLETO, então esconder não é
    opção — mas entregar a lista crua sem aviso deixava a segurança alimentar
    na mão da memória do modelo.
    """
    perfil = _perfil_do_turno()
    if not perfil:
        return pratos
    anotados = []
    for p in pratos:
        motivos = filters.conflitos_com_perfil(p, perfil)
        anotados.append({**p, "conflita_com_perfil": motivos} if motivos else p)
    return anotados


def _pratos(dia: str) -> list[dict]:
    """Uma leitura do cardápio por turno.

    Quatro tools (`listar_pratos_do_dia`, `filtrar_pratos`, `detalhar_prato`,
    `comparar_pratos`) consultam o MESMO dia no mesmo turno; sem isto são até 4
    GETs idênticos na API Go dentro de um orçamento de 60s. Fora de um turno
    (teste, script) não há cache e o comportamento é o de sempre.
    """
    ctx = current_context()
    dia = dia or "hoje"
    cache = cache_do_turno()
    if cache is None:
        return go_api.get_pratos(ctx.unidade_id, dia)
    chave = ("pratos", ctx.unidade_id, dia)
    if chave not in cache:
        cache[chave] = _anotar_conflitos(go_api.get_pratos(ctx.unidade_id, dia))
    return cache[chave]


@tool
@observado
def listar_pratos_do_dia(dia: str = "hoje") -> dict:
    """Lista TODOS os pratos do cardápio do dia da unidade atual. `dia` aceita 'hoje'
    ou data ISO '2026-05-28'. Use SEMPRE quando o usuário pedir o cardápio — mostre a
    lista completa antes de recomendar.

    Retorna {total, pratos: [{id, nome, categoria, conflita_com_perfil?}], nota_do_sistema}.
    `total` é quantos pratos existem: sua resposta precisa citar todos eles."""
    pratos = [filters.resumir(p) for p in _pratos(dia)]

    # `total` explícito e a nota logo abaixo existem porque o modelo resumia o
    # cardápio quando ele crescia — com 8 pratos, chegava a omitir 5. O número
    # dá a ele um alvo verificável, e a nota chega no fim do contexto (é o
    # resultado da tool), que é onde instrução é obedecida.
    if not pratos:
        return {
            "total": 0, "pratos": [],
            "nota_do_sistema": (
                f"Nenhum prato cadastrado para '{dia or 'hoje'}'. NÃO sugira nem cite "
                "nenhum prato — nem de memória, nem 'o que costuma ter'. Diga que o "
                "cardápio ainda não foi publicado e ofereça consultar outro dia."
            ),
        }

    nota = (
        f"São {len(pratos)} pratos. LISTE OS {len(pratos)} na sua resposta, com o nome "
        "exato, ANTES de qualquer recomendação — é regra contratual, vale mesmo que o "
        "usuário só tenha pedido uma sugestão."
    )
    conflitantes = [p["nome"] for p in pratos if p.get("conflita_com_perfil")]
    if conflitantes:
        nota += (
            f" ATENÇÃO: {conflitantes} são incompatíveis com o perfil desta pessoa "
            "(veja `conflita_com_perfil`). Liste-os no cardápio, mas NUNCA os recomende."
        )
    return {"total": len(pratos), "pratos": pratos, "nota_do_sistema": nota}


@tool
@observado
def filtrar_pratos(restricoes: str = "", alergias: str = "", preferencias: str = "", dia: str = "hoje") -> list[dict] | str:
    """Filtra os pratos do dia (da unidade atual) que atendem TODAS as restrições, são
    seguros para TODAS as alergias e combinam com as preferências. Use ao recomendar.

    Args (CSV string): restricoes ex "vegetariano,sem gluten"; alergias ex "peixe,lactose";
    preferencias ex "proteico,frango"; dia "hoje" (default) ou data ISO.
    Retorna pratos completos compatíveis. Lista vazia = nenhum atende."""
    rest, alerg, pref = _csv(restricoes), _csv(alergias), _csv(preferencias)
    pratos = _pratos(dia)

    compativeis = []
    for p in pratos:
        if not all(filters.prato_atende_restricao(p, r) for r in rest):
            continue
        if not filters.prato_seguro_para_alergias(p, alerg):
            continue
        if pref and not any(filters.prato_combina_preferencia(p, x) for x in pref):
            continue
        compativeis.append(p)

    if not compativeis:
        # Regra inviolável 4. Devolver [] deixava o modelo livre para "ajudar"
        # inventando algo plausível; a instrução vai junto do resultado.
        return (
            "Nenhum prato do cardápio atende a esses critérios. NÃO sugira nada fora "
            "do cardápio nem force um prato que não atende. Diga isso ao usuário e "
            "pergunte se ele pode flexibilizar algum critério."
        )
    return compativeis


@tool
@observado
def detalhar_prato(prato_id: int, dia: str = "hoje") -> dict | str:
    """Detalhes completos de um prato do cardápio do dia (ingredientes, alérgenos, nutrição)."""
    for p in _pratos(dia):
        if p["id"] == prato_id:
            return p
    return f"Prato com id {prato_id} não encontrado no cardápio de hoje."


@tool
@observado
def comparar_pratos(
    criterio: Literal["proteinas", "calorias", "carboidratos", "gorduras"] = "proteinas",
    prato_ids: str = "",
    dia: str = "hoje",
) -> list[dict]:
    """Compara pratos do dia por critério nutricional (decrescente). Use para "qual tem mais/menos X?".
    prato_ids: CSV de ids; vazio = compara todos do dia."""
    chave = {"proteinas": "proteinas_g", "calorias": "calorias",
             "carboidratos": "carboidratos_g", "gorduras": "gorduras_g"}.get(criterio, "proteinas_g")

    pratos = _pratos(dia)
    ids = {int(x) for x in _csv(prato_ids) if x.isdigit()}
    if ids:
        pratos = [p for p in pratos if p["id"] in ids]

    resultado = [{"id": p["id"], "nome": p["nome"], "criterio": criterio, "valor": p.get(chave, 0)} for p in pratos]
    resultado.sort(key=lambda x: x["valor"], reverse=True)
    return resultado


@tool
@observado
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
@observado
def consultar_medidas_caseiras() -> list[dict]:
    """Tabela de medidas caseiras (medida → gramas → kcal) para traduzir recomendações em
    porções práticas no self-service (ex.: '2 colheres de arroz')."""
    try:
        return go_api.get_medidas_caseiras()
    except Exception:
        return []


@tool
@observado
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
@observado
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
        # As SOBRAS entram na prévia — são elas que alimentam o índice de resto, então
        # o usuário precisa confirmar o que sobrou, não só o que comeu.
        try:
            consumido = go_api.calcular_consumo(itens)
            previa: dict = {"consumido": consumido}
            resto = go_api.calcular_consumo(sobras) if sobras else {}
            if sobras:
                previa["resto"] = resto
        except Exception:
            return "Não foi possível calcular a prévia agora."

        q = _qualidade(consumido, resto)
        _registrar_qualidade(q)
        resultado = {
            "previa": previa,
            "instrucao": (
                "PRÉVIA — NADA FOI SALVO AINDA. Diga isso ao usuário com estas palavras. Mostre os itens interpretados e as "
                "calorias do que ele COMEU e, se houver, do que SOBROU no prato, e pergunte "
                "se está correto ANTES de salvar. Só depois de ele confirmar, chame registrar_consumo "
                "de novo com os MESMOS itens/sobras e confirmado=true."
            ),
        }
        return anexar_ao_resultado(resultado, _nota_de_incerteza(q))

    # Confirmado: antes de gravar, checa a cobertura. O cálculo é sem efeito
    # colateral, então custa uma chamada a mais só no caminho de escrita.
    try:
        conferencia = _qualidade(go_api.calcular_consumo(itens))
    except Exception:
        conferencia = Qualidade()

    if conferencia.tudo_ignorado:
        # Gravar aqui produziria um registro de 0 kcal: desvio máximo na
        # pontuação e índice de resto sem sentido. Isso é dado corrompido, não
        # dado impreciso — e, uma vez gravado, não há como desfazer.
        _logar_nao_resolvidos(conferencia)
        return (
            "Não reconheci nenhum dos itens informados ("
            + ", ".join(sorted(set(conferencia.ignorados)))
            + "), então NÃO salvei nada — salvar daria 0 kcal e estragaria a pontuação. "
            "Peça ao usuário para descrever os alimentos de forma mais simples "
            "(ex.: 'frango', 'arroz', 'feijão') e refaça a prévia."
        )

    try:
        registro = go_api.registrar_consumo(ctx.unidade_id, itens, ctx.usuario_id, sobras)
    except Exception:
        return "Não foi possível registrar o consumo agora."

    q = _qualidade(registro.get("consumido") or {}, registro.get("resto") or {})
    _registrar_qualidade(q)
    return anexar_ao_resultado(registro, _nota_de_incerteza(q))


# Fuso do refeitório: "hoje" e "amanhã" são do ponto de vista de quem está na
# fila, não do relógio UTC do servidor.
_TZ = ZoneInfo("America/Sao_Paulo")


def _hoje_local() -> date:
    return datetime.now(_TZ).date()


def _resolver_dia(texto: str) -> date | None:
    """Converte 'hoje', 'amanha' ou uma data ISO em data-calendário local."""
    t = filters.normalizar(texto or "").strip()
    if not t:
        return None
    if t in ("hoje",):
        return _hoje_local()
    if t in ("amanha", "amanhã"):
        return _hoje_local() + timedelta(days=1)
    try:
        return date.fromisoformat(t)
    except ValueError:
        return None


def _segunda_da_semana(d: date) -> date:
    return d - timedelta(days=d.weekday())


@tool
@observado
def cardapio_da_semana(inicio: str = "", data_alvo: str = "") -> dict | str:
    """Cardápio da SEMANA da unidade atual. Use quando o usuário perguntar sobre outros
    dias ("o que tem amanhã/na quarta?", "qual o cardápio da semana?").

    PREFIRA `data_alvo`: o dia que o usuário quer ver ("amanha", "hoje" ou data ISO).
    A semana que CONTÉM esse dia é escolhida automaticamente — necessário porque
    "amanhã" num domingo cai na semana seguinte, e pedir a semana atual devolveria
    dias que já passaram.

    `inicio` = segunda-feira em ISO, só se você já souber a semana exata; vazio e sem
    `data_alvo` usa a semana atual.
    Retorna {inicio, dias: [{data, dia_semana, pratos: [{nome, categoria}]}]}."""
    ctx = current_context()

    if not inicio and data_alvo:
        alvo = _resolver_dia(data_alvo)
        if alvo:
            inicio = _segunda_da_semana(alvo).isoformat()

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
@observado
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
