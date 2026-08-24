"""Biblioteca de asserções do eval.

Separada do runner por um motivo medido: as rodadas variavam 20 pontos porque
várias checagens dependiam da REDAÇÃO ("a resposta contém 'não reconheci'"), e o
modelo parafraseia. Uma checagem difusa que ninguém testa é ruído disfarçado de
sinal.

Duas regras aqui:

1. **Prefira estrutura.** Tool chamada, argumento de tool, nome de prato que
   veio de um retorno — isso não muda com a redação. Só cai no texto quando o
   requisito É sobre o que a pessoa lê ("a Lia avisou que o item ficou de fora?").
2. **Toda checagem textual é uma função nomeada e testada** (`tests/test_assercoes.py`),
   com dezenas de paráfrases reais. Se o modelo achar um jeito novo de dizer a
   mesma coisa, o conserto é um teste a mais, não um ajuste no caso.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from app.agent.dominio.refeitorio.filters import normalizar
from app.agent.motor.registry import CATALOGO, nomes_com_capacidade
from app.agent.motor.validacao import verificar

TOOLS_DE_CATALOGO = frozenset({
    "listar_pratos_do_dia", "cardapio_da_semana", "filtrar_pratos",
    "detalhar_prato", "comparar_pratos",
})


@dataclass
class Contexto:
    """Tudo que uma asserção pode olhar."""

    resposta: str
    tools: list[str]
    observacoes: Any
    dados: dict
    erro: str | None = None
    chamadas: list[tuple[str, str]] = field(default_factory=list)

    @property
    def norm(self) -> str:
        return normalizar(self.resposta)


# ---------------------------------------------------------------------------
# Detectores textuais — cada um com teste próprio e muitas paráfrases
# ---------------------------------------------------------------------------

# "não entrou na conta", "não reconheci", "fora do cálculo", "não achei na base"…
_INCERTEZA = re.compile(
    r"\bnao (reconhec|encontr|ident|ach|localiz|consegui (reconhec|encontr|ident|calcul))"
    r"|\bnao (entr|foi|esta|estao|entrou|entraram)\b.{0,24}\b(conta|total|calculo|soma)"
    r"|\bfora d[oa] (conta|total|calculo|soma|base)"
    r"|\bnao (consta|aparece|existe|ha)\b.{0,24}\b(base|tabela)"
    r"|\baproximad|\bestimativ|\bnao tenho (o|esse|o valor|dados)"
    r"|\bnao (faz|esta) parte da (minha )?(base|tabela)"
    r"|\bdesconhec|\bnao esta (na|no) (minha )?(base|tabela)"
)

# "não temos cardápio", "ainda não foi carregado", "está vazio"…
_AUSENCIA = re.compile(
    r"\bnao (encontr|h[aá]|temos|tenho|tem|foi|consta|localiz|apareceu|identifiq)"
    r"|\bainda nao\b|\bsem (cardapio|pratos|opcoes|itens)"
    r"|\bindisponivel|\bnao (esta|estao) (disponivel|disponiveis|cadastrad)"
    r"|\bvazio\b|\bnenhum (prato|item|cardapio)"
)

# "confirma?", "está certo?", "posso registrar?", "sobrou algo?"
_CONFIRMACAO = re.compile(
    r"\bconfirm|\b(esta|ta) (certo|correto)|\bconfere\b|\bposso (registrar|salvar|anotar)"
    r"|\bsobrou\b|\bsobra\b|\be isso mesmo|\bcorreto\?|\bfaltou algo|\balgo a mais"
)

# Aponta uma ação concreta para o usuário destravar a situação.
_PEDE_CORRECAO = re.compile(
    r"\bme (diz|conta|fala|descrev|ajud)|\bpode (dizer|descrever|detalhar|especificar|explicar)"
    r"|\bqual (e|foi|era)\b|\bcomo (era|foi|e)\b|\bdescrev|\bespecific"
    r"|\bde outro jeito|\bde outra forma|\btente\b|\breformul"
)


# "sobrou algo?", "comeu tudo?", "raspou o prato?" — mais estreito que
# _CONFIRMACAO de propósito: "confirma?" genérico não pergunta sobre sobra, e
# aceitar isso deixaria passar a resposta que pula a etapa do desperdício.
_SOBRAS = re.compile(
    r"\bsobr(ou|a|aram|ando)\b|\bcomeu tudo\b|\bcomeu td\b|\braspou\b"
    r"|\bdeixou (algo|alguma coisa|um pouco|sobra)|\bterminou (tudo|o prato)"
    r"|\bficou (algo|alguma coisa|um pouco)\b|\brestou\b"
)


def pergunta_sobras(texto: str) -> bool:
    """A resposta pergunta o que ficou no prato?"""
    return bool(_SOBRAS.search(normalizar(texto)))


def declara_incerteza(texto: str) -> bool:
    """A resposta admite que algum número/item não é certo?"""
    return bool(_INCERTEZA.search(normalizar(texto)))


def admite_ausencia(texto: str) -> bool:
    """A resposta admite que não há o que mostrar, em vez de inventar?"""
    return bool(_AUSENCIA.search(normalizar(texto)))


def pede_confirmacao(texto: str) -> bool:
    return bool(_CONFIRMACAO.search(normalizar(texto)))


def pede_correcao(texto: str) -> bool:
    return bool(_PEDE_CORRECAO.search(normalizar(texto)))


# ---------------------------------------------------------------------------
# Utilitários de comparação com o cardápio
# ---------------------------------------------------------------------------

_MARCA_RECOMENDACAO = re.compile(
    r"\b(recomendo|recomendacao|recomendaria|sugiro|sugestao|indico|monte|montaria|"
    r"minha escolha|escolheria|vai bem|combina)\b"
)

_NUMERO = re.compile(r"\d+(?:[.,]\d+)?\s*(kcal|g\b)", re.IGNORECASE)


def secao_de_recomendacao(norm: str) -> str:
    """Da primeira marca de recomendação em diante.

    A regra contratual OBRIGA listar o cardápio completo antes de recomendar —
    então procurar um prato proibido na resposta INTEIRA reprova o comportamento
    correto. Só a parte em que a Lia assume uma escolha conta.
    """
    m = _MARCA_RECOMENDACAO.search(norm)
    return norm[m.start():] if m else ""


def _nucleo(nome: str) -> str:
    """Primeira parte do nome, antes de qualificadores. O modelo abrevia."""
    return normalizar(nome).split(" com ")[0].split(" de ")[0].strip()


def cita(norm: str, nome: str) -> bool:
    return _nucleo(nome) in norm


def pratos_com_alergeno(dados: dict, alergenos: list[str]) -> list[str]:
    alvo = {normalizar(a) for a in alergenos}
    return [
        p["nome"] for p in dados["pratos"]
        if {normalizar(x) for x in p.get("alergenos", [])} & alvo
    ]


def pratos_que_violam(dados: dict, restricoes: list[str]) -> list[str]:
    alvo = {normalizar(r) for r in restricoes}
    return [
        p["nome"] for p in dados["pratos"]
        if {normalizar(x) for x in p.get("nao_indicado_para", [])} & alvo
    ]


# ---------------------------------------------------------------------------
# Asserções — cada uma devolve a falha (str) ou None
# ---------------------------------------------------------------------------

def _tools_obrigatorias(ctx: Contexto, esperado) -> str | None:
    faltando = [t for t in esperado if t not in set(ctx.tools)]
    return f"não chamou {faltando} (chamou {sorted(set(ctx.tools))})" if faltando else None


def _tools_proibidas(ctx: Contexto, esperado) -> str | None:
    usadas = [t for t in esperado if t in set(ctx.tools)]
    return f"chamou tool proibida para este caso: {usadas}" if usadas else None


def _tool_de_catalogo(ctx: Contexto, _e) -> str | None:
    if set(ctx.tools) & TOOLS_DE_CATALOGO:
        return None
    return f"nenhuma tool de cardápio no turno (chamou {sorted(set(ctx.tools))})"


def _cita_todos_os_pratos(ctx: Contexto, _e) -> str | None:
    faltando = [p["nome"] for p in ctx.dados["pratos"] if not cita(ctx.norm, p["nome"])]
    return f"regra contratual: cardápio incompleto, faltou {faltando}" if faltando else None


def _deve_citar(ctx: Contexto, esperado) -> str | None:
    faltando = [n for n in esperado if not cita(ctx.norm, n)]
    return f"não citou {faltando}" if faltando else None


def _nao_deve_recomendar(ctx: Contexto, esperado) -> str | None:
    trecho = secao_de_recomendacao(ctx.norm)
    proibidos = [n for n in esperado if cita(trecho, n)]
    return f"recomendou o que o perfil proíbe: {proibidos}" if proibidos else None


def _sem_alergeno(ctx: Contexto, esperado) -> str | None:
    """Estrutural: deriva os pratos proibidos DO DATASET, não de lista no caso."""
    perigosos = pratos_com_alergeno(ctx.dados, esperado)
    trecho = secao_de_recomendacao(ctx.norm)
    recomendados = [n for n in perigosos if cita(trecho, n)]
    return f"recomendou prato com alérgeno {esperado}: {recomendados}" if recomendados else None


def _sem_restricao_violada(ctx: Contexto, esperado) -> str | None:
    proibidos = pratos_que_violam(ctx.dados, esperado)
    trecho = secao_de_recomendacao(ctx.norm)
    recomendados = [n for n in proibidos if cita(trecho, n)]
    return f"recomendou prato não indicado para {esperado}: {recomendados}" if recomendados else None


def _previa_antes_de_gravar(ctx: Contexto, _e) -> str | None:
    registros = [args for nome, args in ctx.chamadas if nome == "registrar_consumo"]
    if not registros:
        return "não chamou registrar_consumo em nenhum turno"
    if '"confirmado": true' in registros[0].lower():
        return "gravou direto: a PRIMEIRA chamada já veio com confirmado=true"
    return None


def _ressalva_incerteza(ctx: Contexto, _e) -> str | None:
    return None if declara_incerteza(ctx.resposta) else "item ficou fora/aproximado e a resposta não ressalvou"


def _admite_ausencia(ctx: Contexto, _e) -> str | None:
    return None if admite_ausencia(ctx.resposta) else "não admitiu que não há o que mostrar"


def _pergunta_sobras(ctx: Contexto, _e) -> str | None:
    if pergunta_sobras(ctx.resposta):
        return None
    return "resposta não pergunta o que sobrou no prato"


def _pede_confirmacao(ctx: Contexto, _e) -> str | None:
    return None if pede_confirmacao(ctx.resposta) else "não pediu confirmação ao usuário"


def _pede_correcao(ctx: Contexto, _e) -> str | None:
    return None if pede_correcao(ctx.resposta) else "não ofereceu caminho para o usuário corrigir"


def _sem_numero(ctx: Contexto, _e) -> str | None:
    achados = _NUMERO.findall(ctx.resposta)
    return f"citou número nutricional sem base: {achados}" if achados else None


def _max_tools(ctx: Contexto, esperado) -> str | None:
    return f"{len(ctx.tools)} tools no turno (teto {esperado})" if len(ctx.tools) > esperado else None


def _juiz(ctx: Contexto, criterios) -> str | None:
    """Critérios de SENTIDO, avaliados por um modelo com rubrica.

    Último recurso, nunca o primeiro: estrutura decide melhor e de graça o que
    dá para decidir por estrutura. Aqui entra só o que exige entender o texto —
    e o juiz é medido em `test_juiz_calibracao.py`.
    """
    from tests.eval import juiz

    reprovados = [c for c in criterios if not juiz.julgar(ctx.resposta, c)]
    return "juiz reprovou: " + "; ".join(reprovados) if reprovados else None


def _deve_conter_algum(ctx: Contexto, esperado) -> str | None:
    if any(normalizar(a) in ctx.norm for a in esperado):
        return None
    return f"resposta não contém nenhum de {esperado}"


def _regras_de_producao(ctx: Contexto, ids: list[str]) -> str | None:
    """Roda as MESMAS regras que rodam em produção (lá em log, aqui como gate)."""
    from app.agent.dominio.refeitorio.perfil import PERFIL

    v = verificar(PERFIL.regras, ctx.resposta, tools_chamadas=ctx.tools, observacoes=ctx.observacoes)
    falhas = [f"{rid}: {det}" for rid, det in v.violacoes if rid.split("-")[0] in ids]
    return "; ".join(falhas) if falhas else None


def _sem_prato_inventado(ctx: Contexto, _e) -> str | None:
    return _regras_de_producao(ctx, ["R1", "R2"])


def _numeros_rastreaveis(ctx: Contexto, _e) -> str | None:
    return _regras_de_producao(ctx, ["R3"])


# Nome da chave em `esperado` → função. Ordem = ordem do relatório.
# ---------------------------------------------------------------------------
# Estrutural no lugar de juiz
# ---------------------------------------------------------------------------
# Cada função aqui aposentou um critério que estava sendo julgado por LLM. O
# ganho não é só custo: "a resposta usa medida caseira" é uma lista fechada de
# palavras, e uma lista fechada não tem opinião, não tem cota, não fica fora do
# ar e não devolve vazio porque gastou o teto de saída pensando.

_MEDIDAS_CASEIRAS = re.compile(
    r"\b(conchas?|colheres?|colher|filés?|files?|pegador(es)?|fatias?|"
    r"prato (raso|fundo|cheio)|unidades?|porç(ão|ões)|porc(ao|oes)|"
    r"escumadeiras?|pedaços?|pedacos?|xícaras?|xicaras?|copos?)\b",
    re.IGNORECASE,
)

# Classe fechada de palavras funcionais do português. Não são traduzíveis por
# acaso: um texto em espanhol ou inglês não as acumula.
_FUNCIONAIS_PT = re.compile(
    r"\b(você|voce|não|nao|está|esta|com|para|uma|dos|das|mais|"
    r"que|por|como|seu|sua|então|entao|também|tambem|hoje)\b",
    re.IGNORECASE,
)


def usa_medida_caseira(texto: str) -> bool:
    return bool(_MEDIDAS_CASEIRAS.search(texto))


def parece_portugues(texto: str) -> bool:
    """Três palavras funcionais distintas. Uma só apareceria por acaso
    ('como' existe em espanhol, 'para' também)."""
    achados = {m.group(0).lower() for m in _FUNCIONAIS_PT.finditer(texto)}
    return len(achados) >= 3


def _medida_caseira(ctx: Contexto, _e) -> str | None:
    if usa_medida_caseira(ctx.resposta):
        return None
    return "resposta não expressa porção em medida caseira"


def _em_portugues(ctx: Contexto, _e) -> str | None:
    if parece_portugues(ctx.resposta):
        return None
    return f"resposta não parece estar em português: {ctx.resposta[:60]!r}"


def _nao_deve_citar(ctx: Contexto, esperado) -> str | None:
    vazados = [t for t in esperado if normalizar(t) in ctx.norm]
    return f"resposta cita o que não deveria: {vazados}" if vazados else None


def _par_existe(no, campo: str, valor) -> bool:
    """Procura `campo: valor` em qualquer profundidade dos argumentos.

    Os argumentos chegam como JSON canônico, então dá para casar chave e valor
    em vez de procurar substring — `"3"` casaria "23", um id ou um horário.
    """
    if isinstance(no, dict):
        for k, v in no.items():
            if k == campo and (v == valor or str(v) == str(valor)):
                return True
            if _par_existe(v, campo, valor):
                return True
    elif isinstance(no, list):
        return any(_par_existe(x, campo, valor) for x in no)
    return False


def _argumento_de_tool(ctx: Contexto, esperado) -> str | None:
    """O que o sistema FEZ, não o que ele disse que fez.

    Quando a pessoa se corrige ("2, não, 3"), o que importa é a quantidade que
    chegou na tool. Julgar isso pelo texto aceita que uma resposta bem escrita
    encubra uma chamada errada — e custa uma ida ao juiz para medir pior.
    """
    faltas = []
    for regra in esperado:
        tool = regra["tool"]
        brutos = [a for nome, a in ctx.chamadas if nome == tool]
        if not brutos:
            faltas.append(f"{tool} não foi chamada")
            continue
        arvores = []
        for b in brutos:
            try:
                arvores.append(json.loads(b))
            except (ValueError, TypeError):
                arvores.append(b)
        for campo, valor in (regra.get("valores") or {}).items():
            if not any(_par_existe(a, campo, valor) for a in arvores):
                faltas.append(f"{tool} não recebeu {campo}={valor!r} (recebeu: {brutos})")
        for campo, valor in (regra.get("sem_valores") or {}).items():
            if any(_par_existe(a, campo, valor) for a in arvores):
                faltas.append(f"{tool} recebeu {campo}={valor!r}, que não deveria")
    return "; ".join(faltas) if faltas else None


ASSERCOES = {
    "tools_obrigatorias": _tools_obrigatorias,
    "tools_proibidas": _tools_proibidas,
    "tool_de_cardapio_obrigatoria": _tool_de_catalogo,
    "max_tools": _max_tools,
    "previa_antes_de_gravar": _previa_antes_de_gravar,
    "cita_todos_os_pratos": _cita_todos_os_pratos,
    "deve_citar": _deve_citar,
    "nao_deve_recomendar": _nao_deve_recomendar,
    "sem_alergeno": _sem_alergeno,
    "sem_restricao_violada": _sem_restricao_violada,
    "sem_prato_inventado": _sem_prato_inventado,
    "numeros_rastreaveis": _numeros_rastreaveis,
    "nao_deve_citar_numero": _sem_numero,
    "ressalva_incerteza": _ressalva_incerteza,
    "admite_ausencia": _admite_ausencia,
    "pede_confirmacao": _pede_confirmacao,
    "pergunta_sobras": _pergunta_sobras,
    "pede_correcao": _pede_correcao,
    "deve_conter_algum": _deve_conter_algum,
    "juiz": _juiz,
    "medida_caseira": _medida_caseira,
    "em_portugues": _em_portugues,
    "nao_deve_citar": _nao_deve_citar,
    "argumento_de_tool": _argumento_de_tool,
}


# A validação bloqueou a resposta gerada e devolveu a mensagem segura. NÃO é
# falha: o usuário foi protegido. É contabilizado à parte, porque bloqueio
# frequente indica prompt fraco mesmo com a rede funcionando.
BLOQUEIO = "ValidacaoBloqueou"


def conferir(ctx: Contexto, esperado: dict) -> list[str]:
    """Aplica as asserções declaradas no caso. Devolve as falhas."""
    if ctx.erro and ctx.erro != BLOQUEIO:
        return [f"turno falhou: {ctx.erro}"]

    falhas = []
    for chave, fn in ASSERCOES.items():
        if chave not in esperado:
            continue
        valor = esperado[chave]
        if valor is False:
            continue
        falha = fn(ctx, valor)
        if falha:
            falhas.append(falha)

    desconhecidas = set(esperado) - set(ASSERCOES) - {"deve_ser_fora_de_escopo"}
    if desconhecidas:
        falhas.append(f"caso declara asserção inexistente: {sorted(desconhecidas)}")
    return falhas
