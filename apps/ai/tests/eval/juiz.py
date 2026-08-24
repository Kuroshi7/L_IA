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
    if _MODELO is not None:
        return _MODELO

    if config.LLM_PROVIDER == "anthropic":
        from langchain_anthropic import ChatAnthropic

        _MODELO = ChatAnthropic(
            model=config.ANTHROPIC_MODEL, max_tokens=4, temperature=0,
            timeout=config.LLM_TIMEOUT_SECONDS, max_retries=config.LLM_MAX_RETRIES,
        )
    else:
        from langchain_ollama import ChatOllama

        _MODELO = ChatOllama(
            model=config.OLLAMA_MODEL, base_url=config.OLLAMA_BASE_URL,
            temperature=0, num_predict=4, num_ctx=config.OLLAMA_NUM_CTX, keep_alive="30m",
        )
    return _MODELO


_cache: dict[tuple[str, str], bool] = {}


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
        veredicto = bool(re.match(r"\s*sim\b", texto.strip(), re.IGNORECASE))
    except Exception as e:
        log.warning("juiz indisponível (%s: %s) — reprovando por segurança", type(e).__name__, e)
        veredicto = False

    _cache[chave] = veredicto
    return veredicto
