"""Fachada de processamento de uma mensagem: guardrail → turno → resposta.

Esta é a única superfície de `app.agent` consumida de fora (worker, `/infer`,
Telegram) — e `app/channels/telegram.py` a chama POSICIONALMENTE, então a ordem
dos parâmetros é contrato, não só os nomes. Por isso a fachada não se move nem
muda de assinatura quando as camadas internas mudam; `deadline` entrou como
keyword-only justamente para não deslocar nada.

A memória de curto prazo (histórico) é fornecida pelo serviço Go a cada
requisição; este serviço é stateless quanto a sessão.
"""

import logging
import time

from app.agent.context import RequestContext, reset_context, set_context
from app.agent.dominio.refeitorio.perfil import PERFIL
from app.agent.dominio.refeitorio.perfil import prewarm  # noqa: F401 — reexport p/ o worker
from app.agent.dominio.refeitorio.tools import CACHE_APROXIMADOS, CACHE_NAO_RECONHECIDOS
from app.agent.motor import turn
from app.agent.motor.reminders import Gatilhos

log = logging.getLogger("chat")


def processar_mensagem(
    session_id: str,
    mensagem: str,
    unidade_id: int,
    usuario_id: int | None = None,
    historico: list[dict] | None = None,
    primeira_do_dia: bool = False,
    # Carimbado pela API Go a partir do X-Admin-Token validado. Chega até aqui
    # como dado do envelope; nenhum cliente escreve neste campo.
    is_admin: bool = False,
    *,
    deadline: float | None = None,
) -> dict:
    t0 = time.perf_counter()
    historico = historico or []
    log.info(
        "REQ START | session=%s | unidade=%s | msg=%r",
        session_id[:12], unidade_id, mensagem[:120],
    )

    if not PERFIL.esta_no_escopo(mensagem, len(historico) > 0):
        log.info("REQ END | fora de escopo")
        return {"resposta": PERFIL.resposta_fora_de_escopo, "fora_de_escopo": True}

    contexto = RequestContext(unidade_id=unidade_id, usuario_id=usuario_id, is_admin=is_admin)
    token = set_context(contexto)
    try:
        resultado = turn.executar_turno(
            PERFIL,
            mensagem,
            contexto=contexto,
            historico=historico,
            gatilhos=Gatilhos(primeira_interacao_do_dia=primeira_do_dia),
            prazo=deadline,
            session_id=session_id,
        )
    finally:
        reset_context(token)

    log.info(
        "REQ END | total=%.2fs | llm_calls=%s | resp_chars=%d | erro=%s",
        time.perf_counter() - t0, resultado.llm_calls, len(resultado.resposta), resultado.erro,
    )

    resposta = {"resposta": resultado.resposta, "fora_de_escopo": False}
    if resultado.erro:
        resposta["erro_interno"] = resultado.erro
    if confianca := _confianca(resultado):
        resposta["confianca"] = confianca
    return resposta


def _confianca(resultado) -> dict | None:
    """Sinal de incerteza para o cliente exibir.

    Omitido quando não há nada a relatar — o campo é opcional no contrato, então
    consumidores que ainda não o conhecem seguem funcionando. Só reportamos o
    que é acionável pelo usuário: os termos que ele escreveu e a base não
    reconheceu, porque a ação é reescrever o alimento de outro jeito."""
    cache = resultado.cache or {}
    nao_reconhecidos = list(cache.get(CACHE_NAO_RECONHECIDOS) or [])
    aproximados = list(cache.get(CACHE_APROXIMADOS) or [])
    if not nao_reconhecidos and not aproximados:
        return None
    return {
        # "parcial" = algo ficou de fora da conta; "aproximada" = tudo entrou,
        # mas com número que a base não garante. São coisas diferentes para
        # quem lê, e a segunda era invisível até aqui.
        "nivel": "parcial" if nao_reconhecidos else "aproximada",
        "nao_reconhecidos": nao_reconhecidos,
        "aproximados": aproximados,
    }
