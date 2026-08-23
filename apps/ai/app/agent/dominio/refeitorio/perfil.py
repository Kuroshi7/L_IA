"""Perfil do domínio "refeitório self-service" — a Lia.

Este é o único arquivo que o motor precisa para rodar este produto. Trocar de
produto significa escrever outro perfil ao lado deste; nada em `motor/` muda.
"""

from app.agent.dominio.refeitorio import prompts
from app.agent.dominio.refeitorio import tools as _t
from app.agent.dominio.refeitorio import regras as _regras
from app.agent.dominio.refeitorio.guardrail import is_in_scope
from app.agent.motor import llm
from app.agent.motor.perfil import PerfilDeDominio
from app.agent.motor.reminders import Gatilhos, Reminder
from app.agent.motor.registry import CATALOGO, ToolSpec

RESPOSTA_ERRO_TRANSIENTE = (
    "Desculpe, tive um problema para consultar as informações agora. "
    "Pode tentar de novo em instantes?"
)


def _tem_usuario(contexto) -> bool:
    """Sem usuário identificado, estas tools só sabem responder 'não
    identificado' — e o modelo gasta um turno inteiro para chegar nessa
    resposta. Melhor não oferecê-las."""
    return getattr(contexto, "usuario_id", None) is not None


# CATALOGO marca as tools que mostram ao modelo os pratos realmente servidos.
# É o que sustenta a regra "sem tool = sem recomendação": se nenhuma delas rodou
# no turno, qualquer prato citado na resposta foi inventado.
REGISTRO: tuple[ToolSpec, ...] = (
    ToolSpec(_t.listar_pratos_do_dia, capacidades=frozenset({CATALOGO})),
    ToolSpec(_t.cardapio_da_semana, capacidades=frozenset({CATALOGO})),
    ToolSpec(_t.filtrar_pratos, capacidades=frozenset({CATALOGO})),
    ToolSpec(_t.detalhar_prato, capacidades=frozenset({CATALOGO})),
    ToolSpec(_t.comparar_pratos, capacidades=frozenset({CATALOGO})),
    ToolSpec(_t.meu_perfil, disponivel=_tem_usuario),
    ToolSpec(_t.meus_pontos, disponivel=_tem_usuario),
    ToolSpec(_t.consultar_medidas_caseiras),
    ToolSpec(_t.buscar_informacao),
    ToolSpec(_t.registrar_consumo),
)

# A âncora `regra_de_origem` PRECISA aparecer literalmente no SYSTEM_AGENT — é a
# invariante que impede um reminder de conceder algo que o system não autoriza.
# Há teste que verifica isso para cada reminder declarado aqui.
REMINDER_CARDAPIO_COMPLETO = Reminder(
    nome="primeira_do_dia",
    texto=prompts.REMINDER_PRIMEIRA_DO_DIA,
    regra_de_origem="REGRA CONTRATUAL",
)


def reminders_do_turno(gatilhos: Gatilhos) -> tuple[Reminder, ...]:
    if gatilhos.primeira_interacao_do_dia:
        return (REMINDER_CARDAPIO_COMPLETO,)
    return ()


PERFIL = PerfilDeDominio(
    nome="refeitorio",
    system_prompt=prompts.SYSTEM_AGENT,
    registro=REGISTRO,
    esta_no_escopo=is_in_scope,
    resposta_fora_de_escopo=prompts.RESPOSTA_FORA_DE_ESCOPO,
    resposta_erro_transiente=RESPOSTA_ERRO_TRANSIENTE,
    reminders=reminders_do_turno,
    regras=_regras.construir(REGISTRO),
)


def prewarm() -> None:
    llm.prewarm(PERFIL.system_prompt, [spec.tool for spec in REGISTRO])
