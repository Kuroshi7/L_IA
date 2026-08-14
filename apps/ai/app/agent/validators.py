"""Pós-validação da resposta do agente (log-only, não bloqueia).

A regra inviolável nº 2 do prompt diz "sem tool = sem recomendação". O prompt não
garante nada sozinho; aqui detectamos deterministicamente o descumprimento mais
perigoso — a resposta RECOMENDA prato sem ter consultado o cardápio no turno —
que é o indicador mais barato de prato inventado (alucinação).

Hoje o resultado vai para o log (métrica de qualidade por sessão); quando houver
eval set rodando em CI, a mesma função vira gate de regressão.
"""

import logging
import re
import unicodedata

log = logging.getLogger("validators")

# Tools cujo retorno traz pratos do cardápio — se qualquer uma foi chamada no
# turno, a recomendação tem base real.
TOOLS_DE_CARDAPIO = {
    "listar_pratos_do_dia",
    "cardapio_da_semana",
    "filtrar_pratos",
    "detalhar_prato",
    "comparar_pratos",
}

# Sinais (em texto normalizado, sem acento) de que a resposta está recomendando
# ou afirmando conteúdo do cardápio.
_PADRAO_RECOMENDACAO = re.compile(
    r"\b(recomendo|sugiro|indico|cardapio de hoje|cardapio do dia|"
    r"opcao de hoje|opcoes de hoje|prato do dia)\b"
)


def _normalizar(texto: str) -> str:
    s = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return s.lower()


def resposta_recomenda(resposta: str) -> bool:
    """True se a resposta aparenta recomendar prato ou afirmar o cardápio."""
    return bool(_PADRAO_RECOMENDACAO.search(_normalizar(resposta)))


def verificar_resposta(resposta: str, tools_chamadas: list[str], session_id: str = "") -> bool:
    """Valida a resposta contra as tools chamadas no turno. Retorna True se ok.

    Violação detectada: recomendação/afirmação de cardápio sem NENHUMA tool de
    cardápio no turno. Loga em WARNING — é o sinal a alarmar em produção.
    """
    if not resposta_recomenda(resposta):
        return True
    if set(tools_chamadas) & TOOLS_DE_CARDAPIO:
        return True
    log.warning(
        "VALIDACAO | possivel alucinacao: resposta recomenda/afirma cardapio sem tool "
        "de cardapio no turno | session=%s | tools=%s | resposta=%r",
        session_id[:12], tools_chamadas, resposta[:200],
    )
    return False
