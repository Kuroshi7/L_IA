"""Tools LangChain expostas ao agente.

Os dados vêm da API interna do serviço Go (fonte da verdade), sempre filtrados
pela UNIDADE do contexto da requisição. Args usam CSV string (mais robusto para
LLMs pequenos). A filtragem por restrição/alergia é determinística em Python.
"""

import json as _json
import logging
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import Literal

from langchain_core.tools import tool

from app.agent.dominio.refeitorio import filters
from app.agent.context import current_context
from app.agent.motor.observacao import cache_do_turno, observado
from app.agent.motor.reminders import anexar_ao_resultado
from app.agent.motor import relogio
from app.clients import go_api
from app.rag import retriever
from app.agent.motor.tools import ErroDeTool

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
# Estado/saída estruturada do fluxo conversacional. Estas chaves atravessam a
# fronteira pelo ResultadoDeTurno; o motor não precisa conhecer o conteúdo.
CACHE_ACAO_PENDENTE = "acao_pendente"
CACHE_LIMPAR_ACAO_PENDENTE = "limpar_acao_pendente"
CACHE_EXPERIENCIA = "experiencia"
CACHE_RESPOSTA_DETERMINISTICA = "resposta_deterministica"


def _guardar_fluxo(*, acao=None, experiencia=None, resposta=None, limpar=False) -> None:
    cache = cache_do_turno()
    if cache is None:
        return
    if acao is not None:
        cache[CACHE_ACAO_PENDENTE] = acao
    if experiencia is not None:
        cache[CACHE_EXPERIENCIA] = experiencia
    if resposta is not None:
        cache[CACHE_RESPOSTA_DETERMINISTICA] = resposta
    if limpar:
        cache[CACHE_LIMPAR_ACAO_PENDENTE] = True


def _cartao_prato(prato: dict) -> dict:
    """Recorte factual exibido pelo front; nenhum texto do modelo entra aqui."""
    return {
        "id": prato.get("id"),
        "nome": prato.get("nome"),
        "categoria": prato.get("categoria") or "",
        "calorias": prato.get("calorias"),
        "proteinas_g": prato.get("proteinas_g"),
        "carboidratos_g": prato.get("carboidratos_g"),
        "gorduras_g": prato.get("gorduras_g"),
        "ingredientes": list(prato.get("ingredientes") or []),
        "is_proteina_do_dia": bool(prato.get("is_proteina_do_dia")),
        "conflita_com_perfil": list(prato.get("conflita_com_perfil") or []),
    }


def _guardar_pratos(pratos: list[dict], tipo: str) -> None:
    seguros = [p for p in pratos if not p.get("conflita_com_perfil")]
    exibidos = seguros[:3] if tipo == "recomendacoes" else pratos
    _guardar_fluxo(experiencia={
        "tipo": tipo,
        "titulo": "Opções compatíveis" if tipo == "recomendacoes" else "Cardápio consultado",
        "pratos": [_cartao_prato(p) for p in exibidos],
        "fonte": "Cardápio da unidade",
    })

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


def _divergencia_de_procedencia(consumido: dict) -> str:
    """IA-20: o mesmo prato saindo com dois valores na mesma conversa.

    A recomendação mostra o kcal que a nutricionista declarou para o prato; o
    registro calcula pela medida caseira que a pessoa informou. Divergir é
    legítimo — "1 filé" não é a porção padrão do cardápio —, mas apresentar os
    dois números sem explicar faz a pessoa achar que o sistema erra.

    Comparação aritmética, não julgamento do modelo: mesma razão de _incoerencia.
    O limiar de 25% deixa passar arredondamento e pega diferença que a pessoa nota.
    """
    avisos = []
    for item in consumido.get("itens") or []:
        declarada = item.get("kcal_declarada_cardapio")
        calculada = float(item.get("kcal") or 0)
        if not declarada or calculada <= 0:
            continue
        declarada = float(declarada)
        if abs(calculada - declarada) / declarada <= 0.25:
            continue
        avisos.append(
            f"{item.get('alimento_resolvido') or item.get('entrada', {}).get('alimento')}: "
            f"{calculada:.0f} kcal pela medida informada, contra {declarada:.0f} kcal da "
            "porção padrão do cardápio"
        )
    if not avisos:
        return ""
    return (
        "PROCEDÊNCIA DIFERENTE — " + "; ".join(avisos) + ". "
        "Se você já citou o valor do cardápio nesta conversa, diga que este é o cálculo da "
        "porção que a pessoa informou, e por isso difere. NÃO apresente os dois números como "
        "se um deles estivesse errado."
    )


def _incoerencia(consumido: dict, resto: dict) -> str:
    """Sobra maior que o consumo é impossível, e é aritmética — não opinião.

    Pedir ao modelo que "perceba" isso é gastar atenção com o que uma
    comparação resolve. Medido em 0 de 3 enquanto dependia dele.

    Não bloqueia: a pessoa pode ter se enganado na medida, e travar o registro
    por isso seria pior que registrar com ressalva.
    """
    c = float(consumido.get("gramas_totais") or 0)
    r = float(resto.get("gramas_totais") or 0)
    if r <= c or c <= 0:
        return ""
    return (
        f"ATENÇÃO: a sobra informada ({r:.0f} g) é MAIOR que o consumo ({c:.0f} g), o que não "
        "é possível. Antes de registrar, confirme com o usuário o que ele comeu e o que sobrou "
        "— provavelmente uma das medidas saiu trocada."
    )


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
    vocabulario = _vocabulario_de_restricoes(pratos)
    anotados = []
    for p in pratos:
        motivos = filters.conflitos_com_perfil(p, perfil, vocabulario)
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


def _vocabulario_de_restricoes(pratos: list[dict]) -> list[str]:
    """Os rótulos de restrição que ESTE cardápio declara.

    Nada de constante: o vocabulário é DADO, não código. Uma unidade cadastra
    "sem lactose/vegetariano", outra "low carb/proteico" — e amanhã, por tenant,
    a lista muda de novo. Uma tabela fixa aqui envelheceria no primeiro cliente.

    `nao_indicado_para` entra na união porque é o MESMO namespace de
    `restricoes_atendidas`. Sem ele, num dia em que nenhum prato é vegetariano
    mas um está marcado `nao_indicado_para=['vegetariano']`, "vegetariano" seria
    tratado como termo desconhecido — e o roteamento devolveria ao modelo
    justamente o prato proibido.

    Deduplica por `normalizar`, mas devolve a grafia que a nutricionista
    cadastrou: este texto vai para o modelo, e ele repete o que lê.
    """
    vistos: set[str] = set()
    vocabulario: list[str] = []
    for p in pratos:
        declarados = list(p.get("restricoes_atendidas") or []) + list(p.get("nao_indicado_para") or [])
        for rotulo in declarados:
            chave = filters.normalizar(rotulo or "")
            if not chave or chave in vistos:
                continue
            vistos.add(chave)
            vocabulario.append(rotulo)
    return vocabulario


def _fora_do_vocabulario(termos: list[str], vocabulario: list[str]) -> list[str]:
    """Quais dos termos pedidos este filtro NÃO sabe aplicar.

    Pergunta ao PRÓPRIO `prato_atende_restricao`, com um prato-sonda sintético,
    em vez de comparar strings normalizadas. É o que faz as equivalências de
    `filters` ('celiaco' → 'sem gluten') continuarem valendo de graça: uma
    comparação literal passaria a rotear 'celiaco' em vez de filtrar, e a
    barreira determinística do celíaco viraria decisão do modelo. Copiar a
    tabela de equivalências para cá criaria duas verdades, que divergem na
    primeira equivalência nova.
    """
    return [termo for termo in termos if not filters.restricao_verificavel(termo, vocabulario)]


@tool
@observado
def listar_pratos_do_dia(dia: str = "hoje") -> dict:
    """Lista TODOS os pratos do cardápio do dia da unidade atual. `dia` aceita 'hoje'
    ou data ISO '2026-05-28'. Use SEMPRE quando o usuário pedir o cardápio — mostre a
    lista completa antes de recomendar.

    Retorna {total, pratos: [{id, nome, categoria, conflita_com_perfil?}], nota_do_sistema}.
    `total` é quantos pratos existem: sua resposta precisa citar todos eles."""
    pratos = [filters.resumir(p) for p in _pratos(dia)]
    _guardar_pratos(pratos, "cardapio")

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
        f"São {len(pratos)} pratos hoje. Se pediram o CARDÁPIO, liste os {len(pratos)} com o "
        "nome exato. Se pediram uma RECOMENDAÇÃO, escolha e justifique — e diga que há outras "
        "opções, sem precisar enumerar todas."
    )
    conflitantes = [p["nome"] for p in pratos if p.get("conflita_com_perfil")]
    if conflitantes:
        # `conflita_com_perfil` já vem escrito na voz certa ("você informou alergia a X —
        # e este prato leva X"): é material para a Lia parafrasear, não rótulo de sistema.
        nota += (
            f" ATENÇÃO: {conflitantes} não são indicados para esta pessoa. O campo "
            "`conflita_com_perfil` traz o motivo já na forma de falar com ela. Nunca os "
            "recomende; se ela perguntar sobre um deles, explique devolvendo a informação "
            "que ela mesma deu, com o motivo concreto — sem proibir."
        )
    return {"total": len(pratos), "pratos": pratos, "nota_do_sistema": nota}


@tool
@observado
def filtrar_pratos(restricoes: str = "", alergias: str = "", preferencias: str = "", dia: str = "hoje") -> list[dict] | dict | str:
    """Filtra os pratos do dia (da unidade atual) que atendem TODAS as restrições, são
    seguros para TODAS as alergias e combinam com as preferências. Use ao recomendar.

    Os dois campos de restrição NÃO são simétricos:
    - `restricoes` = vocabulário FECHADO (CSV): só os rótulos que o cardápio declara
      ("vegetariano", "sem lactose", "sem gluten"). Pedido ABERTO ("sem carne vermelha",
      "sem fritura") NÃO vai aqui — decida você, pelos `ingredientes` que vêm no retorno.
    - `preferencias` = vocabulário ABERTO (CSV): busca nos `ingredientes`, para o que a
      pessoa QUER incluir (ex "frango,legumes").
    `alergias` CSV ex "peixe,lactose". `dia` "hoje" (default) ou data ISO.
    Retorna os pratos completos compatíveis."""
    rest, alerg, pref = _csv(restricoes), _csv(alergias), _csv(preferencias)
    pratos = _pratos(dia)

    if not pratos:
        # Cardápio não publicado é um fracasso DIFERENTE de "filtrei e nada
        # atende", e precisa vir antes de tudo: sem pratos o vocabulário é
        # vazio, todo termo pareceria desconhecido e o roteamento mandaria o
        # modelo escolher pelos ingredientes de uma lista que não existe.
        return {
            "pratos": [],
            "nota_do_sistema": (
                f"Nenhum prato cadastrado para '{dia or 'hoje'}'. NÃO sugira nem cite "
                "nenhum prato — nem de memória, nem 'o que costuma ter'. Diga que o "
                "cardápio ainda não foi publicado e ofereça consultar outro dia."
            ),
        }

    vocabulario = _vocabulario_de_restricoes(pratos)
    desconhecidas = _fora_do_vocabulario(rest, vocabulario)
    conhecidas = [r for r in rest if r not in desconhecidas]

    compativeis = [
        p for p in pratos
        if all(filters.prato_atende_restricao(p, r) for r in conhecidas)
        and filters.prato_seguro_para_alergias(p, alerg)
    ]
    # Preferência ORDENA, não elimina. "comida caseira" não é ingrediente de ficha
    # nenhuma, e como filtro zerava o cardápio: a tool dizia "nenhum prato atende" a
    # quem só tinha dito do que gosta (E2E 23/09, seu João). Se ao menos um prato casa,
    # fica só quem casa — é o pedido "quero frango"; se nenhum casa, a preferência não
    # tinha como ser checada e não pode custar o almoço.
    preferencia_sem_efeito: list[str] = []
    if pref and compativeis:
        preferidos = [p for p in compativeis if any(filters.prato_combina_preferencia(p, x) for x in pref)]
        if preferidos:
            compativeis = preferidos
        else:
            preferencia_sem_efeito = pref
    _guardar_pratos(compativeis, "recomendacoes")

    if not compativeis:
        # Regra inviolável 4. Devolver [] deixava o modelo livre para "ajudar"
        # inventando algo plausível; a instrução vai junto do resultado.
        #
        # Vem ANTES do roteamento de propósito, e continua honesto mesmo com
        # termo desconhecido na jogada: filtrar por um SUBCONJUNTO dos critérios
        # dá um superconjunto dos pratos: se nem o subconjunto sobrou nada,
        # o critério completo também não sobraria. Roteando aqui, a nota
        # mandaria o modelo decidir sobre uma lista vazia.
        return (
            "Nenhum prato do cardápio atende a esses critérios. NÃO sugira nada fora "
            "do cardápio nem force um prato que não atende. Diga isso ao usuário e "
            "pergunte se ele pode flexibilizar algum critério."
        )

    if preferencia_sem_efeito and not desconhecidas:
        return {
            "pratos": compativeis,
            "nota_do_sistema": (
                f"Nenhum prato cita '{', '.join(preferencia_sem_efeito)}' nos ingredientes, então "
                "estes são todos os que passaram nas restrições e alergias. Recomende entre eles "
                "normalmente; não diga que nenhum prato atende."
            ),
        }

    if desconhecidas:
        # O falso negativo que originou isto: 'sem carne vermelha' chegou no
        # campo fechado, não casou com rótulo nenhum e zerou o cardápio inteiro.
        # O tool então dizia "nenhum prato atende" com voz de autoridade, o
        # modelo obedecia — corretamente — e a conversa morria. Duas vezes
        # seguidas, e a Lia acabou culpando o sistema na frente do cliente.
        #
        # Em vez de mentir, o tool declara o próprio vocabulário e devolve a
        # decisão a quem sabe tomá-la. Os PRATOS vão junto da instrução, não só
        # ela: o orçamento é de poucas tool calls por turno, e obrigar mais uma
        # chamada só para ver `ingredientes` gasta o turno de novo. A assimetria
        # decidida se mantém — alergia segue determinística no código acima, e
        # `conflita_com_perfil` continua anotado; só a restrição ABERTA vai para
        # o modelo, com os ingredientes na mão.
        #
        # Duas frases diferentes para dois fracassos diferentes. Vocabulário
        # VAZIO não é "o termo é aberto": é a nutricionista que ainda não
        # classificou prato nenhum — o estado normal do dia 1 de uma unidade
        # nova, e o estado esperado com 300 lojas. Sem a distinção, a nota saía
        # com o parêntese literalmente vazio ("os rótulos que o cardápio declara
        # ()") e afirmava um material de decisão que não existe.
        declarado = (
            f"Este campo só filtra os rótulos que o cardápio declara ({', '.join(vocabulario)})."
            if vocabulario else
            "O cardápio de hoje não classificou prato nenhum, então não havia rótulo "
            "por onde filtrar."
        )
        termos = ", ".join(desconhecidas)
        nota = (
            f"NÃO filtrei por: {termos}. {declarado} Isso NÃO significa que nenhum prato "
            f"sirva — e também NÃO significa que estes {len(compativeis)} pratos atendam a "
            f"'{termos}': eles passaram pelos critérios que EU sei aplicar, e vêm com "
            "`ingredientes` para você olhar. Recomende só o que você consiga justificar "
            f"pelos ingredientes do prato, e NUNCA afirme que um prato atende '{termos}' se "
            "os ingredientes não mostrarem isso — quando não der para saber, diga o que o "
            "prato leva e deixe a pessoa decidir. Não repita esta consulta com o mesmo "
            "termo. Para o que a pessoa QUER incluir, use `preferencias`, que busca nos "
            "ingredientes. NUNCA diga ao usuário que a consulta falhou ou que o sistema "
            "está rigoroso: responda com o que dá para fazer."
        )
        # A lista roteada CONTÉM pratos conflitantes (é o que
        # `test_conflito_com_perfil_sobrevive_ao_roteamento` prova), e sem esta
        # frase a última mensagem do contexto dizia "escolha entre eles" sem
        # nunca mencionar o campo — contradizendo, da posição de maior
        # obediência, a regra 6b que está no topo do system. Mesmo texto de
        # `listar_pratos_do_dia`, de propósito: dois avisos diferentes para o
        # mesmo fato é como o modelo aprende a escolher qual obedecer.
        conflitantes = [p["nome"] for p in compativeis if p.get("conflita_com_perfil")]
        if conflitantes:
            nota += (
                f" ATENÇÃO: {conflitantes} não são indicados para esta pessoa. O campo "
                "`conflita_com_perfil` traz o motivo já na forma de falar com ela. Nunca os "
                "recomende; se ela perguntar sobre um deles, explique devolvendo a informação "
                "que ela mesma deu, com o motivo concreto — sem proibir."
            )
        return {
            "pratos": compativeis,
            "restricoes_aplicadas": conhecidas,
            "nao_filtrei_por": desconhecidas,
            "vocabulario_de_restricoes": vocabulario,
            "nota_do_sistema": nota,
        }
    return compativeis


_NOTA_DADO_AUSENTE = (
    "Esta ficha NÃO tem sódio/sal, açúcar, fibra nem modo de preparo. Se perguntarem, diga "
    "que você não tem esse dado e sugira perguntar à equipe do refeitório — não deduza pelos "
    "ingredientes nem pelo nome do prato."
)


@tool
@observado
def detalhar_prato(prato_id: int, dia: str = "hoje") -> dict | str:
    """Detalhes completos de um prato do cardápio do dia (ingredientes, alérgenos, nutrição)."""
    for p in _pratos(dia):
        if p["id"] == prato_id:
            # Regra 6d no system não bastou: no E2E de 23/09, com esta ficha na mão, a
            # Lia afirmou "a grelha não adiciona sódio" para um hipertenso. A nota
            # chega no fim do contexto, colada à pergunta.
            return {**p, "nota_do_sistema": _NOTA_DADO_AUSENTE}
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


def _numero(valor) -> str:
    n = float(valor or 0)
    return f"{n:.0f}" if n.is_integer() else f"{n:.1f}".replace(".", ",")


def _kcal(total: dict) -> float:
    return float(total.get("kcal") or total.get("kcal_total") or 0)


def _linha_item(item: dict) -> str:
    entrada = item.get("entrada") or {}
    quantidade = entrada.get("quantidade") or 1
    medida = entrada.get("medida") or item.get("porcao_resolvida") or "porção"
    nome = item.get("alimento_resolvido") or entrada.get("alimento") or "item"
    return f"- {_numero(quantidade)} {medida} de {nome} — {_numero(item.get('kcal'))} kcal"


def _texto_previa(previa: dict, q: Qualidade) -> str:
    consumido = previa.get("consumido") or {}
    resto = previa.get("resto") or {}
    linhas = ["Preparei a prévia — **nada foi salvo ainda**.", "", "Você comeu:"]
    linhas.extend(_linha_item(i) for i in (consumido.get("itens") or []))
    linhas.append(f"Total calculado: **{_numero(_kcal(consumido))} kcal**.")
    if resto:
        linhas.extend(["", "Sobrou no prato:"])
        linhas.extend(_linha_item(i) for i in (resto.get("itens") or []))
        linhas.append(f"Total das sobras: **{_numero(_kcal(resto))} kcal**.")
    else:
        linhas.extend(["", "Sobras: **nenhuma**."])
    if q.ignorados:
        linhas.append(
            "Não reconheci " + ", ".join(sorted(set(q.ignorados)))
            + "; esses itens ficaram fora do total."
        )
    elif q.imprecisos:
        linhas.append("Alguns valores são aproximados; deixei isso sinalizado no resumo.")
    linhas.extend(["", "Está correto? Confirme para eu registrar e calcular seus pontos."])
    return "\n".join(linhas)


def _texto_registro(registro: dict) -> str:
    consumido = registro.get("consumido") or {}
    pontos = registro.get("pontuacao") or {}
    gami = registro.get("gamificacao") or {}
    linhas = [
        "Registro confirmado ✓",
        f"- Consumo: **{_numero(_kcal(consumido))} kcal**",
        f"- Desperdício: **{_numero(registro.get('indice_resto_perc'))}%**",
    ]
    if pontos:
        linhas.append(f"- Pontos ganhos: **+{_numero(pontos.get('pontos'))}**")
    if gami:
        linhas.append(
            f"- Total: **{_numero(gami.get('pontos'))} pontos** · nível "
            f"{_numero(gami.get('nivel'))} · sequência de {_numero(gami.get('streak_dias'))} dia(s)"
        )
    if registro.get("pontuacao_pendente"):
        linhas.append("O consumo foi salvo, mas a pontuação ficou pendente porque o total está incompleto.")
    return "\n".join(linhas)


def pedir_sobras_consumo(itens: list[dict]) -> dict:
    acao = {"tipo": "consumo", "etapa": "aguardando_sobras", "itens": itens}
    resposta = (
        "Antes de calcular a prévia: **sobrou algo no prato?** "
        "Pode responder “não sobrou nada” ou dizer o alimento e a medida que ficou."
    )
    return {
        "resposta": resposta,
        "experiencia": {"tipo": "pergunta_sobras", "itens": itens},
        "acao_pendente": acao,
        "resultado_tool": {
            "aguardando_sobras": True,
            "instrucao": "Pergunte o que sobrou. Nada foi calculado nem salvo.",
        },
    }


def preparar_previa_consumo(itens: list[dict], sobras: list[dict]) -> dict:
    ctx = current_context()
    try:
        consumido = go_api.calcular_consumo(itens, ctx.unidade_id)
        resto = go_api.calcular_consumo(sobras, ctx.unidade_id) if sobras else {}
    except Exception:
        return {"erro": "Não foi possível calcular a prévia agora."}

    previa: dict = {"consumido": consumido}
    if sobras:
        previa["resto"] = resto
    q = _qualidade(consumido, resto)
    _registrar_qualidade(q)
    notas = [n for n in (
        _incoerencia(consumido, resto),
        _divergencia_de_procedencia(consumido),
        _nota_de_incerteza(q),
    ) if n]
    acao = {
        "tipo": "consumo", "etapa": "aguardando_confirmacao",
        "itens": itens, "sobras": sobras, "previa": previa,
    }
    resultado_tool = {
        "previa": previa,
        "instrucao": (
            "PRÉVIA — NADA FOI SALVO AINDA. O sistema guardou exatamente estes "
            "itens; a próxima confirmação persiste este payload, sem reinterpretá-lo."
        ),
    }
    return {
        "resposta": _texto_previa(previa, q),
        "experiencia": {
            "tipo": "consumo_previa", "consumido": consumido,
            "resto": resto, "pode_confirmar": not bool(_incoerencia(consumido, resto)),
        },
        "acao_pendente": acao,
        "resultado_tool": anexar_ao_resultado(resultado_tool, " ".join(notas)),
    }


def confirmar_consumo_pendente(acao: dict) -> dict:
    """Persiste SOMENTE o payload da prévia guardada na sessão."""
    if acao.get("tipo") != "consumo" or acao.get("etapa") != "aguardando_confirmacao":
        return {"erro": "Não há uma prévia de consumo pronta para confirmar."}
    itens = _parse_itens(acao.get("itens")) or []
    sobras = _parse_itens(acao.get("sobras")) or []
    ctx = current_context()

    try:
        conferencia = _qualidade(go_api.calcular_consumo(itens, ctx.unidade_id))
    except Exception:
        conferencia = Qualidade()
    if conferencia.tudo_ignorado:
        _logar_nao_resolvidos(conferencia)
        return {
            "resposta": (
                "Não reconheci nenhum dos itens da prévia, então **não salvei nada**. "
                "Descreva os alimentos de forma mais simples e eu preparo outra prévia."
            ),
            "experiencia": {"tipo": "consumo_erro", "motivo": "itens_nao_reconhecidos"},
            "limpar_acao_pendente": True,
            "resultado_tool": "Nenhum item reconhecido; nada foi salvo.",
        }

    try:
        registro = go_api.registrar_consumo(
            ctx.unidade_id, itens, ctx.usuario_id, sobras, session_id=ctx.session_id
        )
    except Exception:
        return {"erro": "Não foi possível registrar o consumo agora."}

    q = _qualidade(registro.get("consumido") or {}, registro.get("resto") or {})
    _registrar_qualidade(q)
    return {
        "resposta": _texto_registro(registro),
        "experiencia": {"tipo": "consumo_registrado", **registro},
        "limpar_acao_pendente": True,
        "resultado_tool": anexar_ao_resultado(registro, _nota_de_incerteza(q)),
    }


def _cachear_resultado_fluxo(resultado: dict) -> None:
    if resultado.get("erro"):
        _guardar_fluxo(resposta=resultado["erro"])
        return
    _guardar_fluxo(
        acao=resultado.get("acao_pendente"),
        experiencia=resultado.get("experiencia"),
        resposta=resultado.get("resposta"),
        limpar=bool(resultado.get("limpar_acao_pendente")),
    )


@tool
@observado
def registrar_consumo(
    itens: list[dict],
    sobras: list[dict] | None = None,
    sobras_informadas: bool = False,
    confirmado: bool = False,
) -> dict | str:
    """Conduz consumo em três estados: perguntar sobras → prévia → confirmar.

    `itens` e `sobras` usam {alimento, medida, quantidade}. Se a pessoa disser
    explicitamente que não sobrou nada, passe `sobras=[]` e
    `sobras_informadas=true`. Nunca use `confirmado=true` no mesmo turno do
    relato: confirmação só vale quando já existe prévia pendente na sessão.
    """
    itens = _parse_itens(itens)
    if not itens:
        return "Envie ao menos um item {alimento, medida, quantidade}."
    sobras_ausentes = sobras is None and not sobras_informadas
    sobras_parseadas = _parse_itens(sobras) if sobras is not None else []
    if sobras is not None and sobras_parseadas is None:
        return "Sobras precisam ser uma lista {alimento, medida, quantidade}."

    ctx = current_context()
    pendente = getattr(ctx, "acao_pendente", None) or {}

    # O modelo não tem autoridade para pular a prévia. Mesmo que envie
    # confirmado=true no primeiro relato, cai no fluxo normal.
    if confirmado and pendente.get("etapa") == "aguardando_confirmacao":
        resultado = confirmar_consumo_pendente(pendente)
        _cachear_resultado_fluxo(resultado)
        return resultado.get("resultado_tool") or resultado.get("erro")

    # Ao responder a pergunta de sobras, os itens consumidos vêm do estado, não
    # da reconstrução do modelo.
    if pendente.get("etapa") == "aguardando_sobras":
        itens = _parse_itens(pendente.get("itens")) or itens

    if sobras_ausentes:
        resultado = pedir_sobras_consumo(itens)
    else:
        resultado = preparar_previa_consumo(itens, sobras_parseadas or [])
    _cachear_resultado_fluxo(resultado)
    return resultado.get("resultado_tool") or resultado.get("erro")


# "hoje" e "amanhã" são do ponto de vista de quem está na fila, não do relógio
# UTC do servidor. O fuso vem de `motor/relogio.py` — mesma fonte que informa a
# data ao modelo. Duas contas de "hoje" em lugares diferentes divergem na virada
# do dia, e o bug só aparece à noite.
def _hoje_local() -> date:
    return relogio.hoje()


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
    resultado = {
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

    # A tool avisa quando a semana devolvida não é a de hoje.
    #
    # Foi por falta disto que uma resposta apresentou o cardápio de 28/05 como se
    # fosse o de hoje: sem cardápio publicado para hoje, o modelo chutou uma data
    # absoluta, caiu num resto de seed de três meses atrás e a tool entregou sem
    # dizer nada. `listar_pratos_do_dia` já se protege assim quando vem vazio —
    # é a mesma ideia, aplicada onde faltava.
    #
    # Não é validação de entrada (a data pedida é legítima, o gestor precisa
    # consultar semanas passadas). É contexto: o dado vai junto com o que ele
    # significa, para o modelo não poder confundir passado com hoje.
    inicio_ret = resultado.get("inicio")
    try:
        distancia = (date.fromisoformat(inicio_ret) - _segunda_da_semana(_hoje_local())).days // 7
    except (TypeError, ValueError):
        distancia = 0
    if distancia:
        quando = "passada" if distancia < 0 else "futura"
        resultado = anexar_ao_resultado(resultado, (
            f"ATENÇÃO: esta é uma semana {quando} ({abs(distancia)} semana(s) de distância "
            f"da semana atual), NÃO é o cardápio de hoje. Só apresente estes pratos se o "
            f"usuário tiver pedido explicitamente esse período, e diga de que dias eles são. "
            f"Se ele perguntou sobre hoje, o cardápio de hoje não está publicado."
        ))
    return resultado


# Espelha domain.PontosPorNivel (apps/api/internal/domain/gamificacao.go): nível = 1 + pontos/500.
_PONTOS_POR_NIVEL = 500


@tool
@observado
def meus_pontos() -> dict | str:
    """Pontuação de gamificação do usuário atual: pontos acumulados, nível, streak de
    dias registrando consumo, os últimos eventos, quanto falta para o próximo nível e a
    posição no ranking da unidade. Use quando perguntarem "quantos pontos eu tenho?",
    "qual meu nível?", "como subo de nível?", "quem está em primeiro?", "como funciona a pontuação?"."""
    ctx = current_context()
    if not ctx.usuario_id:
        return ("Usuário não identificado nesta sessão — para acumular pontos é preciso "
                "criar um perfil (no site) e conversar identificado.")
    try:
        estado = go_api.get_gamificacao(ctx.usuario_id)
    except Exception:
        return "Não foi possível carregar sua pontuação agora."

    pontos = int((estado.get("gamificacao") or {}).get("pontos") or 0)
    estado["pontos_para_proximo_nivel"] = _PONTOS_POR_NIVEL - pontos % _PONTOS_POR_NIVEL
    # Ranking: a Lia respondia "não tenho acesso" a "quem está em primeiro?", com a
    # tela de ranking no próprio app. Só o primeiro nome, como a tela mostra.
    try:
        ranking = go_api.get_ranking(ctx.unidade_id)
    except Exception:
        ranking = None
    if ranking is not None:
        posicao = next((i + 1 for i, r in enumerate(ranking) if r.get("usuario_id") == ctx.usuario_id), None)
        estado["ranking_da_unidade"] = {
            "sua_posicao": posicao,
            "participantes": len(ranking),
            "top3": [
                {"posicao": i + 1, "nome": (r.get("nome") or "").split(" ")[0], "pontos": r.get("pontos")}
                for i, r in enumerate(ranking[:3])
            ],
        }
    return estado


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


@tool
def resumo_de_desperdicio(de: str | None = None, ate: str | None = None) -> dict | str:
    """GESTÃO — agregado de desperdício da unidade num período (padrão: 14 dias).

    Use para perguntas de análise: quanto se desperdiça, quais pratos sobram
    mais, como evoluiu no período. Datas em AAAA-MM-DD.

    Devolve: total do período, série por dia e os alimentos mais desperdiçados.
    Os números vêm agregados do banco — NÃO recalcule nem some de cabeça, e não
    cite valor que não esteja aqui.
    """
    ctx = current_context()
    try:
        return go_api.resumo_desperdicio(ctx.unidade_id, de, ate)
    except Exception as e:
        raise ErroDeTool(
            "Não consegui consultar o resumo de desperdício agora. "
            "Diga isso e não estime números."
        ) from e
