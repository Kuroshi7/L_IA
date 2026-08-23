"""Contrato entre o motor e um domínio de produto.

O motor é reutilizável para aplicações conversacionais *agentic* — com tools,
contexto, validação e RAG. Ele NÃO é um framework genérico para qualquer sistema
de IA: quanto mais genérico, mais interface artificial aparece, e interface
artificial custa manutenção sem entregar reuso.

`PerfilDeDominio` é a única superfície que o motor enxerga. Trocar de produto
significa escrever outro perfil — nenhuma linha de `motor/` muda.

Os campos entram conforme ganham consumidor, nunca por simetria: um campo que
ninguém lê é exatamente a interface artificial que queremos evitar. Hoje o motor
consome estes seis; `reminders` e `regras` chegam junto com o código que os usa.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.agent.motor.reminders import Gatilhos, Reminder
from app.agent.motor.registry import ToolSpec


@dataclass(frozen=True)
class PerfilDeDominio:
    nome: str

    # Persona e regras do produto. Texto puro — o motor não interpreta, só posiciona.
    system_prompt: str

    # Tools que o domínio expõe, com os metadados que o motor usa para montar
    # o conjunto de cada requisição.
    registro: Sequence[ToolSpec]

    # Filtro de escopo do domínio. Recebe (texto, tem_historico) e diz se a
    # mensagem merece resposta. Fica no domínio porque só o produto sabe o que
    # está dentro do seu assunto.
    esta_no_escopo: Callable[[str, bool], bool]

    resposta_fora_de_escopo: str
    resposta_erro_transiente: str

    # Traduz as condições do turno nas instruções que vão para o fim do contexto.
    reminders: Callable[[Gatilhos], Sequence[Reminder]] = lambda _g: ()

    # Regras de validação pós-resposta, como (id, funcao).
    regras: Sequence[tuple[str, Callable]] = ()
