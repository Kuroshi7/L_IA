"""A memória de becos sem saída não pode marcar como morto o que veio vivo.

Três defeitos do mecanismo de `motor/observacao.py`, achados na revisão. Todos
atacam a garantia que o próprio módulo declara — "é impossível esta memória
impedir uma consulta viva":

1. TEXTO ERA SEMPRE "VAZIO". `_colher` não extrai item nem número de uma string,
   e `vazia` olhava só essas duas coisas. Então TODO retorno em texto era
   gravado como beco — inclusive os de SUCESSO. Uma consulta sem argumentos
   produz a MESMA chave em todo turno, e a partir do segundo o modelo recebia a
   resposta correta com um selo do servidor dizendo que ela veio vazia.

2. O AVISO MANDAVA MEXER NOS ARGUMENTOS. Num domínio em que os argumentos de uma
   chamada são a barreira de segurança verificada em código, isso é autorizar o
   modelo a derrubá-la para se livrar de um retorno vazio — na última posição do
   contexto, que é a de maior obediência.

3. A COMPRESSÃO ENGOLIA O REMINDER. O ramo que devolve o marcador de repetição
   retornava antes da reinjeção, e a última coisa antes da inferência virava um
   marcador seco — sem a instrução cuja aderência sem reinjeção foi medida em
   0 de 3.

Tudo aqui roda sobre tools FALSAS: o comportamento em teste é do motor.
"""

from langchain_core.tools import tool

from app import config
from app.agent.motor.observacao import (
    CHAVE_NOTA,
    TEXTO_JA_CONSULTADO,
    TEXTO_SEM_SAIDA,
    ObservacoesDoTurno,
    encerrar_turno,
    iniciar_turno,
    observado,
)

# O texto longo importa: `_colher` só recolhe strings de até 60 caracteres, então
# a prosa de sucesso de uma busca não deixava rastro nenhum no estado do turno.
PROSA_DE_SUCESSO = (
    "Uma concha média de arroz corresponde a cerca de quatro colheres de sopa "
    "cheias, o que equivale a uma porção padrão nas tabelas de medida caseira."
)
TEXTO_CURTO_CORRETO = "Não identificado nesta sessão — pergunte diretamente."


# --- 1. texto é conteúdo, não ausência de resultado ---------------------------

def test_retorno_em_texto_nunca_e_beco_sem_saida():
    obs = ObservacoesDoTurno()
    assert obs.registrar(("buscar", "a"), PROSA_DE_SUCESSO) is False
    assert obs.registrar(("perfil", "{}"), TEXTO_CURTO_CORRETO) is False
    assert obs.sem_resultado == []


def test_payload_estruturado_vazio_continua_sendo_beco():
    # O outro lado: o mecanismo tinha que continuar existindo. Se isto passar a
    # devolver False, a memória entre turnos nasceu morta.
    obs = ObservacoesDoTurno()
    assert obs.registrar(("consultar", "a"), {"itens": [], CHAVE_NOTA: "nada aqui"}) is True
    assert obs.registrar(("consultar", "b"), []) is True
    assert obs.sem_resultado == [("consultar", "a"), ("consultar", "b")]


def test_contagem_e_saldo_continuam_fora():
    # Regressão do guard já existente: tool de escrita/saldo confirma com número.
    obs = ObservacoesDoTurno()
    assert obs.registrar(("saldo", "{}"), {"total": 0}) is False


def test_consulta_sem_argumentos_nao_se_auto_condena():
    """O caso mais frequente do produto, e o mais silencioso.

    Uma tool sem argumentos tem chave idêntica em todo turno da conversa. Se a
    resposta dela (texto, correta, estável) contasse como beco, do segundo turno
    em diante o modelo leria a resposta certa seguida de "mude os argumentos" —
    para uma tool que não tem argumentos.
    """
    chamadas = []

    @observado
    def sondar() -> str:
        chamadas.append(1)
        return TEXTO_CURTO_CORRETO

    chave = ("sondar", "{}")
    token = iniciar_turno(sem_resultado_antes=frozenset({chave}))
    try:
        saida = sondar()
    finally:
        encerrar_turno(token)

    assert saida == TEXTO_CURTO_CORRETO
    assert TEXTO_SEM_SAIDA not in saida
    assert chamadas == [1]


# --- 2. o aviso não autoriza afrouxar o que a pessoa declarou ------------------

def test_aviso_de_beco_nao_manda_mexer_nos_argumentos():
    # Os argumentos de uma chamada podem ser a única barreira determinística do
    # turno. Quem pode abrir mão de um critério é quem o declarou.
    baixo = TEXTO_SEM_SAIDA.lower()
    assert "mude os argumentos" not in baixo
    assert "não descarte por conta própria um critério que ela declarou" in baixo
    assert "pergunte à pessoa" in baixo


# --- 3. a compressão não pode custar o reminder --------------------------------

def test_marcador_de_repeticao_carrega_os_reminders(monkeypatch):
    monkeypatch.setattr(config, "COMPRIMIR_REPETICOES", True)

    @tool
    @observado
    def consultar(criterio: str = "") -> dict:
        """Consulta qualquer coisa."""
        return {"itens": [{"nome": "Item A"}]}

    lembrete = "Encaminhe a pessoa a um profissional antes de responder."
    token = iniciar_turno(reminders=(lembrete,))
    try:
        consultar.invoke({"criterio": "x"})
        repetida = consultar.invoke({"criterio": "x"})
    finally:
        encerrar_turno(token)

    assert TEXTO_JA_CONSULTADO in repetida
    assert lembrete in repetida


def test_sem_reminder_o_marcador_continua_seco(monkeypatch):
    monkeypatch.setattr(config, "COMPRIMIR_REPETICOES", True)

    @observado
    def sondar(criterio: str = "") -> dict:
        return {"itens": [{"nome": "Item A"}]}

    token = iniciar_turno()
    try:
        sondar("x")
        repetida = sondar("x")
    finally:
        encerrar_turno(token)

    assert repetida == TEXTO_JA_CONSULTADO
