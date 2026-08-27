"""Verificação de partida: o provedor responde e sabe chamar tool?

Sem isto o worker sobe, começa a consumir a fila e só descobre que o provedor
está inalcançável na primeira mensagem de um usuário real — respondendo "tive um
problema, tente de novo" a cada pergunta, para sempre. Foi o que aconteceu em
24/08/2026: `LLM_PROVIDER` não chegava ao container, o worker caía calado no
default e seis mensagens seguidas viraram erro. Nada no log de partida indicava
problema, porque para o worker não havia problema — havia configuração.

Falhar na partida troca isso por uma linha clara antes de qualquer usuário ser
afetado. É a diferença entre "o sistema está quebrado" e "o sistema não subiu".

**Tool calling é requisito, não detalhe.** Um agente sem tool não degrada com
elegância: ele alucina o dado que deveria ter buscado. Modelo pequeno ou versão
`:free` de roteador podem simplesmente não suportar — e o sintoma aparece como
resposta errada, não como erro. Testar na partida custa uma chamada.

Agnóstico de produto de propósito: a tool daqui é descartável, existe só para
ver se o protocolo funciona. O motor não conhece as tools de nenhum domínio.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.agent.motor.erros import ErroClassificado, classificar

log = logging.getLogger(__name__)

# Tool sem relação com domínio nenhum: o que se testa é o protocolo, não o
# conteúdo. Nome improvável de propósito, para não colidir com tool real.
_TOOL_DE_SONDA = {
    "type": "function",
    "function": {
        "name": "_preflight_echo",
        "description": "Devolve o número recebido. Use sempre que perguntarem o valor de sonda.",
        "parameters": {
            "type": "object",
            "properties": {"valor": {"type": "integer", "description": "o número"}},
            "required": ["valor"],
        },
    },
}
_PERGUNTA = "Chame _preflight_echo com valor 7."

# Teto de saída que a sonda EXIGE de quem constrói o modelo.
#
# Não é detalhe de ajuste fino: num provider que devolve a chamada de tool como
# bloco estruturado (Anthropic), o nome da tool e o JSON dos argumentos são
# tokens de SAÍDA. Com teto apertado a resposta é truncada antes de o bloco
# fechar, `tool_calls` volta vazio e a sonda conclui "o modelo não faz tool
# calling" — sobre um modelo que faz.
#
# Foi exatamente o que aconteceu em 27/08/2026: o worker construía a sonda com
# max_tokens=16 e reprovava o claude-haiku-4-5 na partida. Medido depois: 16
# reprova, 64 e 256 passam. 256 dá folga para nome de tool e argumentos maiores
# sem custar nada relevante — é UMA chamada, uma vez, no boot.
MAX_TOKENS_SONDA = 256


@dataclass(frozen=True)
class Resultado:
    ok: bool
    alcancavel: bool
    chama_tool: bool
    detalhe: str
    falha: ErroClassificado | None = None

    def __str__(self) -> str:
        if self.ok:
            return "provedor alcançável e faz tool calling"
        return self.detalhe


def verificar(construir_modelo, *, exigir_tool: bool = True) -> Resultado:
    """Uma chamada real ao provedor configurado.

    `construir_modelo` é injetado para o preflight não decidir provedor — quem
    decide é `provedores.construir`. Assim o mesmo código serve para verificar o
    modelo do agente e o do juiz, que podem ser de provedores diferentes.
    """
    try:
        modelo = construir_modelo()
    except Exception as e:
        falha = classificar(e)
        return Resultado(ok=False, alcancavel=False, chama_tool=False,
                         detalhe=f"não foi possível construir o modelo: {falha.detalhe}",
                         falha=falha)

    teto = getattr(modelo, "max_tokens", None)
    if exigir_tool and isinstance(teto, int) and teto < MAX_TOKENS_SONDA:
        # Aviso e não erro: alguns providers não expõem `max_tokens` no cliente,
        # e recusar por causa de um atributo ausente seria pior que o problema.
        log.warning(
            "PREFLIGHT | teto de saída do modelo é %s, abaixo de MAX_TOKENS_SONDA=%s — "
            "a chamada de tool pode ser truncada e a sonda reprovar um modelo bom",
            teto, MAX_TOKENS_SONDA,
        )

    try:
        if exigir_tool and hasattr(modelo, "bind_tools"):
            resposta = modelo.bind_tools([_TOOL_DE_SONDA]).invoke(_PERGUNTA)
            chamou = bool(getattr(resposta, "tool_calls", None))
            if not chamou:
                return Resultado(
                    ok=False, alcancavel=True, chama_tool=False,
                    detalhe=("o provedor respondeu, mas o modelo NÃO chamou a tool. "
                             "Um agente sem tool calling alucina o dado em vez de buscá-lo."),
                )
            return Resultado(ok=True, alcancavel=True, chama_tool=True,
                             detalhe="provedor alcançável e faz tool calling")

        modelo.invoke("oi")
        return Resultado(ok=True, alcancavel=True, chama_tool=False,
                         detalhe="provedor alcançável (tool calling não verificado)")
    except Exception as e:
        falha = classificar(e)
        return Resultado(ok=False, alcancavel=False, chama_tool=False,
                         detalhe=f"[{falha.codigo}] {falha.detalhe}", falha=falha)


def exigir(construir_modelo, *, exigir_tool: bool = True) -> None:
    """Igual a `verificar`, mas derruba o processo se não passar.

    Existe para o worker: consumir fila sem conseguir responder é pior que não
    subir — a mensagem do usuário é consumida, a falha é silenciosa e o operador
    não tem sinal nenhum de que algo está errado.
    """
    r = verificar(construir_modelo, exigir_tool=exigir_tool)
    if r.ok:
        log.info("PREFLIGHT OK | %s", r)
        return
    log.error("PREFLIGHT FALHOU | %s", r.detalhe)
    raise RuntimeError(f"preflight do modelo falhou: {r.detalhe}")
