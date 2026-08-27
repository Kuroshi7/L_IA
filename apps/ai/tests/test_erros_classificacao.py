"""Classificação de falha do modelo.

Os casos não são inventados: cada um reproduz um erro que este projeto viu de
verdade, com o texto que o provedor devolveu. Ver docs/custos-provedores.md.
"""

import pytest

from app.agent.motor.erros import ClasseDeErro, classificar


class _ErroHTTP(Exception):
    """Imita a exceção dos clientes: mensagem + status_code."""

    def __init__(self, msg: str, status: int | None = None):
        super().__init__(msg)
        if status is not None:
            self.status_code = status


class RateLimitError(_ErroHTTP): pass
class AuthenticationError(_ErroHTTP): pass
class APIConnectionError(_ErroHTTP): pass
class ContextWindowExceededError(_ErroHTTP): pass
class NotFoundError(_ErroHTTP): pass
class GraphRecursionError(Exception): pass


# (rótulo, exceção, classe esperada, retentável)
CASOS = [
    # ─── vistos neste projeto ───
    ("openrouter: cota diária esgotada",
     RateLimitError("Rate limit exceeded: free-models-per-day. Add 10 credits to "
                    "unlock 1000 free model requests per day", 429),
     ClasseDeErro.COTA, False),

    ("huggingface: crédito mensal acabou",
     _ErroHTTP("You have depleted your monthly included credits", 402),
     ClasseDeErro.COTA, False),

    ("huggingface: chave inválida",
     AuthenticationError("Error code: 401 - {'error': 'Invalid username or password.'}", 401),
     ClasseDeErro.AUTENTICACAO, False),

    ("ollama inexistente: nome não resolve",
     APIConnectionError("[Errno -3] Temporary failure in name resolution"),
     ClasseDeErro.INDISPONIVEL, True),

    # ─── genéricos ───
    ("rate limit de ritmo, sem menção a cota",
     RateLimitError("Too many requests, please slow down", 429),
     ClasseDeErro.LIMITE, True),

    ("contexto estourado chega como 400",
     ContextWindowExceededError("This model's maximum context length is 8192 tokens", 400),
     ClasseDeErro.CONTEXTO, False),

    ("modelo que não existe",
     NotFoundError("The model 'gpt-nao-existe' does not exist", 404),
     ClasseDeErro.CONFIGURACAO, False),

    ("provedor caiu",
     _ErroHTTP("Bad gateway", 502),
     ClasseDeErro.INDISPONIVEL, True),

    ("agente entrou em loop de tools",
     GraphRecursionError("Recursion limit of 25 reached"),
     ClasseDeErro.LOOP, False),
]


@pytest.mark.parametrize("rotulo,exc,classe,retentavel",
                         CASOS, ids=[c[0] for c in CASOS])
def test_classifica(rotulo, exc, classe, retentavel):
    r = classificar(exc)
    assert r.classe is classe, f"{rotulo}: classe={r.classe} codigo={r.codigo}"
    assert r.retentavel is retentavel, f"{rotulo}: retentavel={r.retentavel}"


def test_cota_e_limite_sao_ambos_429_mas_nao_sao_a_mesma_coisa():
    """A distinção que motivou o módulo.

    Ambos chegam com 429. "20 por minuto" passa sozinho; "1000 por dia" não
    passa hoje. Dizer "tente de novo em instantes" no segundo caso é mentira.
    """
    ritmo = classificar(RateLimitError("Too many requests", 429))
    cota = classificar(RateLimitError("Rate limit exceeded: free-models-per-day", 429))
    assert ritmo.retentavel and not cota.retentavel


def test_erro_embrulhado_e_classificado_pela_causa():
    """Clientes embrulham o erro real. Classificar só a casca perde a informação."""
    try:
        try:
            raise AuthenticationError("Invalid API key", 401)
        except AuthenticationError as causa:
            raise RuntimeError("falha ao invocar o modelo") from causa
    except RuntimeError as e:
        assert classificar(e).classe is ClasseDeErro.AUTENTICACAO


@pytest.mark.parametrize("nome_da_classe", [
    "ConnectError",        # httpx — o que aparece de verdade
    "ConnectTimeout",      # httpx
    "ConnectionError",     # embutido do Python
    "APIConnectionError",  # cliente da OpenAI
])
def test_nomes_reais_de_erro_de_conexao(nome_da_classe):
    """Regressão: o classificador procurava "Connection" e o httpx levanta
    `ConnectError`, sem o "ion". O teste passava com o erro embutido do Python
    e falhava contra o provedor real — visto rodando o preflight de verdade."""
    exc = type(nome_da_classe, (Exception,), {})("host não resolve")
    assert classificar(exc).classe is ClasseDeErro.INDISPONIVEL


def test_desconhecido_nao_bloqueia_o_usuario():
    """Sem mapeamento, tratamos como transitório — mas o código diz INTERNO
    para a métrica mostrar que há algo não classificado."""
    r = classificar(ValueError("algo inesperado"))
    assert r.classe is ClasseDeErro.INTERNO and r.retentavel
