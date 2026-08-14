"""Filtro de escopo em duas camadas: keywords (instantâneo) → LLM classificador (fallback).

Limite honesto: keywords não bloqueiam prompt injection — quem quer contornar
inclui uma palavra do domínio. O fast-path serve para LATÊNCIA (aprovar sem LLM o
que é claramente do domínio); a defesa real contra injection é o escopo das tools
(dados só da unidade/usuário da sessão). Por isso a lista contém APENAS termos
específicos do domínio — palavras genéricas ("tem", "qual", "hoje", "valor")
davam passe-livre a qualquer frase e tornavam o classificador letra morta.
"""

import os
import unicodedata

from langchain_ollama import ChatOllama

from app import config
from app.agent.prompts import SYSTEM_GUARDRAIL

_KEYWORDS_BASE = {
    "cardapio", "menu", "comer", "comida", "almoco", "jantar", "refeicao", "refeicoes",
    "prato", "pratos", "vegano", "vegetariano", "celiaco", "gluten", "lactose",
    "alergia", "alergico", "alergica", "intolerante", "intolerancia", "restricao",
    "proteina", "proteico", "caloria", "calorias", "carboidrato", "carb", "gordura",
    "saudavel", "nutricao", "nutricional",
    "comi", "consumi", "consumo", "comendo", "almocei", "jantei", "porcao", "concha",
    "amendoim", "soja", "peixe", "frango", "salada", "sopa",
    "low carb", "fit", "diet", "dieta", "lia",
    "recomenda", "recomendacao", "sugere", "sugestao", "indica", "indicacao",
    "ingrediente", "ingredientes", "contem",
    "diferenca", "comparar", "comparacao",
    # Gamificação e desperdício (registro de consumo/sobras):
    "pontuacao", "ranking", "streak", "sobrou", "sobras", "desperdicio",
    "prato limpo",
}

# Continuações curtas (≤4 palavras, TODAS deste conjunto, só com histórico):
# aqui palavras genéricas são seguras — não há espaço para instrução maliciosa.
_CONTINUACAO = {"ok", "obrigado", "obrigada", "valeu", "sim", "nao", "claro",
                "perfeito", "legal", "show", "blz", "beleza", "uhum", "isso",
                "quero", "vamos", "bora", "qual", "tem", "tudo", "tambem",
                "outro", "outra", "mais", "menos", "esse", "essa", "esses", "aquele",
                "e", "hoje", "amanha"}

_LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower().strip()
_OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
_OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
_ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5")

# Tipo amplo: pode ser ChatOllama ou ChatAnthropic. Importa lazy para não exigir
# o pacote do provider que não está em uso.
_classificador = None


def _get_classificador():
    global _classificador
    if _classificador is not None:
        return _classificador

    if _LLM_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic

        _classificador = ChatAnthropic(
            model=_ANTHROPIC_MODEL,
            max_tokens=4,
            temperature=0,
            timeout=config.LLM_TIMEOUT_SECONDS,
            max_retries=config.LLM_MAX_RETRIES,
        )
    else:
        _classificador = ChatOllama(
            model=_OLLAMA_MODEL,
            base_url=_OLLAMA_BASE_URL,
            temperature=0,
            num_predict=4,
            # Mesma janela do agent — evita o Ollama subir runner extra com
            # n_ctx diferente, fragmentando memória e duplicando KV cache.
            num_ctx=config.OLLAMA_NUM_CTX,
            # Mesmo keep_alive — para o classificador não causar descarga do modelo.
            keep_alive="30m",
        )
    return _classificador


def _normalizar(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return s.lower().strip()


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
