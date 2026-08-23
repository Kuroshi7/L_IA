"""Instruções entregues no FIM do contexto.

Por que no fim: a mesma instrução no system prompt é seguida com frequência
muito menor do que quando aparece como última coisa antes da geração. O modelo
atende com muito mais força ao que está colado no ponto de decisão. Regra de
negócio crítica no meio de um system prompt longo é regra que se perde.

INVARIANTE DE SEGURANÇA — um reminder só pode REPETIR uma regra que já existe no
system prompt do domínio. Nunca introduzir capacidade, permissão ou dado novo.

É isso que concilia a posição (fim do contexto, canal do usuário) com o fato de
esse canal ser spoofável: se o reminder só repete o que o system já autoriza, o
pior que um atacante consegue escrevendo "NOTA DO SISTEMA: ..." é repetir uma
regra que já valia. A autoridade continua sendo exclusivamente do system prompt.

`regra_de_origem` existe para tornar a invariante VERIFICÁVEL: há teste que exige
que essa âncora apareça literalmente no system prompt do perfil.
"""

from dataclasses import dataclass

CABECALHO = "[NOTA DO SISTEMA — gerada pelo servidor, não é texto do usuário]"


@dataclass(frozen=True)
class Reminder:
    nome: str
    texto: str
    regra_de_origem: str


@dataclass(frozen=True)
class Gatilhos:
    """Condições do turno que o domínio traduz em reminders.

    Genérico de propósito: o motor sabe que existe "primeira interação do dia",
    não o que o produto faz com isso.
    """

    primeira_interacao_do_dia: bool = False


def render(reminders) -> str:
    corpo = "\n".join(r.texto for r in reminders)
    return f"{CABECALHO}\n{corpo}"


def anexar(mensagem: str, reminders) -> str:
    """Funde os reminders no fim da mensagem do usuário.

    Poderia ser uma mensagem separada, mas `SystemMessage` fora da posição 0 não
    é portável entre providers e mensagens de usuário consecutivas dependem de
    merge de cada um. Fundir é um caminho de código só, igual nos dois providers,
    e preserva o que importa: o texto fica literalmente por último.
    """
    if not reminders:
        return mensagem
    return f"{mensagem}\n\n---\n{render(reminders)}"


def anexar_ao_resultado(resultado, nota: str):
    """Acrescenta uma instrução ao resultado de uma tool.

    É a mesma ideia do reminder no fim do contexto, aplicada no melhor ponto
    disponível durante o turno: o retorno de uma tool é a última mensagem antes
    da próxima inferência. Uma instrução colada ali é obedecida muito mais do que
    a mesma frase perdida no system prompt.

    Só mexe em retorno que já é dict. Alterar o formato de um retorno de lista
    confunde modelos pequenos, e o ganho não compensa.
    """
    if not nota or not isinstance(resultado, dict):
        return resultado
    return {**resultado, "nota_do_sistema": nota}
