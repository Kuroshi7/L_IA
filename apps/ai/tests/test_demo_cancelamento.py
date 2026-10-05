from dataclasses import replace

from app.agent import orchestrator


def test_cancelar_previa_nao_depende_do_classificador(monkeypatch):
    monkeypatch.setattr(orchestrator, 'PERFIL', replace(orchestrator.PERFIL, esta_no_escopo=lambda *a: False))
    resultado = orchestrator.processar_mensagem(
        session_id='qa-cancelar', mensagem='Cancelar', unidade_id=1,
        acao_pendente={'tipo':'consumo', 'etapa':'aguardando_confirmacao', 'itens':[]},
    )
    assert resultado['fora_de_escopo'] is False
    assert resultado['experiencia']['tipo'] == 'consumo_cancelado'
    assert resultado['limpar_acao_pendente'] is True


def test_assunto_fora_do_escopo_continua_barrado(monkeypatch):
    monkeypatch.setattr(orchestrator, 'PERFIL', replace(orchestrator.PERFIL, esta_no_escopo=lambda *a: False))
    resultado = orchestrator.processar_mensagem(
        session_id='qa-escopo', mensagem='Escreva um programa de computador', unidade_id=1,
        acao_pendente={'tipo':'consumo', 'etapa':'aguardando_confirmacao', 'itens':[]},
    )
    assert resultado['fora_de_escopo'] is True
