"""Filtro de escopo em duas camadas: keywords (instantâneo) → LLM classificador (fallback).

Duas decisões guiam esta lista:

1. Keywords não bloqueiam prompt injection — quem quer contornar inclui uma
   palavra do domínio. O fast-path serve para LATÊNCIA (aprovar sem LLM o que é
   claramente do domínio); a defesa real contra injection é o escopo das tools
   (dados só da unidade/usuário da sessão).
2. Por isso a lista contém termos ESPECÍFICOS do domínio (inclusive substantivos
   que carregam tráfego real: "pontos", "nivel", "meta", "registrar", "carne",
   "ovo", "leve", "sobra"), mas NÃO palavras puramente genéricas ("tem", "qual",
   "valor", "detalhe") que davam passe-livre a qualquer frase. Frases genuinamente
   ambíguas ("o que tem hoje?") caem no classificador — e, se ele falhar, o
   fail-OPEN em is_in_scope evita rejeitar a pergunta mais comum do produto.
"""

import logging


from app import config
from app.agent.dominio.refeitorio.filters import normalizar
from app.agent.dominio.refeitorio.prompts import SYSTEM_GUARDRAIL

log = logging.getLogger("agent")

_KEYWORDS_BASE = {
    "cardapio", "menu", "comer", "comida", "almoco", "jantar", "refeicao", "refeicoes",
    "prato", "pratos", "vegano", "vegetariano", "celiaco", "gluten", "lactose",
    "alergia", "alergico", "alergica", "intolerante", "intolerancia", "restricao",
    "proteina", "proteico", "caloria", "calorias", "carboidrato", "carb", "gordura",
    "saudavel", "leve", "nutricao", "nutricional",
    "comi", "consumi", "consumo", "comendo", "almocei", "jantei", "porcao", "concha",
    "amendoim", "soja", "peixe", "frango", "carne", "ovo", "salada", "sopa",
    "low carb", "fit", "diet", "dieta", "lia",
    "recomenda", "recomendacao", "sugere", "sugestao", "indica", "indicacao",
    "ingrediente", "ingredientes", "contem",
    "diferenca", "comparar", "comparacao",
    # Gamificação e desperdício (registro de consumo/sobras) — substantivos que
    # o próprio produto roteia para tools (meus_pontos, registrar_consumo):
    "ponto", "pontos", "pontuacao", "nivel", "meta", "ranking", "streak",
    "registrar", "registro", "sobra", "sobrou", "sobras", "deixei", "resto",
    "desperdicio", "prato limpo",
}

# Continuações curtas (≤4 palavras, TODAS deste conjunto, só com histórico):
# aqui palavras genéricas são seguras — não há espaço para instrução maliciosa.
_CONTINUACAO = {"ok", "obrigado", "obrigada", "valeu", "sim", "nao", "claro",
                "perfeito", "legal", "show", "blz", "beleza", "uhum", "isso",
                "quero", "vamos", "bora", "qual", "tem", "tudo", "tambem",
                "outro", "outra", "mais", "menos", "esse", "essa", "esses", "aquele",
                "e", "hoje", "amanha",
                # Artigos e demonstrativos: "e o outro?", "e a salada?" são
                # continuações legítimas e caíam no classificador (ou eram
                # barradas). Com ≤4 palavras e histórico, não há espaço para
                # instrução maliciosa aqui.
                "o", "a", "os", "as", "um", "uma", "isso", "esta", "estao", "tem",
                "qual", "quais", "quanto", "quantos", "como", "pode", "posso", "sim"}

# Tipo amplo: pode ser ChatOllama ou ChatAnthropic. Importa lazy para não exigir
# o pacote do provider que não está em uso. Config (provider/modelo/url) vem de
# app.config — fonte única, já com load_dotenv.
_classificador = None


def _get_classificador():
    """Classificador de escopo: temperatura zero e saída de 4 tokens — ele só
    responde sim ou não. Construído pela mesma fábrica do agente, para um
    provider novo valer nos dois sem edição em dois lugares."""
    global _classificador
    if _classificador is None:
        from app.agent.motor import provedores

        _classificador = provedores.construir(temperatura=0, max_tokens=4)
    return _classificador


def _bate_keyword(texto_norm: str) -> bool:
    palavras = set(texto_norm.replace("?", " ").replace("!", " ").replace(",", " ").split())
    return bool(palavras & _KEYWORDS_BASE)


def _eh_continuacao_curta(texto_norm: str) -> bool:
    palavras = texto_norm.replace("?", "").replace("!", "").replace(".", "").replace(",", "").split()
    if len(palavras) > 4:
        return False
    return all(p in _CONTINUACAO for p in palavras)


def is_in_scope(texto: str, tem_historico: bool = False) -> bool:
    """True se a mensagem está no escopo do assistente. Não-bloqueante: só consulta o LLM
    classificador se as heurísticas locais não decidirem."""
    if not texto or not texto.strip():
        return False

    texto_norm = normalizar(texto)

    if _bate_keyword(texto_norm):
        return True

    if tem_historico and _eh_continuacao_curta(texto_norm):
        return True

    try:
        resp = _get_classificador().invoke([
            ("system", SYSTEM_GUARDRAIL),
            ("human", texto),
        ])
        veredicto = normalizar(getattr(resp, "content", str(resp)))
    except Exception as e:
        # Fail-OPEN: se o classificador está fora ou lento, rejeitar deixaria o
        # usuário sem resposta para a pergunta mais comum ("o que tem hoje?"). O
        # agente tem instrução de escopo no próprio prompt, e a defesa real contra
        # abuso é o escopo das tools, não este guardrail.
        log.warning("classificador indisponível (%s) — deixando passar", type(e).__name__)
        return True

    if veredicto.startswith("nao"):
        return False
    if veredicto.startswith("sim"):
        return True

    # Resposta que não dá para interpretar — vazia, em outro idioma, ou de um
    # modelo que gastou os poucos tokens de saída raciocinando. É a MESMA
    # situação do erro acima: não temos veredicto. Tratar como "não" bloqueava
    # o usuário em silêncio, e foi o que aconteceu ao trocar de provider.
    log.warning("classificador respondeu algo ininteligível (%r) — deixando passar", veredicto[:40])
    return True
