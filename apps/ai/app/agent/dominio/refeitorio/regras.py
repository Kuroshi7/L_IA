"""As regras de validação deste domínio.

Cada uma detecta deterministicamente um jeito de a resposta estar errada apesar
de o prompt proibir. Prompt não garante nada sozinho — estas quatro são a rede.

Todas são LOG-ONLY por padrão (ver `config.VALIDACAO_BLOQUEANTE`). Promover uma
delas a bloqueante exige antes medir o falso positivo nos logs: R2 depende de o
modelo seguir o FORMATO do prompt (o llama3.2 nem sempre segue) e R3 quebra em
aritmética legítima, como somar as kcal de duas porções.
"""

import re

from app.agent.dominio.refeitorio.filters import normalizar
from app.agent.motor.registry import CATALOGO, nomes_com_capacidade
from app.agent.motor.validacao import Achado

# A Lia ASSUMINDO uma escolha. Basta o verbo para a regra valer.
_VERBO_DE_RECOMENDACAO = re.compile(r"\b(recomendo|recomendacao|sugiro|sugestao|indico)\b")

# Menção ao cardápio. Sozinha não basta: "posso te ajudar com o cardápio de hoje"
# é OFERTA, não afirmação de conteúdo — e acusar oferta gerava falso positivo em
# toda saudação. Só conta quando vem junto com um item citado.
_AFIRMA_CARDAPIO = re.compile(
    r"\b(cardapio de hoje|cardapio do dia|opcao de hoje|opcoes de hoje|prato do dia)\b"
)

# O FORMATO do SYSTEM_AGENT manda o nome do prato vir em **negrito**. R2 se
# ancora nesse contrato que o prompt já impõe, em vez de tentar adivinhar quais
# palavras da frase são nome de prato.
_NEGRITO = re.compile(r"\*\*(.+?)\*\*")

# Rótulos que também aparecem em negrito e não são nome de prato.
_ROTULOS = {
    "nutricao", "porcao sugerida", "cardapio de hoje", "recomendacao",
    "cardapio", "hoje", "dica", "atencao", "observacao", "total",
}

# O modelo usa negrito para MUITO mais que nome de prato: títulos de seção,
# rótulos, datas e frases inteiras. Medido em turnos reais, tratar todo negrito
# como nome de prato acusava coisas como "recomendação para você", "235 kcal" e
# "segunda-feira (17/08)". Estes filtros existem para a regra ter precisão
# suficiente para alguém olhar o log; sem eles ela vira ruído ignorado.
_MAX_PALAVRAS_NOME = 5
_PONTUACAO_DE_FRASE = ("?", "!", ";", ":")

# Classe fechada de palavras funcionais. Nome de prato em português começa por
# substantivo ("Frango grelhado"), nunca por determinante ou quantificador —
# então "duas opções veganas" e "a melhor escolha" são prosa em negrito, não
# item do cardápio. É critério linguístico, não lista de termos do domínio.
_INICIO_DE_PROSA = {
    "um", "uma", "uns", "umas", "o", "a", "os", "as", "dois", "duas", "tres", "três",
    "meu", "minha", "seu", "sua", "esse", "essa", "este", "esta", "aquele", "aquela",
    "alguns", "algumas", "muitos", "muitas", "mais", "menos", "todos", "todas",
    "qualquer", "cada", "nosso", "nossa", "outro", "outra", "melhor", "pior",
    # Preposições: "para você", "com salada", "sem gluten" também são prosa.
    "para", "pra", "com", "sem", "de", "do", "da", "em", "no", "na", "por", "ao", "aos",
}


def _parece_nome_de_item(bruto: str, seguinte: str) -> bool:
    nome = bruto.strip()
    if not nome:
        return False
    # Negrito seguido de ":" é título de seção ("**Recomendação para você:**").
    if nome.endswith(":") or seguinte.startswith(":"):
        return False
    if any(c in nome for c in _PONTUACAO_DE_FRASE):
        return False
    # Número no meio é rótulo ou data, não nome ("235 kcal", "segunda-feira (17/08)").
    if any(c.isdigit() for c in nome):
        return False
    palavras = normalizar(nome).split()
    if len(palavras) > _MAX_PALAVRAS_NOME:
        return False
    if palavras and palavras[0] in _INICIO_DE_PROSA:
        return False
    return True

_NUMERO_COM_UNIDADE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kcal|g\b)", re.IGNORECASE)

# Palavras com que a resposta reconhece que não sabe. Se nenhuma aparecer quando
# houve item ignorado, a Lia apresentou um total incompleto como final.
_RESSALVAS = ("nao reconheci", "nao encontrei", "nao entrou", "nao entraram",
              "aproximad", "nao identifiquei", "confirma", "confere")


def resposta_recomenda(resposta: str) -> bool:
    """True se a resposta assume uma escolha ou afirma o conteúdo do cardápio.

    Oferta de ajuda ("posso te mostrar o cardápio de hoje") NÃO conta: sem verbo
    de recomendação e sem item citado, não há o que ter sido inventado.
    """
    norm = normalizar(resposta)
    if _VERBO_DE_RECOMENDACAO.search(norm):
        return True
    return bool(_AFIRMA_CARDAPIO.search(norm)) and bool(_itens_citados(resposta))


def _itens_citados(resposta: str) -> list[str]:
    citados = []
    for m in _NEGRITO.finditer(resposta):
        bruto = m.group(1)
        seguinte = resposta[m.end():m.end() + 2]
        if not _parece_nome_de_item(bruto, seguinte):
            continue
        nome = normalizar(bruto).strip(" :*-")
        if not nome or nome in _ROTULOS:
            continue
        citados.append(nome)
    return citados


def _casa_com_algum(nome: str, conhecidos) -> bool:
    if nome in conhecidos:
        return True
    # O modelo abrevia ("Frango grelhado com ervas" → "Frango grelhado"). Aceita
    # quando um contém o outro, ou quando os tokens do citado cabem no conhecido.
    tokens = set(nome.split())
    for conhecido in conhecidos:
        if nome in conhecido or conhecido in nome:
            return True
        if tokens and tokens <= set(conhecido.split()):
            return True
    return False


# --- R1 ----------------------------------------------------------------------

def _sem_tool_de_catalogo(registro):
    nomes_catalogo = nomes_com_capacidade(registro, CATALOGO)

    def regra(a: Achado) -> str | None:
        if not resposta_recomenda(a.resposta):
            return None
        if set(a.tools_chamadas) & nomes_catalogo:
            return None
        return "resposta recomenda/afirma cardápio sem nenhuma tool de cardápio no turno"

    return regra


# --- R2 ----------------------------------------------------------------------

def _prato_fora_do_cardapio(a: Achado) -> str | None:
    obs = a.observacoes
    if obs is None or not obs.itens_conhecidos:
        return None  # nada foi lido no turno; R1 cobre esse caso
    # Um termo que apareceu em QUALQUER retorno de tool não foi inventado — o
    # modelo leu de lá. É o caso de **lactose** (alérgeno) ou **proteína**
    # (categoria), que não são nomes de prato mas vieram do dado.
    vistos = getattr(obs, "termos_vistos", set())
    inventados = [
        n for n in _itens_citados(a.resposta)
        if n not in vistos and not _casa_com_algum(n, obs.itens_conhecidos)
    ]
    if not inventados:
        return None
    return f"pratos citados que nenhuma tool retornou: {inventados}"


# --- R3 ----------------------------------------------------------------------

# Somar as kcal dos pratos recomendados é aritmética LEGÍTIMA e esperada
# ("110 + 95 + 30 = 235 kcal no total"). Sem isto a regra acusava o total de
# toda recomendação combinada. Combinações de 2 e 3 cobrem o prato montado sem
# explodir: o teto evita custo quadrático quando o turno expôs muitos valores.
_MAX_VALORES_PARA_SOMA = 16


def _valores_aceitaveis(expostos) -> set[float]:
    valores = {v for v in expostos if v}
    if len(valores) > _MAX_VALORES_PARA_SOMA:
        return valores
    lista = sorted(valores)
    aceitos = set(valores)
    for i, a in enumerate(lista):
        for j, b in enumerate(lista[i + 1:], start=i + 1):
            aceitos.add(a + b)
            for c in lista[j + 1:]:
                aceitos.add(a + b + c)
    return aceitos



def _numero_nao_exposto(a: Achado) -> str | None:
    obs = a.observacoes
    if obs is None:
        return None
    # Só pula quando o turno não trouxe NADA estruturado — caso do RAG, que
    # devolve prosa e pode legitimamente conter números que a regra não tem como
    # conferir. Se alguma tool trouxe itens mas nenhum número (é o que
    # `listar_pratos_do_dia` faz: só id/nome/categoria), citar kcal é inventar —
    # e é exatamente por isso que itens_conhecidos e valores_expostos são
    # colhidos separadamente.
    if not obs.itens_conhecidos and not obs.valores_expostos:
        return None
    aceitos = _valores_aceitaveis(obs.valores_expostos)

    fora = []
    for bruto, _unidade in _NUMERO_COM_UNIDADE.findall(a.resposta):
        valor = float(bruto.replace(",", "."))
        # Tolerância de arredondamento: 182.4 vira "182 kcal" legitimamente.
        if any(abs(valor - v) <= max(1.0, abs(v) * 0.02) for v in aceitos):
            continue
        fora.append(valor)
    if not fora:
        return None
    return f"números citados que nenhuma tool expôs: {fora}"


# --- R4 ----------------------------------------------------------------------

def _total_incompleto_sem_ressalva(a: Achado) -> str | None:
    obs = a.observacoes
    if obs is None or not obs.avisos:
        return None
    if not any(v in normalizar(a.resposta) for v in _RESSALVAS):
        return "houve item não reconhecido no turno e a resposta não ressalvou a incerteza"
    return None


def construir(registro):
    """As regras deste domínio, na ordem de confiança (R1 é a mais precisa)."""
    return (
        ("R1-sem-tool-de-catalogo", _sem_tool_de_catalogo(registro)),
        ("R2-prato-fora-do-cardapio", _prato_fora_do_cardapio),
        ("R3-numero-nao-exposto", _numero_nao_exposto),
        ("R4-incompleto-sem-ressalva", _total_incompleto_sem_ressalva),
    )
