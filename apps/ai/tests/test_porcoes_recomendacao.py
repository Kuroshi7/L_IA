from app.agent.dominio.refeitorio import tools, filters, regras
from app.agent.motor.observacao import ObservacoesDoTurno
from app.agent.motor.validacao import Achado


def test_porcao_vem_da_referencia_vinculada():
    prato = tools._com_porcao({'id':1,'nome':'Frango','porcoes':[
        {'medida_label':'100g','medida_cod':'','quantidade_g':100},
        {'medida_label':'FILE','medida_cod':'FILE','quantidade_g':100},
    ]})
    assert prato['porcao_referencia']['medida'] == 'filé'
    assert prato['porcao_referencia']['quantidade'] == 1
    assert prato['porcao_referencia']['gramas'] == 100
    assert filters.resumir(prato)['porcao_referencia'] == prato['porcao_referencia']


def test_nao_inventa_medida_pelo_nome_do_prato():
    prato = tools._com_porcao({'id':1,'nome':'Filé de Frango','porcoes':[]})
    assert prato['porcao_referencia'] is None
    assert prato['porcao_status'] == 'sem_medida_caseira_cadastrada'


def test_reparo_preserva_porcoes_e_numeros_validos():
    obs = ObservacoesDoTurno()
    obs.registrar(('filtrar_pratos','{}'), [{'id':1,'nome':'Frango','proteinas_g':31}])
    v = type('V', (), {'ids':('R3-numero-nao-exposto',)})()
    resposta = regras.reparar_resposta('Sugiro **Frango** — 1 filé, 999 kcal e 31g de proteína.',v,obs)
    assert '1 filé' in resposta and '**Frango**' in resposta and '31g' in resposta
    assert '999' not in resposta
    assert regras._numero_nao_exposto(Achado(resposta,(),obs)) is None


def test_reparo_nao_deixa_metade_de_um_intervalo_inventado():
    obs = ObservacoesDoTurno()
    obs.registrar(('filtrar_pratos','{}'), [{'nome':'Frango','proteinas_g':31}])
    v = type('V', (), {'ids':('R3-numero-nao-exposto',)})()
    resposta = regras.reparar_resposta('Sirva 1 filé — 200-999 kcal.',v,obs)
    assert '1 filé' in resposta and '200-' not in resposta and '999' not in resposta
