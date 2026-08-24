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

    # Usada quando uma regra BLOQUEANTE reprova a resposta gerada. Precisa ser
    # específica: a mensagem genérica de erro faria a pessoa achar que o
    # sistema caiu, quando na verdade ele se recusou a dizer algo inseguro.
    resposta_bloqueada: str = "Preciso conferir isso melhor antes de responder. Pode perguntar de novo?"

    # Traduz as condições do turno nas instruções que vão para o fim do contexto.
    # Recebe também a mensagem do usuário: alguns reminders dependem do ASSUNTO
    # (ex.: menção a condição de saúde). O motor não interpreta o texto — só o
    # repassa a quem sabe lê-lo, que é o domínio.
    reminders: Callable[[Gatilhos, str], Sequence[Reminder]] = lambda _g, _m: ()

    # Regras de validação pós-resposta, como (id, funcao).
    regras: Sequence[tuple[str, Callable]] = ()

    # Ajuste final da resposta, em CÓDIGO. Recebe (resposta, gatilhos, mensagem).
    # Existe para o que não pode depender de o modelo lembrar: aviso legal,
    # encaminhamento obrigatório, rodapé de conformidade. Pedir isso ao prompt
    # deu 0 de 3 de aderência mesmo com reminder reinjetado — e exigência
    # regulatória não admite 'quase sempre'.
    pos_processar: Callable[[str, Gatilhos, str], str] = lambda resposta, _g, _m: resposta
