"""Juiz LLM para os critérios que estrutura e regex não decidem.

Quando usar: só quando o requisito é sobre SENTIDO do que a pessoa leu — "a Lia
explicou POR QUE recomendou aquele prato?", "o tom acolheu em vez de julgar?".
Para "chamou a tool X" ou "citou um prato que não existe", estrutura decide
melhor, de graça e sem variância.

Como este juiz evita os defeitos clássicos:

- **Rubrica antes do veredicto.** O critério vem com o que conta como SIM e o que
  conta como NÃO. Juiz sem rubrica vira medidor de simpatia e aprova quase tudo.
- **Binário, com viés declarado para NÃO.** Na dúvida reprova. Um eval que erra
  para o lado permissivo não protege nada.
- **temperature=0 e resposta de 3 tokens.** O juiz não escreve redação.
- **Não vê o gabarito nem o resto da conversa.** Só o texto e o critério — senão
  ele racionaliza a favor do que já está lá.
- **É calibrado.** `test_juiz_calibracao.py` mede o juiz contra respostas boas e
  ruins conhecidas. Juiz não medido é opinião com custo de API.
"""

import logging
import os
import re

from app import config

log = logging.getLogger("juiz")

SYSTEM = """Você avalia se a resposta de um assistente de refeitório cumpre UM critério.

Regras da avaliação:
- Responda SOMENTE com SIM ou NAO. Nenhuma outra palavra.
- SIM apenas se a resposta cumpre o critério de forma clara e verificável no texto.
- Na dúvida, responda NAO. É preferível reprovar uma resposta boa a aprovar uma ruim.
- Julgue APENAS o critério pedido. Ignore tom, formatação, emojis e qualquer outra qualidade.
- Não suponha intenção: se o critério exige que algo esteja dito, precisa estar escrito."""

_MODELO = None


def _modelo():
    """Instância dedicada: temperatura 0 e saída mínima. Reaproveitar o LLM do
    agente traria temperatura 0.3 e as tools no contexto."""
    global _MODELO
    if _MODELO is None:
        from app.agent.motor import provedores

        # EVAL_JUIZ_PROVIDER/_MODELO desacoplam o juiz do agente. Sem isso,
        # medir o agente em outro provider trocava o juiz junto — e um juiz não
        # calibrado, com falha fechada, reprova o que não consegue julgar.
        # O _MODELO importa mesmo com um provider só: num provider que serve
        # muitas famílias, "mesmo provider" não significa mais "mesmo modelo",
        # e é o modelo que precisa ser fixo e diferente do avaliado.
        _MODELO = provedores.construir(
            temperatura=0, max_tokens=4,
            provider=os.getenv("EVAL_JUIZ_PROVIDER") or None,
            modelo=os.getenv("EVAL_JUIZ_MODELO") or None,
        )
    return _MODELO


_cache: dict[tuple[str, str], bool] = {}

# Motivos pelos quais o juiz não conseguiu julgar. Separado do veredicto de
# propósito: "reprovado" e "não consegui avaliar" são a mesma saída (False) e
# leituras opostas. Sem esta lista, cota estourada lê como produto ruim — foi
# o que aconteceu: 50 requisições/dia esgotadas, todo o lote em 429, e a
# calibração reportou 53% de acurácia de um juiz que nunca respondeu.
INDISPONIVEIS: list[str] = []


def limpar() -> None:
    _cache.clear()
    INDISPONIVEIS.clear()


def julgar(resposta: str, criterio: str) -> bool:
    """True se a resposta cumpre o critério. Fail-CLOSED: erro do juiz reprova.

    O contrário deixaria o eval verde quando o juiz caísse — o pior modo de
    falha possível para um gate.
    """
    chave = (criterio, resposta)
    if chave in _cache:
        return _cache[chave]

    prompt = f"CRITÉRIO:\n{criterio}\n\nRESPOSTA DO ASSISTENTE:\n\"\"\"\n{resposta}\n\"\"\"\n\nSIM ou NAO?"
    try:
        saida = _modelo().invoke([("system", SYSTEM), ("human", prompt)])
        texto = getattr(saida, "content", str(saida))
        if isinstance(texto, list):  # blocos do Anthropic
            texto = "".join(b.get("text", "") for b in texto if isinstance(b, dict))
        texto = texto.strip()
        if not re.match(r"\s*(sim|nao|não)\b", texto, re.IGNORECASE):
            # Nem SIM nem NAO. Quase sempre é modelo de raciocínio: gasta o teto
            # de saída pensando e devolve content vazio. Contar isso como
            # "reprovado" faz um modelo que nunca respondeu parecer um juiz
            # severo — medido com Qwen 3.8 e GLM 5.2, que devolvem '' com
            # max_tokens=4. Continua reprovando (é gate), mas fica registrado.
            log.warning("juiz ininteligível (%r) — reprovando por segurança", texto[:80])
            INDISPONIVEIS.append(f"RespostaIninteligivel: {texto[:120]!r}")
            return False
        veredicto = bool(re.match(r"\s*sim\b", texto, re.IGNORECASE))
    except Exception as e:
        log.warning("juiz indisponível (%s: %s) — reprovando por segurança", type(e).__name__, e)
        INDISPONIVEIS.append(f"{type(e).__name__}: {str(e)[:160]}")
        # Não entra no cache: guardar a indisponibilidade como veredicto
        # propagaria uma falha momentânea por toda a rodada, e uma nova
        # tentativa depois da cota voltar leria o 429 antigo.
        return False

    _cache[chave] = veredicto
    return veredicto
