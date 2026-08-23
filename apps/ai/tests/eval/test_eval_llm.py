"""Eval com LLM real: as regras de negócio viram asserção sobre a resposta.

NÃO roda por padrão (`pytest.ini` exclui o marcador `llm`). Rodar com:
    LLM_PROVIDER=anthropic pytest tests/eval -m llm
    LLM_PROVIDER=ollama    pytest tests/eval -m llm     # pior caso de formato

Por que LIMIAR e não all-or-nothing: o modelo é estocástico e nenhum prompt
acerta 100% dos turnos. Um gate binário ficaria vermelho por ruído, seria
ignorado em duas semanas e pararia de proteger qualquer coisa. O que importa é
a QUEDA da taxa entre uma versão do prompt e a seguinte.

As asserções reutilizam as mesmas regras de `dominio/refeitorio/regras.py` que
rodam em produção — lá elas só registram log, aqui elas reprovam. Uma
implementação, dois rigores.
"""

import pytest

from app.agent.context import RequestContext, reset_context, set_context
from app.agent.dominio.refeitorio.filters import normalizar
from app.agent.dominio.refeitorio.perfil import PERFIL
from app.agent.motor import turn
from app.agent.motor.reminders import Gatilhos
from app.agent.motor.validacao import verificar
from tests.eval import fakes

TAXA_MINIMA = 0.90

pytestmark = pytest.mark.llm


def _rodar(caso, monkeypatch):
    dados = fakes.carregar_dados(caso["dados"])
    fakes.instalar(monkeypatch, dados)

    historico = caso.get("historico") or []
    if not PERFIL.esta_no_escopo(caso["mensagem"], bool(historico)):
        return None, dados  # barrado pelo guardrail

    contexto = RequestContext(unidade_id=1, usuario_id=caso.get("usuario_id"))
    token = set_context(contexto)
    try:
        return turn.executar_turno(
            PERFIL, caso["mensagem"], contexto=contexto, historico=historico,
            gatilhos=Gatilhos(primeira_interacao_do_dia=caso.get("primeira_do_dia", False)),
            session_id=caso["nome"][:12],
        ), dados
    finally:
        reset_context(token)


def _conferir(caso, resultado, dados) -> list[str]:
    """Devolve a lista de falhas do caso (vazia = passou)."""
    esperado = caso["esperado"]
    falhas: list[str] = []

    if esperado.get("deve_ser_fora_de_escopo"):
        if resultado is not None:
            falhas.append("passou pelo guardrail, deveria ter sido barrado")
        return falhas

    if resultado is None:
        return ["barrado pelo guardrail indevidamente"]
    if resultado.erro:
        return [f"turno falhou: {resultado.erro}"]

    resposta_norm = normalizar(resultado.resposta)
    chamadas = set(resultado.tools_chamadas)

    for tool in esperado.get("tools_obrigatorias", []):
        if tool not in chamadas:
            falhas.append(f"não chamou {tool} (chamou {sorted(chamadas)})")

    if esperado.get("tool_de_cardapio_obrigatoria"):
        catalogo = {"listar_pratos_do_dia", "cardapio_da_semana", "filtrar_pratos",
                    "detalhar_prato", "comparar_pratos"}
        if not chamadas & catalogo:
            falhas.append(f"nenhuma tool de cardápio no turno (chamou {sorted(chamadas)})")

    if esperado.get("cita_todos_os_pratos"):
        faltando = [p["nome"] for p in dados["pratos"]
                    if normalizar(p["nome"]).split(" com ")[0] not in resposta_norm]
        if faltando:
            falhas.append(f"regra contratual: não listou o cardápio completo, faltou {faltando}")

    for nome in esperado.get("nao_deve_recomendar", []):
        if normalizar(nome) in resposta_norm:
            falhas.append(f"recomendou o que o perfil proíbe: {nome!r}")

    alternativas = esperado.get("deve_conter_algum")
    if alternativas and not any(normalizar(a) in resposta_norm for a in alternativas):
        falhas.append(f"resposta não contém nenhum de {alternativas}")

    if esperado.get("nao_pode_confirmar_sozinho"):
        # A prévia não pode virar gravação sem o usuário dizer que está certo.
        if any("confirmado" in c and "true" in c.lower() for c, _ in
               [(a, b) for a, b in (resultado.observacoes.chamadas if resultado.observacoes else [])]):
            falhas.append("gravou o consumo sem passar pela confirmação do usuário")

    if esperado.get("ressalva_incerteza"):
        ressalvas = ("nao reconheci", "nao encontrei", "nao entrou", "nao identifiquei",
                     "fora da conta", "nao achei", "aproximad")
        if not any(r in resposta_norm for r in ressalvas):
            falhas.append("item ficou fora do total e a resposta não ressalvou")

    # As regras de produção, aqui como gate.
    quero = []
    if esperado.get("sem_prato_inventado"):
        quero += ["R1-sem-tool-de-catalogo", "R2-prato-fora-do-cardapio"]
    if esperado.get("numeros_rastreaveis"):
        quero.append("R3-numero-nao-exposto")
    if quero:
        v = verificar(PERFIL.regras, resultado.resposta,
                      tools_chamadas=resultado.tools_chamadas,
                      observacoes=resultado.observacoes)
        for rid, detalhe in v.violacoes:
            if rid in quero:
                falhas.append(f"{rid}: {detalhe}")

    return falhas


def test_eval_das_regras_de_negocio(monkeypatch, capsys):
    casos = fakes.carregar_casos()
    assert casos, "nenhum caso de eval encontrado"

    resultados = []
    for caso in casos:
        try:
            resultado, dados = _rodar(caso, monkeypatch)
            falhas = _conferir(caso, resultado, dados)
        except Exception as e:  # um caso quebrado não invalida a rodada inteira
            falhas = [f"exceção: {type(e).__name__}: {e}"]
        resultados.append((caso, falhas))

    linhas = ["", "=" * 78, "EVAL — regras de negócio", "=" * 78]
    for caso, falhas in resultados:
        marca = "PASS" if not falhas else "FALHA"
        linhas.append(f"[{marca}] {caso['nome']}")
        if falhas:
            linhas.append(f"        motivo: {caso['porque']}")
            linhas += [f"        - {f}" for f in falhas]

    passaram = sum(1 for _, f in resultados if not f)
    taxa = passaram / len(resultados)
    linhas += ["-" * 78, f"{passaram}/{len(resultados)} casos ({taxa:.0%}) | mínimo {TAXA_MINIMA:.0%}", ""]

    with capsys.disabled():
        print("\n".join(linhas))

    assert taxa >= TAXA_MINIMA, (
        f"taxa de acerto {taxa:.0%} abaixo do mínimo {TAXA_MINIMA:.0%} — "
        "provável regressão de prompt (veja a tabela acima)"
    )
