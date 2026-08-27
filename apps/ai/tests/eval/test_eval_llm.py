"""Eval com LLM real: as regras de negócio viram asserção sobre a resposta.

NÃO roda por padrão (`pytest.ini` exclui o marcador `llm`). Rodar com:

    LLM_PROVIDER=anthropic pytest tests/eval -m llm -s
    EVAL_REPETICOES=3 LLM_PROVIDER=anthropic pytest tests/eval -m llm -s
    EVAL_BATERIA=seguranca ... pytest tests/eval -m llm -s

POR QUE REPETIÇÕES. A primeira versão deste eval tinha 10 casos e uma rodada, e
as medições vieram 20% → 60% → 80% → 80% → 60%. Com uma execução por caso é
impossível distinguir "o produto está errado" de "o modelo variou" — e um gate
que fica vermelho por variação é um gate que todo mundo aprende a ignorar.

Rodando cada caso N vezes, a distinção aparece sozinha:

    N/N passa  → comportamento estável e correto
    0/N passa  → DEFEITO. É aqui que se olha primeiro.
    entre eles → INSTÁVEL. O produto às vezes acerta; costuma ser prompt frouxo
                 ou asserção dependente de redação.

O limiar vale sobre o total de execuções, não sobre casos, para uma instabilidade
isolada não derrubar a rodada inteira.
"""

import os
import uuid
from collections import defaultdict

import pytest

from app.agent.context import RequestContext, reset_context, set_context
from app.agent.dominio.refeitorio.perfil import PERFIL
from app.agent.motor import turn
from app.agent.motor.reminders import Gatilhos
from tests.eval import assercoes, fakes, juiz

TAXA_MINIMA = float(os.getenv("EVAL_TAXA_MINIMA", "0.90"))
REPETICOES = int(os.getenv("EVAL_REPETICOES", "1"))
BATERIA = os.getenv("EVAL_BATERIA") or None

pytestmark = pytest.mark.llm


def _rodar(caso, monkeypatch):
    """Roda a conversa do caso e devolve o contexto ACUMULADO.

    `turnos` existe porque várias regras só se completam em dois passos: o prompt
    manda perguntar sobre sobras ANTES de registrar, então exigir a tool no
    primeiro turno reprovaria o comportamento correto.

    O `session_id` é novo a cada execução, e estável entre os turnos DELA. Isso
    importa desde que o motor passou a guardar estado por conversa entre turnos
    (`motor/memoria.py`, TTL de 15 min): derivá-lo do nome do caso fazia as
    REPETIÇÕES herdarem umas das outras — logo elas mediriam contextos
    diferentes, e o número que sai daqui deixaria de ser reproduzível, quando a
    razão de existirem é justamente separar "o produto está errado" de "o modelo
    variou". Um prefixo truncado ainda por cima colidia entre casos DIFERENTES
    ("recomendação" cobria três casos da bateria), tornando o resultado
    dependente da ordem do glob.
    """
    dados = fakes.carregar_dados(caso["dados"])
    fakes.instalar(monkeypatch, dados)

    mensagens = caso.get("turnos") or [caso["mensagem"]]
    historico = list(caso.get("historico") or [])

    if not PERFIL.esta_no_escopo(mensagens[0], bool(historico)):
        return None, dados

    sessao = f"{caso['nome'][:12]}-{uuid.uuid4().hex[:8]}"
    contexto = RequestContext(unidade_id=1, usuario_id=caso.get("usuario_id"))
    token = set_context(contexto)
    try:
        resultado = None
        tools, chamadas = [], []
        for i, mensagem in enumerate(mensagens):
            resultado = turn.executar_turno(
                PERFIL, mensagem, contexto=contexto, historico=historico,
                gatilhos=Gatilhos(primeira_interacao_do_dia=caso.get("primeira_do_dia", False) and i == 0),
                session_id=sessao,
            )
            tools += resultado.tools_chamadas
            if resultado.observacoes:
                chamadas += list(resultado.observacoes.chamadas)
            historico += [{"papel": "user", "conteudo": mensagem},
                          {"papel": "assistant", "conteudo": resultado.resposta}]
            if resultado.erro:
                break
    finally:
        reset_context(token)

    return assercoes.Contexto(
        resposta=resultado.resposta, tools=tools, observacoes=resultado.observacoes,
        dados=dados, erro=resultado.erro, chamadas=chamadas,
    ), dados


def _conferir(caso, ctx, _dados=None) -> list[str]:
    esperado = caso["esperado"]

    if esperado.get("deve_ser_fora_de_escopo"):
        return [] if ctx is None else ["passou pelo guardrail, deveria ter sido barrado"]
    if ctx is None:
        return ["barrado pelo guardrail indevidamente"]

    return assercoes.conferir(ctx, esperado)


def _executar_uma_vez(caso, monkeypatch) -> tuple[list[str], bool]:
    try:
        ctx, dados = _rodar(caso, monkeypatch)
        bloqueou = bool(ctx and ctx.erro == assercoes.BLOQUEIO)
        return _conferir(caso, ctx, dados), bloqueou
    except Exception as e:  # um caso quebrado não invalida a rodada inteira
        return [f"exceção: {type(e).__name__}: {e}"], False


def test_eval_das_regras_de_negocio(monkeypatch, capsys):
    casos = fakes.carregar_casos(BATERIA)
    assert casos, f"nenhum caso encontrado (bateria={BATERIA})"

    # caso -> lista de execuções, cada uma com suas falhas
    execucoes: dict[str, list[list[str]]] = {}
    for caso in casos:
        execucoes[caso["nome"]] = [_executar_uma_vez(caso, monkeypatch) for _ in range(REPETICOES)]

    por_bateria: dict[str, list[tuple]] = defaultdict(list)
    for caso in casos:
        rodadas = execucoes[caso["nome"]]
        acertos = sum(1 for f, _ in rodadas if not f)
        bloqueios = sum(1 for _, b in rodadas if b)
        por_bateria[caso["bateria"]].append((caso, acertos, rodadas, bloqueios))

    linhas = ["", "=" * 100,
              f"EVAL — {len(casos)} casos × {REPETICOES} repetição(ões) = {len(casos) * REPETICOES} execuções",
              "=" * 100]

    defeitos, instaveis = [], []
    for bateria in sorted(por_bateria):
        itens = por_bateria[bateria]
        ok = sum(a for _, a, _, _ in itens)
        tot = len(itens) * REPETICOES
        linhas.append(f"\n■ {bateria.upper():<16} {ok}/{tot} ({ok / tot:.0%})")
        for caso, acertos, rodadas, bloqueios in sorted(itens, key=lambda x: x[1]):
            if acertos == REPETICOES:
                marca = "  ok  "
            elif acertos == 0:
                marca = " FALHA"
                defeitos.append(caso)
            else:
                marca = "instav"
                instaveis.append(caso)
            aviso = f"  (rede bloqueou {bloqueios}x)" if bloqueios else ""
            linhas.append(f"  [{marca}] {acertos}/{REPETICOES}  {caso['nome']}{aviso}")
            if acertos < REPETICOES:
                motivos = {f for r, _ in rodadas for f in r}
                linhas += [f"            · {m}" for m in sorted(motivos)]

    total_ok = sum(a for itens in por_bateria.values() for _, a, _, _ in itens)
    total_bloqueios = sum(b for itens in por_bateria.values() for _, _, _, b in itens)
    total = len(casos) * REPETICOES
    taxa = total_ok / total

    linhas += ["", "-" * 100,
               f"execuções: {total_ok}/{total} ({taxa:.0%}) | mínimo {TAXA_MINIMA:.0%}",
               f"defeitos (0/{REPETICOES}): {len(defeitos)}" + (f" → {[c['nome'] for c in defeitos]}" if defeitos else ""),
               f"bloqueios pela rede de segurança: {total_bloqueios}"
               + (" (resposta insegura não chegou ao usuário; prompt ainda tentou)" if total_bloqueios else ""),
               f"instáveis: {len(instaveis)}" + (f" → {[c['nome'] for c in instaveis]}" if instaveis else ""),
               ""]
    if juiz.INDISPONIVEIS:
        linhas.append(
            f"ATENÇÃO: {len(juiz.INDISPONIVEIS)} julgamento(s) NÃO aconteceram (cota, rede ou "
            f"modelo fora do ar). A taxa acima está subestimada e não serve de parâmetro. "
            f"Primeiro motivo: {juiz.INDISPONIVEIS[0]}\n"
        )
    if REPETICOES == 1:
        linhas.append("NOTA: com 1 repetição não dá para separar defeito de variância. "
                      "Use EVAL_REPETICOES=3 para o número valer como parâmetro.\n")

    with capsys.disabled():
        print("\n".join(linhas))

    assert not juiz.INDISPONIVEIS, (
        f"{len(juiz.INDISPONIVEIS)} julgamento(s) não aconteceram — a rodada não mediu o "
        f"produto, mediu a disponibilidade do juiz. Primeiro motivo: {juiz.INDISPONIVEIS[0]}"
    )
    assert taxa >= TAXA_MINIMA, (
        f"taxa {taxa:.0%} abaixo do mínimo {TAXA_MINIMA:.0%} — "
        f"{len(defeitos)} defeito(s) e {len(instaveis)} instável(is); veja a tabela acima"
    )
