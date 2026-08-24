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

    @property
    def nomes_chamados(self) -> list[str]:
        return [nome for nome, _ in self.chamadas]

    def ja_chamou(self, chave: tuple[str, str]) -> bool:
        return chave in self.chamadas

    def registrar(self, chave: tuple[str, str], resultado) -> None:
        self.chamadas.append(chave)
        if isinstance(resultado, dict) and resultado.get(CHAVE_NOTA):
            self.avisos.append(str(resultado[CHAVE_NOTA]))
        self._colher(resultado)

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

    def prazo_esgotado(self) -> bool:
        return self.prazo is not None and time.monotonic() >= self.prazo


_estado: contextvars.ContextVar[EstadoDoTurno | None] = contextvars.ContextVar(
    "estado_do_turno", default=None
)


def iniciar_turno(prazo: float | None = None, reminders: tuple[str, ...] = ()) -> contextvars.Token:
    return _estado.set(EstadoDoTurno(prazo=prazo, reminders=tuple(reminders)))


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


def _args_canonicos(args: tuple, kwargs: dict) -> str:
    """Assinatura estável dos argumentos, para detectar chamada repetida."""
    try:
        return json.dumps({"a": list(args), "k": kwargs}, sort_keys=True, default=str)
    except Exception:
        return repr((args, sorted(kwargs.items())))


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

        chave = (fn.__name__, _args_canonicos(args, kwargs))
        if config.COMPRIMIR_REPETICOES and estado.observacoes.ja_chamou(chave):
            log.info("TOOL repetida | %s | devolvendo marcador", fn.__name__)
            return TEXTO_JA_CONSULTADO

        resultado = fn(*args, **kwargs)
        estado.observacoes.registrar(chave, resultado)
        return _reinjetar(resultado, estado.reminders)

    return wrapper
