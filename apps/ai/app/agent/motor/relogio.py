"""A hora local do produto — uma fonte só.

Existe porque o mesmo "hoje" é consumido em dois lugares que precisam concordar:
o texto que informa a data ao modelo e as tools que resolvem "hoje"/"amanhã"
contra os dados. Se cada lado chamasse `datetime.now()` com o seu próprio fuso,
às 23h de um dia o prompt diria uma data e a tool consultaria outra — e o bug
apareceria uma vez por dia, à noite, sem ninguém conseguir reproduzir de manhã.

MULTI-TENANT: hoje o fuso é um só, vindo da env. Numa instalação que atenda
vários tenants isso passa a ser errado — dois locais em fusos diferentes viram o
dia em horas diferentes, e "o de hoje" sai trocado para um deles. O ponto de
escopo é `contexto`: quando existir fuso por tenant, `hoje()` passa a recebê-lo e
lê de lá, e nada mais neste módulo muda.
"""

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app import config

_DIAS = (
    "segunda-feira", "terça-feira", "quarta-feira",
    "quinta-feira", "sexta-feira", "sábado", "domingo",
)
_MESES = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)


def fuso() -> ZoneInfo:
    return ZoneInfo(config.FUSO_HORARIO)


def agora() -> datetime:
    return datetime.now(fuso())


def hoje() -> date:
    return agora().date()


def por_extenso(d: date | None = None) -> str:
    """"quinta-feira, 27 de agosto de 2026".

    Data por extenso e não ISO porque é o formato que o modelo erra menos ao
    fazer aritmética de calendário, e o dia da semana vem junto porque metade
    das perguntas é sobre ele ("o que tem na quarta?"). Sem hora: hora dentro
    do prompt mudaria o texto a cada chamada e derrubaria o cache de prefixo
    dos providers que o oferecem, comprando ruído por precisão que não usamos.
    """
    d = d or hoje()
    return f"{_DIAS[d.weekday()]}, {d.day} de {_MESES[d.month - 1]} de {d.year}"
