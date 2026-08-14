"""Pós-validação: recomendação sem tool de cardápio no turno = possível alucinação."""

from app.agent.validators import resposta_recomenda, verificar_resposta


RESPOSTA_COM_RECOMENDACAO = (
    "O cardápio de hoje é: arroz, feijão, frango grelhado. "
    "Baseado nas suas preferências, recomendo o frango grelhado."
)
RESPOSTA_SEM_RECOMENDACAO = "Você tem 320 pontos e está no nível 2. Continue assim!"


def test_detecta_recomendacao():
    assert resposta_recomenda(RESPOSTA_COM_RECOMENDACAO)
    assert resposta_recomenda("Sugiro o peixe assado, mais leve.")
    assert not resposta_recomenda(RESPOSTA_SEM_RECOMENDACAO)


def test_recomendacao_com_tool_de_cardapio_e_valida():
    assert verificar_resposta(RESPOSTA_COM_RECOMENDACAO, ["meu_perfil", "listar_pratos_do_dia"])
    assert verificar_resposta(RESPOSTA_COM_RECOMENDACAO, ["filtrar_pratos"])


def test_recomendacao_sem_tool_de_cardapio_e_invalida():
    assert not verificar_resposta(RESPOSTA_COM_RECOMENDACAO, [])
    assert not verificar_resposta(RESPOSTA_COM_RECOMENDACAO, ["meu_perfil", "meus_pontos"])


def test_resposta_sem_recomendacao_sempre_valida():
    assert verificar_resposta(RESPOSTA_SEM_RECOMENDACAO, [])
