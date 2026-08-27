"""Filtragem determinística de pratos por restrição/alergia/preferência.

Opera sobre o shape de prato retornado pela API Go (nutrição em campos planos:
calorias, proteinas_g, carboidratos_g, gorduras_g). Garante que, ex., um
vegetariano nunca veja um prato com carne — a regra está no código, não no prompt.

Alergia é o único eixo deste arquivo que erra de propósito para um lado só. A
checagem cruza `alergenos` E `ingredientes`, porque `alergenos` sozinho não
descreve o prato: a maioria dos cadastros vem com ele vazio, e alergia a alho ou
a carne bovina nunca vira "alérgeno" na cabeça de quem preenche a ficha. E o
casamento é deliberadamente conservador: barrar um prato seguro custa uma opção a
menos no almoço, liberar um prato perigoso custa uma reação alérgica. Quem vier
afrouxar isto para "reduzir falso positivo" precisa decidir contra essa
assimetria, não sem ela.

Restrição e preferência não pagam esse preço — `prato_combina_preferencia` segue
com casamento por substring, e continua assim de propósito: ali o erro custa uma
sugestão morna, não uma ida ao hospital.
"""

import functools
import re
import unicodedata


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.lower().strip()


# Moldura de fala ("sou alérgico a…") e conectivos de nome composto ("creme DE
# leite"). Nenhum dos dois identifica comida, e deixá-los no conjunto faria a
# contenção de _casa() depender de como a pessoa escreveu a frase.
_RUIDO = frozenset({
    "de", "do", "da", "com", "e", "em", "sem", "a", "ao", "o", "os", "as",
    "alergico", "alergica", "alergia", "intolerante", "intolerancia", "tenho", "sou",
})


# Plurais que cortar um "s" final não resolve. Cortar o "s" e nada mais é o que
# faz o par singular/plural DEIXAR de casar quando a comparação é por palavra
# inteira: "nozes" virava "noze" e não encontrava "noz". Medido, era bloqueio
# perdido em castanha, noz, camarão, amendoim e pão — e a grafia que a
# nutricionista copia para a ficha é a do rótulo, que a ANVISA (RDC 26/2015)
# imprime no plural ("nozes", "castanhas", "amêndoas"), enquanto a pessoa digita
# o singular no perfil. É tabela de LÍNGUA, não de tenant: por isso vive aqui, e
# não no cadastro da unidade.
_PLURAIS = (
    ("oes", "ao"),   # camaroes -> camarao
    ("aes", "ao"),   # paes -> pao
    ("ais", "al"),   # cereais -> cereal
    ("eis", "el"),   # papeis -> papel
    ("ois", "ol"),   # lencois -> lencol
    ("zes", "z"),    # nozes -> noz
    ("res", "r"),    # acucares -> acucar
    ("ses", "s"),    # gases -> gas
    ("ns", "m"),     # amendoins -> amendoim
)


def _singular(palavra: str) -> str:
    """Forma canônica de uma palavra já normalizada.

    Não é um lematizador e não precisa ser: a MESMA função roda nos dois lados da
    comparação, então basta ser CONSISTENTE — errar de forma igual nos dois lados
    ainda casa. Palavra de até 3 letras fica intacta ("noz", "sal"): encurtar
    mais começa a confundir alimentos diferentes, e a comparação por palavra
    inteira existe justamente para isso não acontecer.
    """
    if len(palavra) <= 3:
        return palavra
    for sufixo, troca in _PLURAIS:
        if palavra.endswith(sufixo) and len(palavra) - len(sufixo) + len(troca) >= 3:
            return palavra[: -len(sufixo)] + troca
    if palavra.endswith("s") and not palavra.endswith("ss"):
        return palavra[:-1]
    return palavra


@functools.lru_cache(maxsize=2048)
def _tokens(texto: str) -> frozenset[str]:
    """Palavras que identificam comida dentro de um texto livre.

    Isto roda pratos × alergias × campos a cada turno; o cache existe porque o
    vocabulário se repete muito (os mesmos ~30 ingredientes da unidade, o mesmo
    perfil, a cada tool do turno).
    """
    palavras = []
    for bruto in re.split(r"[^a-z0-9]+", normalizar(texto)):
        # Plural: alergia a "ovo" TEM que barrar "ovos de codorna", e alergia a
        # "noz" TEM que barrar "nozes". Ovo de codorna é ovo — aqui o falso
        # negativo é a reação alérgica.
        bruto = _singular(bruto)
        if bruto and bruto not in _RUIDO:
            palavras.append(bruto)
    return frozenset(palavras)


# Termos que nomeiam um GRUPO de alimentos, e não um alimento. Existe porque o
# formulário do perfil oferece "frutos do mar" num clique, sob a promessa
# literal de que a Lia nunca sugere um prato com algo da lista — e "frutos do
# mar" não é palavra que apareça em ficha nenhuma: o que está escrito lá é
# "camarão", "lula", "peixe". Sem a expansão, o chip que o produto entrega
# pronto casa com NADA.
#
# Também é tabela de língua, não de tenant, e por isso não segue a regra dos
# rótulos de restrição (esses são dado por unidade, ver `_vocabulario_de_
# restricoes` em tools.py). Só o termo da PESSOA é expandido; o motivo do
# conflito continua citando o termo real do prato, então ela lê "você informou
# alergia a frutos do mar — e este prato leva camarão" e pode discordar com a
# informação na mão.
#
# Os grupos são DELIBERADAMENTE estreitos: colocar derivado aqui ("manteiga"
# dentro de "leite") produz acusação que a ficha do prato não sustenta, que é a
# mentira que `culpados_por_alergia` foi escrita para evitar.
_GRUPOS = {
    "frutos do mar": (
        "camarao", "lula", "polvo", "marisco", "mexilhao", "ostra", "vieira",
        "siri", "caranguejo", "lagosta", "peixe",
    ),
    "leite": ("lactose",),
    "lactose": ("leite",),
    "gluten": ("trigo", "cevada", "centeio", "malte"),
    "trigo": ("gluten",),
}

# Indexado pelo conjunto de tokens, e não pela string: assim "Frutos do Mar",
# "frutos do mar" e "sou alérgica a frutos do mar" caem todos na mesma entrada,
# porque o campo do perfil é texto livre.
_GRUPOS_POR_TOKENS = {_tokens(nome): membros for nome, membros in _GRUPOS.items()}


def _casa(termo_pessoa: str, termo_prato: str) -> bool:
    """O termo que a pessoa declarou acusa este termo do prato?

    Comparação por PALAVRA INTEIRA, e não substring. Substring é o que a versão
    antiga fazia e não sobrevive ao cruzamento com ingredientes: "sal" está
    dentro de "salmão" e de "salsinha", então alergia a salmão apagaria pratos
    que não têm peixe nenhum.

    Basta UMA palavra em comum. A versão anterior exigia contenção de conjuntos
    (um lado contido no outro) e era NÃO MONOTÔNICA — quanto mais específica a
    declaração, menos ela protegia: "leite" barrava o ingrediente "creme de
    leite", mas "leite de vaca" (a forma idiomática de declarar APLV, a alergia
    alimentar mais comum do país) não barrava nada, porque {leite, vaca} não
    contém nem está contido em {creme, leite}. O mesmo valia para "castanha de
    caju" × "castanha do pará". Punir a pessoa por ter sido mais precisa é o
    oposto da assimetria declarada no topo do arquivo.

    O preço é falso positivo em nome composto que compartilha a palavra genérica
    ("molho de soja" × "molho de tomate"). É o lado barato do erro: custa uma
    opção a menos, aparece nomeado no motivo do conflito (ver
    `conflitos_com_perfil`) e nunca libera prato perigoso.
    """
    da_pessoa, do_prato = _tokens(termo_pessoa), _tokens(termo_prato)
    if not da_pessoa or not do_prato:
        # Texto que reduz a conjunto vazio ("", "alergia a") casaria com tudo e
        # esvaziaria o cardápio inteiro.
        return False
    return bool(da_pessoa & do_prato)


_EQUIVALENCIAS = {
    "celiaco": "sem gluten",
    "intolerante a gluten": "sem gluten",
    "intolerante ao gluten": "sem gluten",
    "intolerante a lactose": "sem lactose",
    "sem leite": "sem lactose",
}


def prato_atende_restricao(prato: dict, restricao: str) -> bool:
    r = normalizar(restricao)
    nao_indicado = {normalizar(x) for x in prato.get("nao_indicado_para", [])}
    if r in nao_indicado:
        return False
    atendidas = {normalizar(x) for x in prato.get("restricoes_atendidas", [])}
    if r in atendidas:
        return True
    eq = _EQUIVALENCIAS.get(r)
    return bool(eq and eq in atendidas)


def culpados_por_alergia(prato: dict, alergias: list[str]) -> list[tuple[str, str]]:
    """Pares (alergia declarada, termo do prato que a acusa).

    Varre `alergenos` E `ingredientes`. Olhar só `alergenos` — o que este código
    fazia — declarava seguro todo prato de ficha incompleta: medido, um prato de
    ingredientes ["carne bovina", "cebola", "óleo"] com `alergenos` vazio passava
    para quem é alérgico a carne bovina, e o mesmo valia para qualquer alergia
    fora da lista clássica (alho, cebola, tomate).

    Devolve o PAR, e não um booleano, porque o motivo do conflito precisa citar o
    termo real: dizer "leva leite" num prato que leva leite de coco é mentira, e
    mentira sobre alergia queima a confiança exatamente onde ela é vital.
    """
    termos_do_prato = [*(prato.get("alergenos") or []), *(prato.get("ingredientes") or [])]
    culpados: list[tuple[str, str]] = []
    for alergia in alergias:
        # O termo cru continua valendo junto com a expansão do grupo: a ficha
        # pode trazer literalmente "frutos do mar" como ingrediente. O custo é
        # casar também "frutos vermelhos" pela palavra "fruto" — uma sobremesa a
        # menos, do lado barato da assimetria.
        #
        # O termo LITERAL varre o prato inteiro antes das expansões, e não a
        # cada termo do prato: é o que garante que o motivo comece pela causa
        # que a pessoa reconhece ("leva leite"), com o sinônimo técnico depois
        # ("leva leite, lactose") em vez de no lugar dela.
        for meu in (alergia, *_GRUPOS_POR_TOKENS.get(_tokens(alergia), ())):
            for termo in termos_do_prato:
                if (alergia, termo) not in culpados and _casa(meu, termo):
                    culpados.append((alergia, termo))
    return culpados


def prato_seguro_para_alergias(prato: dict, alergias: list[str]) -> bool:
    return not culpados_por_alergia(prato, alergias)


def alergia_verificavel(prato: dict) -> bool:
    """O prato tem ficha suficiente para "seguro" querer dizer alguma coisa.

    "Seguro" e "não sei" são coisas diferentes, mas a diferença NÃO entra no
    booleano acima de propósito. Se prato sem ficha virasse inseguro, ele sumiria
    de `filtrar_pratos` e a tool cairia no "nenhum prato atende a esses
    critérios" por falta de cadastro; e `conflitos_com_perfil` o anotaria, texto
    que a listagem apresenta ao modelo como "nunca os recomende". Punição forte
    demais para uma incerteza de preenchimento.

    Fica exposto para quem monta a resposta poder ressalvar em vez de esconder.
    """
    return bool(prato.get("ingredientes") or prato.get("alergenos"))


def prato_combina_preferencia(prato: dict, preferencia: str) -> bool:
    p = normalizar(preferencia)
    atendidas = {normalizar(x) for x in prato.get("restricoes_atendidas", [])}
    if p in atendidas:
        return True
    ingredientes = {normalizar(i) for i in prato.get("ingredientes", [])}
    return p in ingredientes or any(p in ing for ing in ingredientes)


def resumir(prato: dict) -> dict:
    """Versão enxuta para listagem. O aviso de conflito com o perfil SEMPRE
    acompanha — é a única informação da listagem que pode evitar um acidente."""
    resumo = {"id": prato["id"], "nome": prato["nome"], "categoria": prato.get("categoria", "")}
    if prato.get("conflita_com_perfil"):
        resumo["conflita_com_perfil"] = prato["conflita_com_perfil"]
    return resumo


def conflitos_com_perfil(prato: dict, perfil: dict | None) -> list[str]:
    """Por que este prato é inadequado para esta pessoa, na voz certa.

    Existe porque filtrar não bastou. `filtrar_pratos` já devolve só o que é
    seguro, mas o modelo às vezes recomenda a partir da lista crua — e o produto
    não pode esconder o prato, porque a pessoa tem o direito de saber o que está
    sendo servido.

    O texto é escrito para ser PARAFRASEADO pela Lia, e por isso já vem na
    posição de autoridade correta: quem declarou a alergia foi a pessoa, e o
    ingrediente é fato verificável do prato. O assistente não determina o que
    alguém pode comer — ele cruza as duas coisas e devolve o motivo.
    """
    if not perfil:
        return []

    motivos = []
    alergias = [a for a in (perfil.get("alergias") or []) if a]
    culpados = culpados_por_alergia(prato, alergias)
    if culpados:
        # Citar o termo que REALMENTE acusou (e não a lista de `alergenos`, que
        # costuma estar vazia) é o que torna o aperto honesto: quem lê "leva
        # leite de coco" discorda com a informação na mão, em vez de aceitar um
        # veto opaco. É a mesma doutrina do docstring: reportar, não proibir.
        declaradas = list(dict.fromkeys(a for a, _ in culpados))
        termos = list(dict.fromkeys(t for _, t in culpados))
        motivos.append(
            f"você informou alergia a {', '.join(declaradas)} — e este prato leva "
            f"{', '.join(termos)}"
        )

    for restricao in (perfil.get("restricoes") or []):
        if restricao and not prato_atende_restricao(prato, restricao):
            ingredientes = [i for i in (prato.get("ingredientes") or [])][:3]
            porque = f" — leva {', '.join(ingredientes)}" if ingredientes else ""
            motivos.append(f"você informou a restrição '{restricao}', e este prato não atende{porque}")

    return motivos
