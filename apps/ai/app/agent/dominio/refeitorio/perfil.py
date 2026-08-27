"""Perfil do domínio "refeitório self-service" — a Lia.

Este é o único arquivo que o motor precisa para rodar este produto. Trocar de
produto significa escrever outro perfil ao lado deste; nada em `motor/` muda.
"""

import re

from app.agent.dominio.refeitorio import prompts
from app.agent.dominio.refeitorio import tools as _t
from app.agent.dominio.refeitorio import regras as _regras
from app.agent.dominio.refeitorio.filters import normalizar
from app.agent.dominio.refeitorio.guardrail import is_in_scope
from app.agent.motor import llm
from app.agent.motor.perfil import PerfilDeDominio
from app.agent.motor.reminders import Gatilhos, Reminder
from app.agent.motor import planejamento
from app.agent.motor.registry import CATALOGO, ToolSpec

RESPOSTA_ERRO_TRANSIENTE = (
    "Desculpe, tive um problema para consultar as informações agora. "
    "Pode tentar de novo em instantes?"
)


def _e_admin(contexto) -> bool:
    """Tools de gestão leem dado agregado da unidade inteira — número que o
    cliente comum não deve ver. A flag vem carimbada pela API Go a partir do
    token validado; o worker não a recebe de cliente nenhum."""
    return bool(getattr(contexto, "is_admin", False))


def _tem_usuario(contexto) -> bool:
    """Sem usuário identificado, estas tools só sabem responder 'não
    identificado' — e o modelo gasta um turno inteiro para chegar nessa
    resposta. Melhor não oferecê-las."""
    return getattr(contexto, "usuario_id", None) is not None


# CATALOGO marca as tools que mostram ao modelo os pratos realmente servidos.
# É o que sustenta a regra "sem tool = sem recomendação": se nenhuma delas rodou
# no turno, qualquer prato citado na resposta foi inventado.
REGISTRO: tuple[ToolSpec, ...] = (
    # Do MOTOR, não do domínio: planejar antes de agir não tem nada de
    # refeitório. Exposta aqui porque quem decide oferecer é o produto.
    ToolSpec(planejamento.pensar),
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
    ToolSpec(_t.resumo_de_desperdicio, disponivel=_e_admin),
)

# A âncora `regra_de_origem` PRECISA aparecer literalmente no SYSTEM_AGENT — é a
# invariante que impede um reminder de conceder algo que o system não autoriza.
# Há teste que verifica isso para cada reminder declarado aqui.
REMINDER_ABERTURA_DO_DIA = Reminder(
    nome="primeira_do_dia",
    texto=prompts.REMINDER_PRIMEIRA_DO_DIA,
    regra_de_origem="PRIMEIRA CONVERSA DO DIA",
)


REMINDER_SAUDE = Reminder(
    nome="condicao_de_saude",
    texto=prompts.REMINDER_CONDICAO_DE_SAUDE,
    regra_de_origem="CONDIÇÃO DE SAÚDE",
)

REMINDER_CONFIRMACAO = Reminder(
    nome="confirmacao_de_registro",
    texto=prompts.REMINDER_CONFIRMACAO_DE_REGISTRO,
    regra_de_origem="DUAS ETAPAS",
)

# Formas de confirmar que apareceram ou aparecem no uso real. Fica no domínio:
# "pode registrar" só significa algo num produto que registra consumo.
_CONFIRMACAO = re.compile(
    r"^(sim|isso|isso mesmo|exato|exatamente|correto|ta certo|esta certo|confirmo|"
    r"pode (ser|salvar|registrar|confirmar|pontuar)|manda|beleza|ok|certo|perfeito|"
    r"tudo certo|e isso)\b",
    re.IGNORECASE,
)

# Condições que exigem encaminhamento a profissional. Lista do domínio, não do
# motor — outro produto teria outros gatilhos (ou nenhum).
_CONDICAO_DE_SAUDE = re.compile(
    r"\b(diabet|pressao alta|hipertens|colesterol|triglicer|renal|rim|"
    r"gestante|gravid|amamenta|anemia|celiac|gastrite|refluxo|bariatric|"
    r"quimioterapia|tireoide)",
    re.IGNORECASE,
)


def reminders_do_turno(gatilhos: Gatilhos, mensagem: str = "") -> tuple[Reminder, ...]:
    ativos = []
    if gatilhos.primeira_interacao_do_dia:
        ativos.append(REMINDER_ABERTURA_DO_DIA)
    if _CONDICAO_DE_SAUDE.search(normalizar(mensagem or "")):
        ativos.append(REMINDER_SAUDE)
    if _CONFIRMACAO.match(normalizar(mensagem or "").strip()):
        ativos.append(REMINDER_CONFIRMACAO)
    return tuple(ativos)


# Já encaminhou? Aceita qualquer forma de dizer, para não duplicar a frase
# quando o modelo acertar sozinho.
_JA_ENCAMINHOU = re.compile(
    r"\b(medico|nutricionista|profissional de saude|endocrino|especialista)\b"
)


def pos_processar(resposta: str, gatilhos: Gatilhos, mensagem: str) -> str:
    """Garante o encaminhamento a profissional quando o assunto exige.

    Em código, não no prompt: com reminder reinjetado a aderência ficou em 0 de
    3 medições. Exigência de conformidade não pode depender de o modelo lembrar.
    """
    if not _CONDICAO_DE_SAUDE.search(normalizar(mensagem or "")):
        return resposta
    if _JA_ENCAMINHOU.search(normalizar(resposta)):
        return resposta
    return resposta.rstrip() + prompts.ENCAMINHAMENTO_PROFISSIONAL


PERFIL = PerfilDeDominio(
    nome="refeitorio",
    system_prompt=prompts.SYSTEM_AGENT,
    registro=REGISTRO,
    esta_no_escopo=is_in_scope,
    resposta_fora_de_escopo=prompts.RESPOSTA_FORA_DE_ESCOPO,
    resposta_erro_transiente=RESPOSTA_ERRO_TRANSIENTE,
    resposta_bloqueada=(
        "Opa, deixa eu refazer essa recomendação 😅 Pelo que você me contou sobre "
        "restrições e alergias, o que eu ia indicar não é o mais adequado pra você. "
        "Pode me pedir de novo?"
    ),
    reminders=reminders_do_turno,
    regras=_regras.construir(REGISTRO),
    pos_processar=pos_processar,
)


def prewarm() -> None:
    llm.prewarm(PERFIL.system_prompt, [spec.tool for spec in REGISTRO])
