"""IA-21 — "pode registrar" tem de registrar.

No teste de usabilidade de 24/08/2026 o usuário escreveu "isso mesmo, pode
registrar" e recebeu "Está correto? Se sim, é só me confirmar que eu salvo".
Ao fim das 6 mensagens nada tinha sido gravado — nem consumo, nem pontos.

A instrução das DUAS ETAPAS chega no retorno da tool, que no turno seguinte já
está enterrado no histórico. O reminder repõe a regra no fim do contexto.
"""

import pytest

from app.agent.dominio.refeitorio.perfil import REMINDER_CONFIRMACAO, reminders_do_turno
from app.agent.motor.reminders import Gatilhos

SEM_GATILHO = Gatilhos()


def _nomes(mensagem: str) -> set[str]:
    return {r.nome for r in reminders_do_turno(SEM_GATILHO, mensagem)}


@pytest.mark.parametrize("mensagem", [
    "isso mesmo, pode registrar",   # o caso exato do teste de usabilidade
    "sim",
    "isso",
    "pode salvar",
    "pode pontuar",
    "confirmo",
    "ta certo",
    "exatamente",
    "Beleza",
    "É isso",
])
def test_confirmacao_dispara_o_reminder(mensagem):
    assert "confirmacao_de_registro" in _nomes(mensagem), mensagem


@pytest.mark.parametrize("mensagem", [
    "o que tem hoje?",
    "comi 2 conchas de arroz",
    "sou alérgico a amendoim",
    "não, não é isso",              # negativa não pode passar por confirmação
    "quero saber se posso comer isso",
])
def test_mensagem_comum_nao_dispara(mensagem):
    assert "confirmacao_de_registro" not in _nomes(mensagem), mensagem


def test_reminder_esta_ancorado_no_system_prompt():
    """Invariante do projeto: reminder não concede o que o system não autoriza.

    A âncora precisa aparecer literalmente — senão o reminder estaria criando
    regra nova em vez de repor uma que já vale.
    """
    from app.agent.dominio.refeitorio import prompts
    assert REMINDER_CONFIRMACAO.regra_de_origem in prompts.SYSTEM_AGENT


def test_o_reminder_nao_dispensa_a_previa():
    """A confirmação em duas etapas é deliberada: ela corrige erro de extração
    ANTES de virar pontuação. O reminder não pode autorizar pular a prévia."""
    texto = REMINDER_CONFIRMACAO.texto
    assert "Se ainda não houver prévia" in texto
    assert "MESMOS" in texto  # tem de reusar os itens da prévia, não reinterpretar
