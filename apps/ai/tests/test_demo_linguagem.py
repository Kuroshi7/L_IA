import pytest

from app.agent.dominio.refeitorio.perfil import pos_processar, reminders_do_turno, REMINDER_CONSUMO
from app.agent.motor.perfil import Gatilhos


@pytest.mark.parametrize('termo', ['100% seguro', 'totalmente seguro', 'completamente segura', 'sem risco', 'sem nenhum risco'])
def test_nao_garante_seguranca_absoluta(termo):
    resposta = pos_processar(f'Esse prato é {termo} para você.', Gatilhos(), 'Tenho alergia a leite.')
    assert termo not in resposta
    assert 'ingredientes cadastrados' in resposta
    assert 'equipe do refeitório' in resposta


def test_preserva_aviso_de_risco():
    original = 'Você informou alergia a leite, e esse prato leva creme de leite.'
    assert pos_processar(original, Gatilhos(), 'Tenho alergia a leite.') == original


def test_relato_de_consumo_exige_previa_da_tool():
    from app.agent.dominio.refeitorio.prompts import SYSTEM_AGENT
    assert REMINDER_CONSUMO.regra_de_origem in SYSTEM_AGENT
    reminders = reminders_do_turno(Gatilhos(), 'Comi arroz e feijão, não sobrou nada.')
    assert REMINDER_CONSUMO in reminders
    assert 'sobras_informadas=true' in REMINDER_CONSUMO.texto
    assert 'Nunca envie confirmado=true' in REMINDER_CONSUMO.texto


@pytest.mark.parametrize('afirmacao', [
    'Frango não dispara o açúcar no sangue.',
    'Esse prato ajuda a controlar sua glicemia.',
    'Arroz integral solta o açúcar mais devagar.',
    'Essa refeição mantém o açúcar mais estável.',
    'É o melhor prato para diabéticos.',
])
def test_retira_promessas_de_efeito_clinico(afirmacao):
    resposta = pos_processar('O cardápio tem Frango Grelhado.\n'+afirmacao, Gatilhos(), 'Tenho diabetes.')
    assert afirmacao not in resposta
    assert 'O cardápio tem Frango Grelhado.' in resposta
    assert 'nutricionista' in resposta


def test_aviso_de_alergia_nao_assume_autoridade():
    resposta = pos_processar('Não posso liberar não. Você informou alergia a amendoim e a salada leva amendoim.', Gatilhos(), 'Quero comer mesmo assim.')
    assert 'não posso liberar' not in resposta.lower()
    assert 'a decisão é sua' in resposta
    assert 'leva amendoim' in resposta


def test_condicao_de_saude_mostra_somente_fatos_do_catalogo(monkeypatch):
    from app.agent.dominio.refeitorio import perfil
    from app.agent.motor.observacao import ObservacoesDoTurno
    obs = ObservacoesDoTurno()
    obs.registrar(('listar_pratos_do_dia','{}'), [
        {'nome':'Frango Grelhado', 'ingredientes':['frango','alho']},
        {'nome':'Strogonoff', 'conflita_com_perfil':['você informou alergia a leite']},
    ])
    monkeypatch.setattr(perfil, 'observacoes_do_turno', lambda: obs)
    resposta = perfil.pos_processar('Frango controla sua glicose: coma 1 filé.', Gatilhos(), 'Tenho diabetes.')
    assert 'controla sua glicose' not in resposta
    assert '1 filé' not in resposta
    assert 'Frango Grelhado' in resposta and 'frango, alho' in resposta
    assert 'Strogonoff' not in resposta
    assert 'nutricionista' in resposta
