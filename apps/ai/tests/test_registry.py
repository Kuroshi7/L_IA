"""Registro de tools: seleção por requisição e reaproveitamento de executor."""

from app.agent.dominio.refeitorio.perfil import PERFIL, REGISTRO
from app.agent.motor.registry import CATALOGO, assinatura, nomes_com_capacidade, tools_do_turno


def _ctx(usuario_id, is_admin=False):
    return type("C", (), {"unidade_id": 1, "usuario_id": usuario_id, "is_admin": is_admin})()


def test_sem_usuario_as_tools_de_identidade_ficam_fora():
    nomes = {s.nome for s in tools_do_turno(REGISTRO, _ctx(None))}
    assert "meu_perfil" not in nomes
    assert "meus_pontos" not in nomes
    # as demais continuam disponíveis — o anônimo ainda escolhe refeição
    assert "listar_pratos_do_dia" in nomes
    assert "registrar_consumo" in nomes


def test_usuario_identificado_ganha_as_tools_de_identidade():
    nomes = {s.nome for s in tools_do_turno(REGISTRO, _ctx(7))}
    assert {"meu_perfil", "meus_pontos"} <= nomes
    # Identificado NÃO é administrador: gestão continua de fora.
    assert "resumo_de_desperdicio" not in nomes


def test_so_admin_ve_as_tools_de_gestao():
    """Gate de privilégio: `resumo_de_desperdicio` lê dado agregado da unidade
    inteira. A flag vem carimbada pela API Go a partir do X-Admin-Token
    validado — cliente nenhum consegue escrevê-la."""
    comum = {s.nome for s in tools_do_turno(REGISTRO, _ctx(7))}
    admin = {s.nome for s in tools_do_turno(REGISTRO, _ctx(7, is_admin=True))}
    assert "resumo_de_desperdicio" not in comum
    assert "resumo_de_desperdicio" in admin
    assert comum < admin


def test_anonimo_mesmo_marcado_admin_nao_ganha_identidade():
    """Os dois gates são independentes: ser admin não inventa um usuário."""
    nomes = {s.nome for s in tools_do_turno(REGISTRO, _ctx(None, is_admin=True))}
    assert "meu_perfil" not in nomes
    assert "resumo_de_desperdicio" in nomes


def test_o_conjunto_de_admin_e_o_registro_inteiro():
    nomes = {s.nome for s in tools_do_turno(REGISTRO, _ctx(7, is_admin=True))}
    assert nomes == {s.nome for s in REGISTRO}


def test_assinatura_e_ordenada_e_estavel():
    specs = tools_do_turno(REGISTRO, _ctx(7))
    assert assinatura(specs) == assinatura(tuple(reversed(specs)))
    assert list(assinatura(specs)) == sorted(assinatura(specs))


def test_assinaturas_diferentes_para_contextos_diferentes():
    assert assinatura(tools_do_turno(REGISTRO, _ctx(None))) != assinatura(
        tools_do_turno(REGISTRO, _ctx(7))
    )


def test_capacidade_catalogo_cobre_as_tools_de_cardapio():
    # É esta lista que sustenta "sem tool de cardápio = recomendação inventada".
    assert nomes_com_capacidade(REGISTRO, CATALOGO) == frozenset({
        "listar_pratos_do_dia", "cardapio_da_semana", "filtrar_pratos",
        "detalhar_prato", "comparar_pratos",
    })


def test_perfil_expoe_o_registro():
    assert PERFIL.registro is REGISTRO
    assert PERFIL.nome == "refeitorio"
