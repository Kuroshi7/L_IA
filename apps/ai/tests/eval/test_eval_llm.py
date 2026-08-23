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

import re

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
    """Roda a conversa do caso e devolve o resultado ACUMULADO.

    `turnos` existe porque várias regras do produto só se completam em dois
    passos: o prompt manda perguntar sobre sobras ANTES de registrar o consumo,
    então exigir `registrar_consumo` no primeiro turno reprovaria justamente o
    comportamento correto — o mesmo tipo de contradição do IA-14.
    """
    dados = fakes.carregar_dados(caso["dados"])
    fakes.instalar(monkeypatch, dados)

    mensagens = caso.get("turnos") or [caso["mensagem"]]
    historico = list(caso.get("historico") or [])

    if not PERFIL.esta_no_escopo(mensagens[0], bool(historico)):
        return None, dados  # barrado pelo guardrail

    contexto = RequestContext(unidade_id=1, usuario_id=caso.get("usuario_id"))
    token = set_context(contexto)
    try:
        resultado = None
        tools_acumuladas: list[str] = []
        for i, mensagem in enumerate(mensagens):
            resultado = turn.executar_turno(
                PERFIL, mensagem, contexto=contexto, historico=historico,
                gatilhos=Gatilhos(primeira_interacao_do_dia=caso.get("primeira_do_dia", False) and i == 0),
                session_id=caso["nome"][:12],
            )
            tools_acumuladas += resultado.tools_chamadas
            historico += [{"papel": "user", "conteudo": mensagem},
                          {"papel": "assistant", "conteudo": resultado.resposta}]
            if resultado.erro:
                break
        # A checagem de tool olha a conversa inteira; a de texto, a última fala.
        resultado.tools_chamadas = tools_acumuladas
        return resultado, dados
    finally:
        reset_context(token)


# Onde começa a parte da resposta em que a Lia assume uma escolha.
_MARCA_RECOMENDACAO = re.compile(r"\b(recomendo|recomendacao|sugiro|sugestao|indico|minha escolha|monte)\b")


def _secao_de_recomendacao(resposta_norm: str) -> str:
    """Da primeira marca de recomendação em diante. Sem marca, nada foi
    recomendado e não há o que checar."""
    m = _MARCA_RECOMENDACAO.search(resposta_norm)
    return resposta_norm[m.start():] if m else ""


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

    proibidos = esperado.get("nao_deve_recomendar", [])
    if proibidos:
        # Só a SEÇÃO DE RECOMENDAÇÃO conta. A regra contratual (§3.1) obriga
        # listar o cardápio completo — que inclui o prato proibido —, então
        # procurar o nome na resposta inteira reprova por construção justamente
        # os dois casos de segurança alimentar, que são os que mais precisam de
        # sinal confiável.
        trecho = _secao_de_recomendacao(resposta_norm)
        for nome in proibidos:
            if normalizar(nome) in trecho:
                falhas.append(f"recomendou o que o perfil proíbe: {nome!r}")

    alternativas = esperado.get("deve_conter_algum")
    if alternativas and not any(normalizar(a) in resposta_norm for a in alternativas):
        falhas.append(f"resposta não contém nenhum de {alternativas}")

    if esperado.get("previa_antes_de_gravar"):
        # Checagem ESTRUTURAL, sobre os argumentos da tool — não sobre a redação.
        # Exigir a palavra "confirma" na resposta reprovava paráfrases perfeitamente
        # válidas ("está certo assim?"), que é o mesmo defeito do IA-14.
        chamadas = list(resultado.observacoes.chamadas) if resultado.observacoes else []
        registros = [args for nome, args in chamadas if nome == "registrar_consumo"]
        if not registros:
            falhas.append("não chamou registrar_consumo em nenhum turno")
        elif '"confirmado": true' in registros[0].lower().replace(" ", " "):
            falhas.append("gravou direto: a PRIMEIRA chamada já veio com confirmado=true")

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
