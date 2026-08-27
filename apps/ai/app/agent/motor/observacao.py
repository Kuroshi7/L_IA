"""Estado do turno e interceptação das tools.

Duas responsabilidades, juntas porque compartilham o mesmo ContextVar:

1. **Estado do turno** — cache de leitura e observações do que as tools
   devolveram. O motor mantém o SEU estado num ContextVar próprio, separado do
   contexto do domínio: o motor trata o contexto de domínio como opaco e nunca o
   introspecciona (é isso que o mantém reaproveitável no próximo produto).

2. **`@observado`** — decorator que envolve a função da tool. Três alternativas
   foram consideradas:
     - callback do LangChain (`on_tool_end`): só vê a string já serializada e
       não pode alterá-la;
     - middleware do agente: superfície não coberta pelos testes deste repo;
     - decorator: código nosso, testável sem LLM, idêntico nos dois providers.

   O decorator ganha de graça uma propriedade que vale muito: o resultado de uma
   tool é a ÚLTIMA mensagem do contexto antes da inferência seguinte. Um sufixo
   nesse resultado é, na prática, uma instrução no fim do contexto — a posição
   com maior taxa de obediência do modelo.

ORDEM DOS DECORATORS (importa): `@tool` por fora, `@observado` por dentro.
`functools.wraps` preserva `__wrapped__`, então o `inspect.signature` que o
`@tool` usa continua enxergando a assinatura original. Há teste para isso.
"""

import contextvars
import functools
import inspect
import json
import logging
import time
import unicodedata
from dataclasses import dataclass, field

from app import config

log = logging.getLogger("agent")

# Campo que identifica um item nos retornos das tools. Uma única constante do
# motor em vez de um campo configurável no perfil: não se extrai abstração com um
# consumidor só. Vira campo do perfil quando um segundo domínio precisar de outro.
CHAVE_NOME = "nome"

# Chaves cujos números NÃO são valores expostos ao usuário (identificadores).
# Sem isso, um `id: 3` viraria "3" na lista de números que a resposta pode citar.
_CHAVES_NAO_NUMERICAS = ("id",)

# Devolvido no lugar do corpo quando a MESMA tool é chamada com os MESMOS
# argumentos duas vezes no turno. Preserva a informação (os argumentos ficam no
# histórico) e corta o custo (o corpo, que pode ser a tabela inteira). De quebra,
# freia o loop que o recursion_limit só corta lá no fim.
TEXTO_JA_CONSULTADO = (
    "Esta consulta já foi feita neste turno com os mesmos argumentos. "
    "Use o resultado anterior em vez de consultar de novo."
)

# Campo que uma tool usa para pedir algo ao modelo junto do resultado.
CHAVE_NOTA = "nota_do_sistema"

# Anexado quando a MESMA consulta já tinha voltado sem resultado num turno
# ANTERIOR desta conversa e acaba de voltar sem resultado de novo.
#
# Não reaproveita o TEXTO_JA_CONSULTADO de propósito: aquele manda usar o
# resultado anterior, e entre turnos o resultado anterior não está mais no
# contexto — seria mandar o modelo usar algo que ele não pode ver.
#
# A última oração é defesa contra o pior sintoma medido no baseline: sem ela o
# modelo parafraseia o mecanismo para quem está do outro lado ("o sistema está
# muito rigoroso"), que é vazar tripa do sistema para o usuário final.
#
# O texto fala de "outro caminho", e não de critérios de busca: quem cai aqui
# pode ser uma leitura que não achou nada ou uma chamada recusada por argumento
# inválido, e a mesma frase precisa servir às duas.
#
# A versão anterior abria com "Mude os argumentos". Num domínio em que os
# argumentos de uma chamada SÃO a barreira de segurança verificada em código,
# isso é autorizar o modelo a derrubá-la — na última posição do contexto, que é
# a de maior obediência — para se livrar de um retorno vazio. Quem pode
# afrouxar um critério é a pessoa que o declarou, e a frase agora manda
# perguntar a ela.
TEXTO_SEM_SAIDA = (
    "Esta mesma chamada, com estes mesmos argumentos, já voltou sem resultado "
    "antes nesta conversa — repetir do mesmo jeito não vai mudar. Tente outro "
    "caminho ou pergunte à pessoa o que dá para ajustar; NÃO descarte por conta "
    "própria um critério que ela declarou. Fale do que faltou, nunca do "
    "funcionamento interno do sistema."
)


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return " ".join(sem_acento.lower().split())


@dataclass
class ObservacoesDoTurno:
    """O que as tools devolveram neste turno — matéria-prima da validação.

    `itens_conhecidos` e `valores_expostos` são separados de propósito. Nem toda
    tool que cita um item expõe os números dele: uma tool de listagem pode
    devolver só nome e categoria. Se a validação usasse uma coisa só, um número
    inventado passaria batido sempre que a listagem tivesse sido chamada.
    """

    chamadas: list[tuple[str, str]] = field(default_factory=list)
    itens_conhecidos: dict[str, dict] = field(default_factory=dict)
    valores_expostos: set[float] = field(default_factory=set)
    # Toda string que apareceu num retorno de tool (nomes, categorias,
    # alérgenos, ingredientes). Serve para não acusar de "inventado" um
    # termo que o modelo leu do próprio resultado — ex.: **lactose**, que
    # veio da lista de alérgenos e não é nome de item.
    termos_vistos: set[str] = field(default_factory=set)
    avisos: list[str] = field(default_factory=list)

    # Chaves cujo retorno não trouxe NEM item NEM número — a consulta rodou e
    # não achou nada. É a única coisa deste estado que atravessa o turno
    # (`motor/memoria.py`), e por isso guarda só a chave, nunca o corpo.
    sem_resultado: list[tuple[str, str]] = field(default_factory=list)

    @property
    def nomes_chamados(self) -> list[str]:
        return [nome for nome, _ in self.chamadas]

    def ja_chamou(self, chave: tuple[str, str]) -> bool:
        return chave in self.chamadas

    def registrar(self, chave: tuple[str, str], resultado) -> bool:
        """Funde o retorno no estado do turno. Devolve True se a chamada não
        achou nada — o chamador usa isso para decidir se anota o retorno."""
        self.chamadas.append(chave)
        if isinstance(resultado, dict) and resultado.get(CHAVE_NOTA):
            self.avisos.append(str(resultado[CHAVE_NOTA]))

        # Colhe primeiro num coletor descartável para medir o DELTA DESTA
        # chamada, e só depois funde. Medir sobre o acumulado mentiria: uma
        # segunda consulta que devolve itens já vistos apenas sobrescreveria
        # chaves em `itens_conhecidos`, o tamanho não mudaria e ela pareceria
        # não ter trazido nada — o motor passaria a marcar como morto um
        # caminho que funciona.
        delta = ObservacoesDoTurno()
        delta._colher(resultado)
        self.itens_conhecidos.update(delta.itens_conhecidos)
        self.valores_expostos |= delta.valores_expostos
        self.termos_vistos |= delta.termos_vistos

        # Deliberadamente conservador: "payload ESTRUTURADO, nem item nem
        # número". É o que mantém fora daqui as tools que devolvem contagem ou
        # saldo (inclusive a listagem que responde `total: 0`) e as de escrita,
        # que confirmam com números. Falso negativo custa o comportamento de
        # hoje; falso positivo ensinaria ao modelo que um caminho vivo está morto.
        #
        # Retorno em TEXTO nunca entra. `_colher` não extrai item nem número de
        # uma string, então todo retorno de texto era classificado como morto —
        # inclusive os de SUCESSO: a prosa que a busca devolve quando ACHA, e a
        # resposta correta e estável de uma consulta sem argumentos (que, sendo
        # sem argumentos, repete a mesma chave em todo turno e recebe o aviso
        # para "tentar outro caminho" indefinidamente). Era exatamente o falso
        # positivo que o parágrafo acima diz evitar. O motor não tem como ler
        # "não achei" dentro de um texto livre sem saber do que o texto fala —
        # e saber isso é do domínio, não daqui; então texto é tratado como
        # conteúdo, e só payload estruturado pode ser declarado vazio.
        vazia = (
            not isinstance(resultado, str)
            and not delta.itens_conhecidos
            and not delta.valores_expostos
        )
        if vazia:
            self.sem_resultado.append(chave)
        return vazia

    def _colher(self, valor, dentro_de_item: bool = False) -> None:
        """Percorre o retorno da tool colhendo itens e números.

        Genérico de propósito: "todo dict com um campo `nome` é um item; todo
        número no payload foi exposto ao modelo". O motor não sabe o que os
        itens representam.
        """
        if isinstance(valor, dict):
            eh_item = isinstance(valor.get(CHAVE_NOME), str)
            if eh_item:
                self.itens_conhecidos[_normalizar(valor[CHAVE_NOME])] = valor
            for chave, sub in valor.items():
                if chave in _CHAVES_NAO_NUMERICAS or chave.endswith("_id"):
                    continue
                self._colher(sub, dentro_de_item=eh_item or dentro_de_item)
        elif isinstance(valor, str):
            texto = _normalizar(valor)
            if 0 < len(texto) <= 60:
                self.termos_vistos.add(texto)
        elif isinstance(valor, (list, tuple)):
            for sub in valor:
                self._colher(sub, dentro_de_item=dentro_de_item)
        elif isinstance(valor, bool):
            return  # bool é subclasse de int; não é valor numérico exposto
        elif isinstance(valor, (int, float)):
            self.valores_expostos.add(float(valor))


class PrazoEsgotado(Exception):
    """O tempo de quem esperava a resposta acabou; não vale a pena continuar."""


@dataclass
class EstadoDoTurno:
    cache: dict = field(default_factory=dict)
    observacoes: ObservacoesDoTurno = field(default_factory=ObservacoesDoTurno)

    # Instante (relógio monotônico) em que quem pediu já desistiu. None = sem
    # prazo, comportamento de sempre.
    prazo: float | None = None

    # Reminders ativos neste turno, para REINJEÇÃO. Eles entram no fim da
    # mensagem do usuário, mas deixam de ser a última coisa do contexto assim
    # que a primeira tool responde — e é depois disso que a resposta é gerada.
    # Reanexá-los ao resultado das tools devolve a instrução à posição que
    # funciona. Medido: a regra de encaminhar a profissional de saúde tinha 0
    # de 3 de aderência só com a injeção inicial.
    reminders: tuple[str, ...] = ()

    # Consultas que já voltaram sem resultado em turnos ANTERIORES desta
    # conversa (`motor/memoria.py`). Vazio = comportamento de sempre.
    sem_resultado_antes: frozenset = frozenset()

    def prazo_esgotado(self) -> bool:
        return self.prazo is not None and time.monotonic() >= self.prazo


_estado: contextvars.ContextVar[EstadoDoTurno | None] = contextvars.ContextVar(
    "estado_do_turno", default=None
)


def iniciar_turno(
    prazo: float | None = None,
    reminders: tuple[str, ...] = (),
    sem_resultado_antes: frozenset = frozenset(),
) -> contextvars.Token:
    return _estado.set(
        EstadoDoTurno(
            prazo=prazo,
            reminders=tuple(reminders),
            sem_resultado_antes=frozenset(sem_resultado_antes),
        )
    )


def encerrar_turno(token: contextvars.Token) -> None:
    _estado.reset(token)


def estado_do_turno() -> EstadoDoTurno | None:
    """None fora de um turno. Tolerante de propósito: as tools continuam
    utilizáveis direto (teste, script, REPL) sem precisar montar estado."""
    return _estado.get()


def cache_do_turno() -> dict | None:
    estado = _estado.get()
    return estado.cache if estado else None


def observacoes_do_turno() -> ObservacoesDoTurno | None:
    estado = _estado.get()
    return estado.observacoes if estado else None


def _args_canonicos(fn, args: tuple, kwargs: dict) -> str:
    """Assinatura estável dos argumentos, para reconhecer a MESMA consulta.

    Liga os argumentos à assinatura da função e aplica os defaults antes de
    serializar. Sem isso a chave é a FORMA da chamada, não o seu conteúdo:
    `f("x")` e `f(criterio="x")` viram chaves diferentes, e omitir um parâmetro
    com default vira chave diferente de passá-lo explícito. Isso já enfraquecia
    a compressão dentro do turno; entre turnos seria fatal, porque um turno
    quase nunca reproduz a forma exata do turno anterior — a memória nasceria
    inútil.

    Fallback para a forma crua porque a assinatura pode não ser inspecionável
    (built-in, chamável exótico): uma otimização não pode derrubar um turno.
    """
    try:
        ligado = inspect.signature(fn).bind(*args, **kwargs)
        ligado.apply_defaults()
        bruto = dict(ligado.arguments)
    except Exception:
        bruto = {"a": list(args), "k": kwargs}
    try:
        return json.dumps(bruto, sort_keys=True, default=str)
    except Exception:
        return repr(sorted(bruto.items()))


def _anotar_sem_saida(resultado):
    """Anexa ao retorno o aviso de que esta consulta já morreu antes.

    Aqui a nota da tool NÃO tem precedência exclusiva como em `_reinjetar`: lá
    o reminder é genérico e pode contradizer a nota concreta; aqui as duas
    dizem a mesma coisa ("não veio nada"), então empilhar não gera contradição
    — e apagar a nota da tool perderia a orientação específica dela.

    Retorno de lista fica intacto pelo mesmo motivo de `_reinjetar`: mudar o
    formato de uma lista confunde modelo pequeno.
    """
    if isinstance(resultado, dict):
        atual = str(resultado.get(CHAVE_NOTA) or "").strip()
        nota = f"{atual}\n{TEXTO_SEM_SAIDA}" if atual else TEXTO_SEM_SAIDA
        return {**resultado, CHAVE_NOTA: nota}
    if isinstance(resultado, str):
        return f"{resultado}\n\n{TEXTO_SEM_SAIDA}"
    return resultado


def _reinjetar(resultado, reminders: tuple[str, ...]):
    """Reanexa os reminders do turno ao resultado da tool.

    Só em retorno que já é dict, e sem apagar nota que a própria tool colocou.
    Mexer no formato de um retorno de lista confunde modelo pequeno, e o ganho
    não compensa.
    """
    if not reminders or not isinstance(resultado, dict):
        return resultado

    # Nota da própria tool tem PRECEDÊNCIA. Ela conhece a situação concreta —
    # inclusive o caso degenerado, em que o resultado veio vazio — enquanto o
    # reminder é genérico e foi escrito para o caso normal. Empilhadas, as duas
    # chegaram a se contradizer, e o modelo resolveu a contradição inventando
    # dado. Empilhar também alonga a instrução, e instrução longa dilui: medimos
    # a aderência da regra principal do domínio cair de 89% para 61% quando o
    # texto cresceu.
    if resultado.get(CHAVE_NOTA):
        return resultado
    return {**resultado, CHAVE_NOTA: "\n".join(reminders)}


def observado(fn):
    """Registra a chamada e o retorno da tool no estado do turno."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        estado = estado_do_turno()
        if estado is None:
            return fn(*args, **kwargs)

        # Toda tool passa por aqui, então este é o ponto natural para checar o
        # prazo — sem inventar um segundo mecanismo de interceptação. Um turno
        # pode encadear várias chamadas de modelo e estourar o tempo de quem
        # espera; continuar depois disso só queima token de resposta que
        # ninguém vai ler e prende o worker (prefetch=1) para o próximo da fila.
        if estado.prazo_esgotado():
            log.warning("PRAZO esgotado antes de %s — abortando o turno", fn.__name__)
            raise PrazoEsgotado(fn.__name__)

        chave = (fn.__name__, _args_canonicos(fn, args, kwargs))
        if config.COMPRIMIR_REPETICOES and estado.observacoes.ja_chamou(chave):
            log.info("TOOL repetida | %s | devolvendo marcador", fn.__name__)
            # Os reminders vão junto. A chave por conteúdo (`_args_canonicos`)
            # alargou o alcance da compressão: chamadas que antes executavam e
            # devolviam corpo + reminder reinjetado agora param aqui, e sem esta
            # linha a última mensagem antes da inferência seria um marcador seco
            # — perdendo justamente a instrução cuja aderência sem reinjeção foi
            # medida em 0 de 3 (ver `EstadoDoTurno.reminders`).
            if estado.reminders:
                return TEXTO_JA_CONSULTADO + "\n\n" + "\n".join(estado.reminders)
            return TEXTO_JA_CONSULTADO

        resultado = fn(*args, **kwargs)
        vazia = estado.observacoes.registrar(chave, resultado)

        # ANOTAR, não bloquear: a tool roda de verdade sempre. Se o que se
        # consulta mudou desde o turno passado, o modelo recebe o resultado real
        # e nenhuma nota; a nota só existe quando as duas execuções concordam
        # que não há nada ali. Assim é impossível esta memória impedir uma
        # consulta que hoje funcionaria — ou uma escrita legítima.
        #
        # A anotação vem DEPOIS da reinjeção, não antes: escrevendo primeiro na
        # `nota_do_sistema` este aviso engoliria os reminders do turno, porque
        # `_reinjetar` cede a vez para qualquer nota já presente. Assim o
        # comportamento de hoje fica idêntico enquanto o modelo não repete um
        # caminho morto, e no caso raro em que repete são no máximo dois textos
        # empilhados — nunca três.
        resultado = _reinjetar(resultado, estado.reminders)
        if vazia and chave in estado.sem_resultado_antes:
            log.info("TOOL sem saída conhecida | %s | anotando o retorno", fn.__name__)
            resultado = _anotar_sem_saida(resultado)
        return resultado

    return wrapper
