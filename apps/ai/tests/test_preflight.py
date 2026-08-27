"""Verificação de partida do provedor.

O que se testa é a decisão: subir ou não subir. Sem rede — o preflight recebe
o construtor do modelo injetado, então o dublê basta.
"""

import pytest

from app.agent.motor import preflight
from app.agent.motor.erros import ClasseDeErro


class _Resposta:
    def __init__(self, tool_calls=None):
        self.tool_calls = tool_calls or []
        self.content = "ok"


class _ModeloBom:
    def bind_tools(self, _tools):
        return self
    def invoke(self, _msg):
        return _Resposta(tool_calls=[{"name": "_preflight_echo", "args": {"valor": 7}}])


class _ModeloSemTool:
    """Responde texto, ignora a tool. É o caso perigoso: parece que funciona."""
    def bind_tools(self, _tools):
        return self
    def invoke(self, _msg):
        return _Resposta(tool_calls=[])


class _ErroHTTP(Exception):
    def __init__(self, msg, status):
        super().__init__(msg)
        self.status_code = status


class _ModeloInalcancavel:
    def bind_tools(self, _tools):
        return self
    def invoke(self, _msg):
        raise _ErroHTTP("[Errno -3] Temporary failure in name resolution", None) \
            if False else ConnectionError("Temporary failure in name resolution")


def test_provedor_saudavel_passa():
    r = preflight.verificar(lambda: _ModeloBom())
    assert r.ok and r.alcancavel and r.chama_tool


def test_modelo_que_nao_chama_tool_reprova():
    """O caso que não dá erro: o provedor responde, o modelo ignora a tool, e o
    agente passa a alucinar o dado em vez de buscá-lo. Só o preflight pega."""
    r = preflight.verificar(lambda: _ModeloSemTool())
    assert not r.ok and r.alcancavel and not r.chama_tool
    assert "NÃO chamou a tool" in r.detalhe


def test_provedor_inalcancavel_reprova_e_classifica():
    r = preflight.verificar(lambda: _ModeloInalcancavel())
    assert not r.ok and not r.alcancavel
    assert r.falha is not None and r.falha.classe is ClasseDeErro.INDISPONIVEL


def test_falha_ao_construir_o_modelo_e_capturada():
    """Config faltando (ex.: LLM_BASE_URL vazio) estoura na construção, antes
    de qualquer chamada — e isso também é motivo para não subir."""
    def _explode():
        raise RuntimeError("LLM_PROVIDER=openai_compat exige LLM_BASE_URL")
    r = preflight.verificar(_explode)
    assert not r.ok and not r.alcancavel and "LLM_BASE_URL" in r.detalhe


def test_exigir_derruba_o_processo_quando_reprova():
    """O comportamento que resolve o silêncio: não subir é melhor que subir
    quebrado, porque quebrado consome a mensagem do usuário e não avisa."""
    with pytest.raises(RuntimeError, match="preflight"):
        preflight.exigir(lambda: _ModeloSemTool())


def test_exigir_deixa_passar_quando_esta_ok():
    preflight.exigir(lambda: _ModeloBom())  # não levanta


def test_pode_dispensar_a_verificacao_de_tool():
    """Nem todo consumidor do motor precisa de tool — o juiz do eval, por
    exemplo, só classifica texto."""
    class _SoTexto:
        def invoke(self, _msg):
            return _Resposta()
    r = preflight.verificar(lambda: _SoTexto(), exigir_tool=False)
    assert r.ok and not r.chama_tool


# --- regressão: o teto de saída da sonda -------------------------------------
# Em 27/08/2026 o worker construía a sonda com max_tokens=16 e o preflight
# reprovava o claude-haiku-4-5 na partida. A chamada de tool da Anthropic vem
# como bloco estruturado e consome tokens de SAÍDA: com teto apertado a resposta
# trunca, `tool_calls` volta vazio e a sonda acusa o modelo de não fazer tool
# calling. Medido: 16 reprova, 64 e 256 passam.

def test_worker_pede_o_teto_que_a_sonda_exige():
    """O worker não pode inventar o teto: ele é conhecimento da sonda."""
    import inspect
    from app.workers import chat_worker
    fonte = inspect.getsource(chat_worker.main)
    assert "preflight.MAX_TOKENS_SONDA" in fonte, (
        "o worker precisa usar o teto declarado pela sonda; um número solto aqui "
        "volta a reprovar modelo bom na partida"
    )


def test_teto_da_sonda_cabe_numa_chamada_de_tool():
    from app.agent.motor import preflight
    assert preflight.MAX_TOKENS_SONDA >= 64, (
        "abaixo de 64 a chamada de tool da Anthropic trunca (medido em 27/08/2026)"
    )


def test_avisa_quando_o_teto_recebido_e_pequeno(caplog):
    """Teto apertado não reprova em silêncio: deixa rastro para o operador."""
    import logging
    from app.agent.motor import preflight

    class _Apertado(_ModeloBom):
        max_tokens = 16

    with caplog.at_level(logging.WARNING):
        r = preflight.verificar(lambda: _Apertado())
    assert r.ok
    assert any("MAX_TOKENS_SONDA" in m for m in caplog.messages)
