"""Filtro de escopo em duas camadas: keywords (instantâneo) → LLM classificador (fallback)."""

import os
import unicodedata

from langchain_ollama import ChatOllama

from cardapio import vocabulario_dominio
from prompts import SYSTEM_GUARDRAIL

_KEYWORDS_BASE = {
    "cardapio", "menu", "comer", "comida", "almoco", "jantar", "refeicao", "refeicoes",
    "prato", "pratos", "vegano", "vegetariano", "celiaco", "gluten", "lactose",
    "alergia", "alergico", "alergica", "intolerante", "intolerancia", "restricao",
    "proteina", "proteico", "caloria", "calorias", "carboidrato", "carb", "gordura",
    "saudavel", "leve", "pesado", "gostoso", "saboroso", "nutricao", "nutricional",
    "amendoim", "soja", "ovo", "peixe", "carne", "frango", "salada", "sopa",
    "low carb", "fit", "diet", "dieta", "lia", "hoje", "amanha", "amanhã",
    "recomenda", "recomendacao", "sugere", "sugestao", "indica", "indicacao",
}

_CONTINUACAO = {"ok", "obrigado", "obrigada", "valeu", "sim", "nao", "claro",
                "perfeito", "legal", "show", "blz", "beleza", "uhum", "isso",
                "quero", "vamos", "bora", "qual", "tem", "tudo", "tambem",
                "outro", "outra", "mais", "menos", "esse", "essa", "esses", "aquele"}

_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

_classificador: ChatOllama | None = None


def _get_classificador() -> ChatOllama:
    global _classificador
    if _classificador is None:
        _classificador = ChatOllama(
            model=_OLLAMA_MODEL,
            base_url=_OLLAMA_BASE_URL,
            temperature=0,
            num_predict=4,
        )
    return _classificador


def _normalizar(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return s.lower().strip()


def _bate_keyword(texto_norm: str) -> bool:
    palavras = set(texto_norm.replace("?", " ").replace("!", " ").replace(",", " ").split())
    if palavras & _KEYWORDS_BASE:
        return True
    if palavras & vocabulario_dominio():
        return True
    return False


def _eh_continuacao_curta(texto_norm: str) -> bool:
    palavras = texto_norm.replace("?", "").replace("!", "").replace(".", "").split()
    if len(palavras) > 4:
        return False
    return all(p in _CONTINUACAO for p in palavras)


def is_in_scope(texto: str, tem_historico: bool = False) -> bool:
    """True se a mensagem está no escopo do assistente. Não-bloqueante: só consulta o LLM
    classificador se as heurísticas locais não decidirem."""
    if not texto or not texto.strip():
        return False

    texto_norm = _normalizar(texto)

    if _bate_keyword(texto_norm):
        return True

    if tem_historico and _eh_continuacao_curta(texto_norm):
        return True

    try:
        resp = _get_classificador().invoke([
            ("system", SYSTEM_GUARDRAIL),
            ("human", texto),
        ])
        veredicto = _normalizar(getattr(resp, "content", str(resp)))
        return veredicto.startswith("sim")
    except Exception:
        # Falha no Ollama: fail-open seria abrir brecha; preferimos fail-closed.
        return False
