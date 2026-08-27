"""Meta nutricional → prato montado em porções.

Existe por causa de uma conversa real (27/08/2026): a pessoa disse "preciso todo
dia de uns 22g de proteina animal e vegetal, uns 40g de carboidrato no minimo" e
perguntou "quais medidas coloco no meu prato". Nunca foi respondida. A única
fonte de meta era `meu_perfil`, que exige `usuario_id` — e ela estava anônima.

Duas decisões estão codificadas aqui, e as duas são de produto:

1. META DITA VALE COMO META SALVA. `combinar` deixa a meta da CONVERSA vencer
   campo a campo e usa o perfil só para preencher buraco. Perfil MELHORA a
   recomendação (lembra entre visitas); nunca HABILITA. Sem isso, quem não tem
   cadastro continua sem resposta.

2. A ARITMÉTICA É NOSSA, NÃO DO MODELO. Esta base já mediu 0 de 3 duas vezes ao
   delegar conta ao modelo (ver `_incoerencia` e `_divergencia_de_procedencia` em
   tools.py). Somar macro de porção fracionada é pior que os dois casos: são
   dezenas de multiplicações. Aqui o número sai calculado e a nota manda não
   recalcular.

Módulo PURO de propósito: sem HTTP, sem `RequestContext`, sem cache de turno. É o
que permite testar a decisão inteira offline — quem precisa do cardápio e do
perfil é a tool em tools.py, que fica sendo uma casca fina.
"""

import re
from dataclasses import dataclass, field

from app.agent.dominio.refeitorio.filters import normalizar

# Os macros que o cardápio realmente carrega (API Go, `Alimento`). Sódio, fibra e
# vitamina NÃO existem no dado — a regra 6d do system prompt já manda dizer que
# não temos, e aqui simplesmente não há como mirar neles.
MACROS = ("proteinas_g", "carboidratos_g", "calorias")

NOME_DO_MACRO = {
    "proteinas_g": "proteína",
    "carboidratos_g": "carboidrato",
    "calorias": "caloria",
}

UNIDADE_DO_MACRO = {"proteinas_g": "g", "carboidratos_g": "g", "calorias": "kcal"}

# Quanto da meta DIÁRIA cai no almoço. Espelha `FracaoRefeicaoAlmoco` em
# apps/api/internal/domain/gamificacao.go:10, que é quem pontua o consumo.
#
# Trade-off assumido: duplicar a constante é aceitar duas fontes da verdade — a
# classe de bug do IA-20 (o mesmo prato saindo com dois valores). O conserto de
# verdade é o Go expor `meta_kcal_refeicao` no `PerfilNutricional`; até lá, a
# constante fica em UM lugar deste lado, com teste travando o valor, para que
# recomendar e pontuar não discordem sem ninguém perceber.
FRACAO_DA_REFEICAO = 0.35

# Uma bandeja de self-service comporta poucas porções. Sem teto, o guloso abaixo
# empilha comida até bater qualquer meta — e responder "coma 4 conchas de arroz"
# é pior do que dizer honestamente que o cardápio de hoje não chega lá.
TETO_POR_PRATO = 2.0
TETO_TOTAL_PORCOES = 5.0

# A pessoa monta o prato com concha e pegador; meia porção ela consegue servir,
# um terço não.
PASSO = 0.5

# "uns 22g" é aproximado: 20 g resolve o pedido dela. "40g no mínimo" é piso e
# não admite folga. Por isso a distinção `piso` existe — ela muda o que conta
# como meta atingida e muda a frase que a Lia diz.
FOLGA_DO_APROXIMADO = 0.9


@dataclass(frozen=True)
class Alvo:
    """Um número de meta, com a procedência e a natureza preservadas.

    `piso` distingue "pelo menos 40g" de "uns 22g"; `origem` é o que permite a
    Lia dizer "como você me falou" em vez de "segundo seu cadastro" — e é a
    única forma de a resposta ficar honesta para quem não tem cadastro nenhum.
    """

    valor: float
    piso: bool = False
    origem: str = "conversa"

    @property
    def efetivo(self) -> float:
        """O que conta como atingido. Piso exige o número cheio; alvo aproximado
        aceita a folga — insistir em cravar 22,0 g faria a Lia empilhar porção
        atrás de uma precisão que a pessoa nem pediu."""
        return self.valor if self.piso else self.valor * FOLGA_DO_APROXIMADO


@dataclass(frozen=True)
class Meta:
    proteinas_g: Alvo | None = None
    carboidratos_g: Alvo | None = None
    calorias: Alvo | None = None

    def alvos(self) -> dict[str, Alvo]:
        return {m: a for m in MACROS if (a := getattr(self, m)) is not None}

    def vazia(self) -> bool:
        return not self.alvos()

    @staticmethod
    def de_argumentos(proteinas_g: float = 0, carboidratos_g: float = 0, calorias: float = 0) -> "Meta":
        """Meta como o modelo a passa: os números que a pessoa disse na conversa.

        Zero significa "não informado", e não "meta zero" — é o default que
        sobrevive a modelo pequeno, que preenche argumento faltante com 0 muito
        mais consistentemente do que com `null`.
        """
        def alvo(v) -> Alvo | None:
            v = float(v or 0)
            return Alvo(v, origem="conversa") if v > 0 else None

        return Meta(alvo(proteinas_g), alvo(carboidratos_g), alvo(calorias))


def meta_do_perfil(perfil: dict | None) -> Meta:
    """O que o perfil salvo sabe hoje: só a meta calórica DIÁRIA.

    Não há campo de proteína nem de carboidrato em `PerfilNutricional`
    (apps/api/internal/domain/types.go) — ou seja, mesmo um usuário logado com
    perfil completo não tinha como responder ao pedido do baseline. Por isso o
    perfil entra como complemento, nunca como pré-requisito.
    """
    if not perfil:
        return Meta()
    diaria = perfil.get("meta_calorica_kcal")
    if not diaria:
        return Meta()
    return Meta(calorias=Alvo(round(float(diaria) * FRACAO_DA_REFEICAO, 1), origem="perfil"))


def combinar(dita: Meta, salva: Meta) -> Meta:
    """A meta dita agora vence a salva, campo a campo.

    É a regra de produto escrita em código: quem acabou de dizer "hoje quero 22g
    de proteína" está corrigindo o cadastro, não pedindo para ser contrariado
    por ele. E o campo que ela NÃO disse continua vindo do perfil — é aí que o
    cadastro melhora a resposta sem ser condição para ela existir.
    """
    return Meta(**{m: getattr(dita, m) or getattr(salva, m) for m in MACROS})


# --- leitura da meta dita em português ---------------------------------------

_MACRO_POR_TERMO = {
    "proteina": "proteinas_g", "proteinas": "proteinas_g", "ptn": "proteinas_g",
    "carboidrato": "carboidratos_g", "carboidratos": "carboidratos_g",
    "carbo": "carboidratos_g", "carbos": "carboidratos_g",
    "caloria": "calorias", "calorias": "calorias", "kcal": "calorias", "cal": "calorias",
}
_TERMOS = "|".join(sorted(_MACRO_POR_TERMO, key=len, reverse=True))

# A unidade é um conjunto FECHADO. É ela que separa "22 g de proteína" de
# "22 pontos" e de "40 anos": qualquer palavra fora desta lista entre o número e
# o macro derruba o casamento. Sem isso o parser vira gerador de falso positivo.
_UNIDADE = r"(?:g|gr|gramas?|kcal|cal|calorias?)"

_NUMERO = r"\d+(?:[.,]\d+)*"
_NUMERO_ANTES = re.compile(
    rf"({_NUMERO})\s*{_UNIDADE}?\s*(?:de\s+)?({_TERMOS})\b"
)
_MACRO_ANTES = re.compile(
    rf"\b({_TERMOS})\b\s*(?:diaria|diario|por dia)?\s*[:=]?\s*({_NUMERO})\s*{_UNIDADE}?"
)

_MILHAR = re.compile(r"\d{1,3}(?:\.\d{3})+")


def _para_numero(bruto: str) -> float:
    """Número como brasileiro escreve. "1.800 kcal" é mil e oitocentos, não 1,8 —
    e essa confusão sozinha erraria a meta calórica por um fator de mil."""
    if "," in bruto:
        return float(bruto.replace(".", "").replace(",", "."))
    if _MILHAR.fullmatch(bruto):
        return float(bruto.replace(".", ""))
    return float(bruto)


# Quem está declarando um ALVO fala de necessidade, não de fato consumado.
_INTENCAO_DE_META = re.compile(
    r"\b(preciso|precisava|necessito|quero|queria|gostaria|meta|objetivo|alvo|"
    r"minimo|maximo|pelo menos|ao menos|bater|atingir|chegar a|ingerir|consumir|"
    r"tenho que|devo)\b"
)

# Quem está DESCREVENDO um prato ou o que já comeu não está declarando meta.
# Sem esta guarda, "esse prato tem 228 kcal" viraria alvo calórico.
_DESCRICAO = re.compile(r"\b(tem|tinha|contem|possui|leva|comi|comeu|comemos|almocei)\b")

_PISO = re.compile(
    r"\b(no minimo|pelo menos|ao menos|minimo de|nao menos que|acima de|a partir de)\b"
)

# Vírgula e ponto separam orações, MENOS entre dígitos: "1,5 g de proteína" é um
# número só. Sem as duas guardas, "quero 1,5 g de proteína" virava a oração
# "5 g de proteína" e a meta saía 3x maior do que a pessoa pediu.
_FIM_DE_ORACAO = re.compile(r"(?<!\d)[,.](?!\d)|[;!?\n]")


def ler_meta(texto: str) -> Meta:
    """Extrai a meta que a pessoa disse por escrito.

    REDE, não fonte primária: a fonte primária continua sendo o argumento que o
    modelo passa para a tool, porque ele entende a frase melhor que qualquer
    regex. Isto aqui existe para o caso em que ele não passa — e para poder
    decidir, sem chamar o modelo, se a conversa declarou uma meta.

    O risco todo é falso positivo: número em português é ambíguo ("40 anos",
    "2 conchas", "22 pontos"). Três travas contra isso: unidade de um conjunto
    fechado colada ao macro, oração com intenção de meta, e oração descritiva
    ("esse prato TEM 228 kcal") desqualificada.
    """
    t = normalizar(texto or "")
    if not t:
        return Meta()

    achados: dict[str, Alvo] = {}
    houve_intencao = False

    for oracao in _FIM_DE_ORACAO.split(t):
        if not oracao.strip():
            continue
        descreve = bool(_DESCRICAO.search(oracao))
        propria = bool(_INTENCAO_DE_META.search(oracao))
        houve_intencao = houve_intencao or propria
        # A oração herda a intenção da anterior ("preciso de uns 22g de proteína,
        # uns 40g de carbo"): a segunda metade da frase real do usuário não repete
        # o verbo. Só herda quando ela própria não está descrevendo nada.
        if descreve or not (propria or houve_intencao):
            continue
        piso = bool(_PISO.search(oracao))
        for regex, ordem in ((_NUMERO_ANTES, "numero"), (_MACRO_ANTES, "macro")):
            for a, b in regex.findall(oracao):
                bruto, termo = (a, b) if ordem == "numero" else (b, a)
                macro = _MACRO_POR_TERMO[termo]
                valor = _para_numero(bruto)
                # Zero não é meta, é ruído ("0 g de gordura no rótulo"): aceitá-lo
                # faria a nota anunciar um alvo que a pessoa nunca pediu.
                if macro in achados or valor <= 0:
                    continue  # primeira menção manda; a segunda costuma ser reformulação
                achados[macro] = Alvo(valor, piso=piso, origem="conversa")

    return Meta(**achados)


# --- composição do prato ------------------------------------------------------

def _valor(prato: dict, macro: str) -> float:
    return float(prato.get(macro) or 0)


def _teto_do_prato(prato: dict, teto: float) -> float:
    """A proteína do dia é 1 porção por pessoa — regra do refeitório, não do
    modelo. Estava só no system prompt (regra 6) e agora é trava: recomendar
    duas porções dela é recomendar algo que a fila não vai servir."""
    return min(teto, 1.0) if prato.get("is_proteina_do_dia") else teto


def _deficit(totais: dict[str, float], alvos: dict[str, Alvo]) -> float:
    """Falta relativa somada. Relativa porque 10 g faltando de proteína pesa muito
    mais que 10 kcal faltando — sem normalizar, a caloria dominaria a escolha."""
    return sum(
        max(0.0, a.efetivo - totais.get(m, 0.0)) / a.efetivo
        for m, a in alvos.items()
        if a.efetivo > 0
    )


@dataclass
class Composicao:
    itens: list[dict] = field(default_factory=list)
    totais: dict[str, float] = field(default_factory=dict)
    atingiu: dict[str, bool] = field(default_factory=dict)
    meta: Meta = field(default_factory=Meta)
    candidatos: list[dict] = field(default_factory=list)

    # Os tetos com que ESTA composição foi montada. Guardados porque o "máximo do
    # cardápio" que vai para a nota precisa ser calculado com eles: anunciado com
    # 1 porção por prato enquanto o prato foi montado com 2, o número sai MENOR
    # que o prato servido, e a mesma resposta afirma duas coisas incompatíveis —
    # a classe de bug do IA-20 que o cabeçalho deste módulo cita.
    teto_porcoes: float = 0.0
    teto_total: float = 0.0

    # Quantos pratos o dia tinha ANTES de qualquer filtro, e quantos saíram por
    # conflito com o perfil. É o que permite a nota distinguir fracassos que
    # pedem frases opostas: cardápio não publicado, tudo excluído por segurança,
    # e nada que ajude na meta.
    #
    # `total_do_dia` é None quando ninguém informou, e tem que ser: `montar` só
    # enxerga os SOBREVIVENTES do filtro do chamador, então lista vazia aqui
    # tanto pode ser "a nutricionista não publicou" quanto "publicou, e nada
    # passou pelo que a pessoa não come" — fracassos com conselhos opostos. Quem
    # sabe a diferença é quem leu o cardápio; quem não sabe, não informa, e a
    # nota não afirma nenhum dos dois.
    total_do_dia: int | None = None
    excluidos_por_conflito: int = 0

    def vazia(self) -> bool:
        return not self.itens

    def maximo_do_cardapio(self) -> dict[str, float]:
        """O teto de hoje sob os MESMOS limites que montaram este prato."""
        return maximo_alcancavel(self.candidatos, self.teto_porcoes, self.teto_total)

    def para_tool(self) -> dict:
        """Payload da tool. Os números saem daqui calculados de propósito: além de
        pouparem a conta do modelo, viram `valores_expostos` no motor de
        observação — e a R3 (número não exposto) para de acusar o total certo."""
        resultado = {
            "composicao": self.itens,
            "totais": self.totais,
            "atingiu": self.atingiu,
        }
        if self.itens and not all(self.atingiu.values()):
            # O máximo alcançável entra no payload, e não só na nota, porque a
            # Lia vai citar esse número — e número citado precisa ter sido exposto.
            resultado["maximo_no_cardapio"] = self.maximo_do_cardapio()
        return resultado


def montar(
    pratos: list[dict],
    meta: Meta,
    teto_porcoes: float = TETO_POR_PRATO,
    teto_total: float = TETO_TOTAL_PORCOES,
    total_do_dia: int | None = None,
) -> Composicao:
    """Monta o prato desta refeição mirando a meta, em passos de meia porção.

    Guloso, não ótimo — e de propósito. O ótimo exigiria programação inteira para
    ganhar frações de grama num domínio onde o usuário serve com concha; o guloso
    é explicável em uma frase ("a cada passo, o que mais reduz o que falta") e
    roda em microssegundos dentro de um turno de 60s.

    Determinismo é requisito, não detalhe: o desempate é estável (mais contribui
    no macro mais deficitário, depois nome), senão a mesma pergunta devolveria
    pratos diferentes a cada turno e o produto pareceria instável.

    `total_do_dia` é o tamanho do cardápio ANTES do filtro do chamador. Só serve
    para a nota escolher a frase certa quando não sobra nada (ver
    `nota_para_o_modelo`); omitir é seguro e faz a nota não afirmar por que
    faltou.
    """
    alvos = meta.alvos()
    # Prato sem nome fica de fora: a Lia não tem como recomendá-lo pelo nome
    # exato, e nome que nenhuma tool expôs é o que a R2 acusa como inventado.
    candidatos = sorted(
        (p for p in pratos if p.get("nome") and not p.get("conflita_com_perfil")),
        key=lambda p: normalizar(p["nome"]),
    )
    contexto = {
        "teto_porcoes": teto_porcoes,
        "teto_total": teto_total,
        "total_do_dia": total_do_dia,
        "excluidos_por_conflito": sum(1 for p in pratos if p.get("conflita_com_perfil")),
    }
    if not alvos or not candidatos:
        # Sem alvo não se inventa alvo: prescrever quantidade é ato de
        # nutricionista, e a Lia não prescreve (regra 6c).
        return Composicao(meta=meta, candidatos=candidatos, **contexto)

    porcoes: dict[int, float] = {}
    totais = {m: 0.0 for m in MACROS}
    usado = 0.0

    while usado + PASSO <= teto_total:
        atual = _deficit(totais, alvos)
        if atual <= 0:
            break
        # Macro mais deficitário agora: é o critério de desempate que evita
        # escolher o prato calórico quando o que falta é proteína.
        faltando = max(
            alvos, key=lambda m: max(0.0, alvos[m].efetivo - totais[m]) / (alvos[m].efetivo or 1)
        )
        melhor = None
        for i, prato in enumerate(candidatos):
            if porcoes.get(i, 0.0) + PASSO > _teto_do_prato(prato, teto_porcoes):
                continue
            novos = {m: totais[m] + _valor(prato, m) * PASSO for m in MACROS}
            ganho = atual - _deficit(novos, alvos)
            if ganho <= 0:
                continue
            chave = (ganho, _valor(prato, faltando), -i)
            if melhor is None or chave > melhor[0]:
                melhor = (chave, i, novos)
        if melhor is None:
            break  # nenhum prato do dia reduz o que falta; o cardápio chegou ao teto dele
        _, i, novos = melhor
        porcoes[i] = porcoes.get(i, 0.0) + PASSO
        totais = novos
        usado += PASSO

    itens = [
        {
            "nome": candidatos[i]["nome"],
            "prato_id": candidatos[i].get("id"),
            "porcoes": porcoes[i],
            **{m: round(_valor(candidatos[i], m) * porcoes[i], 2) for m in MACROS},
        }
        for i in sorted(porcoes, key=lambda i: normalizar(candidatos[i]["nome"]))
    ]
    return Composicao(
        itens=itens,
        totais={m: round(totais[m], 2) for m in MACROS},
        atingiu={m: totais[m] + 1e-9 >= a.efetivo for m, a in alvos.items()},
        meta=meta,
        candidatos=candidatos,
        **contexto,
    )


def maximo_alcancavel(
    pratos: list[dict],
    teto_porcoes: float = 1.0,
    teto_total: float | None = None,
) -> dict[str, float]:
    """O teto do cardápio de hoje sob os tetos dados.

    É o número que transforma "parece que não está funcionando" em "hoje o
    cardápio chega a 18,5 g de proteína sem carne vermelha" — a diferença entre
    culpar o mecanismo e informar a pessoa.

    `teto_total` existe porque o número é ANUNCIADO como máximo, e um máximo que
    o prato servido supera não é máximo: `montar` limita a bandeja, e calcular o
    teto sem esse limite produzia um número maior que a meta que a nota, na mesma
    frase, declarava inalcançável. Quem chama de dentro do módulo passa os mesmos
    tetos da composição (ver `Composicao.maximo_do_cardapio`).

    Com teto de bandeja, o máximo de um macro é encher primeiro as porções mais
    ricas nele — mochila fracionária, exata e determinística, não a soma cega.
    """
    elegiveis = [p for p in pratos if not p.get("conflita_com_perfil")]
    limites = [(p, _teto_do_prato(p, teto_porcoes)) for p in elegiveis]

    maximos = {}
    for macro in MACROS:
        # Desempate pelo nome, como em `montar`: sem ele o mesmo cardápio em
        # outra ordem devolveria outro número quando o teto da bandeja corta.
        ordem = sorted(limites, key=lambda pt: (-_valor(pt[0], macro), normalizar(pt[0].get("nome") or "")))
        sobra = float("inf") if teto_total is None else teto_total
        total = 0.0
        for prato, teto in ordem:
            if sobra <= 0:
                break
            usar = min(teto, sobra)
            total += _valor(prato, macro) * usar
            sobra -= usar
        maximos[macro] = round(total, 2)
    return maximos


# --- a nota que vai junto do resultado ----------------------------------------

def _numero(valor: float, macro: str) -> str:
    texto = f"{valor:.0f}" if macro == "calorias" else f"{valor:.1f}".replace(".", ",")
    return f"{texto} {UNIDADE_DO_MACRO[macro]}"


def _como_a_pessoa_pediu(macro: str, alvo: Alvo) -> str:
    quanto = "pelo menos " if alvo.piso else "por volta de "
    de_onde = "que você me disse" if alvo.origem == "conversa" else "do seu perfil"
    return f"{quanto}{_numero(alvo.valor, macro)} de {NOME_DO_MACRO[macro]} ({de_onde})"


def nota_para_o_modelo(composicao: Composicao, meta: Meta, todos: list[dict] | None = None) -> str:
    """Instrução colada ao resultado — o último lugar do contexto antes da resposta.

    Escrita para ser PARAFRASEADA, no mesmo espírito de `conflitos_com_perfil`:
    nada aqui pode virar frase de mecanismo na boca da Lia. No baseline ela disse
    ao cliente "o sistema está muito rigoroso" e "parece que não está
    funcionando" — duas vezes. O que a pessoa precisa ouvir é o que o cardápio de
    hoje tem, não como o mecanismo se comporta.
    """
    if meta.vazia():
        return (
            "A pessoa não disse nenhum número de meta e não há meta no perfil dela. "
            "NÃO invente um alvo e não monte prato por conta própria: pergunte, em uma "
            "frase simples, quanto ela quer de proteína, de carboidrato ou de calorias "
            "nesta refeição. Você não prescreve dieta."
        )

    pedido = "; ".join(_como_a_pessoa_pediu(m, a) for m, a in meta.alvos().items())

    if composicao.vazia():
        # QUATRO causas, quatro frases: elas mandam a pessoa fazer coisas
        # opostas, e a frase errada é pior que nenhuma.
        if composicao.total_do_dia == 0:
            # Cardápio não publicado. Espelha `listar_pratos_do_dia` e
            # `filtrar_pratos`, que já tratam este caso antes de tudo: culpar as
            # restrições da pessoa por um cadastro que não foi feito é mentira, e
            # "ofereça mostrar o cardápio inteiro" seria convite a citar prato de
            # memória — que é o que as outras duas proíbem em voz alta.
            return (
                "Nenhum prato está cadastrado para hoje. NÃO sugira nem cite nenhum "
                "prato — nem de memória, nem 'o que costuma ter'. Diga que o cardápio "
                "ainda não foi publicado e ofereça ver outro dia."
            )
        if not composicao.candidatos and composicao.excluidos_por_conflito:
            # O que tirou os pratos foi o aviso que veio com cada um deles, e na
            # maioria dos casos ele é alergia. Pedir para "flexibilizar" aqui é
            # convidar a pessoa a abrir mão de uma alergia — o movimento contrário
            # a toda a assimetria de `filters.py`.
            return (
                f"Meta considerada: {pedido}. Nenhum prato de hoje é indicado para esta "
                "pessoa: cada um veio com o aviso do porquê. NÃO peça para ela abrir mão "
                "disso nem tente contornar. Diga, com as palavras dela, o que hoje não dá, "
                "e ofereça ver outro dia. Não sugira nada que não esteja no cardápio."
            )
        falta = (
            "Nenhum prato do cardápio de hoje sobrou depois do que a pessoa não come. "
            "Diga isso com as palavras dela ('hoje o cardápio não tem nada sem X') e "
            "pergunte o que dá para flexibilizar."
            if not composicao.candidatos else
            "Nenhum prato do cardápio de hoje ajuda a chegar nessa meta. Diga o que o "
            "cardápio tem hoje e pergunte se ela quer rever o número."
        )
        return (
            f"Meta considerada: {pedido}. {falta} Ofereça mostrar o cardápio inteiro e "
            "não sugira nada que não esteja nele."
        )

    partes = [
        f"Prato montado para a meta: {pedido}.",
        "As porções e os totais já estão calculados aqui — apresente exatamente estes "
        "números e NÃO refaça a conta.",
        # O usuário do baseline disse "todo dia"; o refeitório serve uma refeição.
        # Calar sobre a premissa faria a Lia parecer estar prescrevendo o dia inteiro.
        "Deixe claro, em uma frase, que esta conta é do prato DESTA refeição, não do dia inteiro.",
        # O pedido literal foi "medidas". Não temos peso de porção nem equivalência em
        # concha por prato: fingir a tradução seria inventar número.
        "As quantidades estão em PORÇÕES do self-service (o que cabe numa concha ou num "
        "pegador de servir); se a pessoa pediu em medida caseira, diga que está em porções.",
    ]

    faltantes = [m for m, ok in composicao.atingiu.items() if not ok]
    if faltantes:
        teto = composicao.maximo_do_cardapio()
        chegou = ", ".join(f"{_numero(teto[m], m)} de {NOME_DO_MACRO[m]}" for m in faltantes)
        partes.append(
            f"O cardápio de hoje não alcança a meta: mesmo enchendo o prato com tudo que "
            f"ela pode comer, dá no máximo {chegou}. Diga esse número à pessoa, com "
            "naturalidade, e ofereça completar amanhã ou ver outro dia. Nunca comente o "
            "funcionamento interno — fale do cardápio, que é o que faltou."
        )
    if todos and len(todos) > len(composicao.itens):
        partes.append("Mencione que há outras opções no cardápio, sem enumerar todas.")
    return " ".join(partes)
