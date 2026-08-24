"""O eval também precisa de teste.

Um harness que aceita qualquer resposta dá falsa segurança: fica verde todo dia
e ninguém percebe que parou de checar. Estes testes rodam SEM LLM, em todo
commit, e provam que as asserções reprovam o que deveriam.
"""

import pytest

from app.agent.motor.observacao import ObservacoesDoTurno
from tests.eval import assercoes, fakes

CAMPOS_OBRIGATORIOS = ("nome", "porque", "dados", "esperado")
COBERTURA_MINIMA_POR_BATERIA = 10


# --- integridade das baterias ------------------------------------------------

def test_baterias_tem_massa_suficiente():
    """Resolução de medição, não cobertura por cobertura.

    Com 10 casos no total, cada um valia 10 pontos e a variância entre rodadas
    chegou a 20. Com 6 por bateria ainda valia 5,5 — o suficiente para uma
    oscilação parecer regressão. Com 10 por bateria, um caso vale 3,3.
    """
    casos = fakes.carregar_casos()
    assert len(casos) >= 55, f"apenas {len(casos)} casos — amostra pequena demais para ser gate"
    for bateria in fakes.baterias():
        n = len(fakes.carregar_casos(bateria))
        assert n >= COBERTURA_MINIMA_POR_BATERIA, f"bateria {bateria} com só {n} casos"


def test_todos_os_casos_estao_completos():
    for caso in fakes.carregar_casos():
        faltando = [c for c in CAMPOS_OBRIGATORIOS if not caso.get(c)]
        assert not faltando, f"{caso.get('nome', caso['arquivo'])}: campos faltando {faltando}"
        assert caso.get("mensagem") or caso.get("turnos"), f"{caso['nome']}: sem mensagem nem turnos"


def test_todo_caso_usa_assercao_existente():
    # Erro de digitação numa chave faria o caso passar sem checar nada.
    validas = set(assercoes.ASSERCOES) | {"deve_ser_fora_de_escopo"}
    for caso in fakes.carregar_casos():
        desconhecidas = set(caso["esperado"]) - validas
        assert not desconhecidas, f"{caso['nome']}: asserção inexistente {sorted(desconhecidas)}"


def test_todo_caso_aponta_para_dataset_existente():
    for caso in fakes.carregar_casos():
        dados = fakes.carregar_dados(caso["dados"])
        assert "pratos" in dados and "perfil" in dados


def test_as_regras_criticas_estao_cobertas():
    esperados = [c["esperado"] for c in fakes.carregar_casos()]
    assert any(e.get("cita_todos_os_pratos") for e in esperados), "sem caso da regra contratual"
    assert any(e.get("sem_alergeno") for e in esperados), "sem caso de alergia"
    assert any(e.get("sem_restricao_violada") for e in esperados), "sem caso de restrição"
    assert any(e.get("ressalva_incerteza") for e in esperados), "sem caso de incerteza declarada"
    assert any(e.get("previa_antes_de_gravar") for e in esperados), "sem caso do registro em 2 etapas"
    assert any(e.get("deve_ser_fora_de_escopo") for e in esperados), "sem caso de guardrail"


def test_juiz_e_minoria():
    # O juiz custa API e é estocástico. Se a maioria dos casos depender dele, o
    # eval virou opinião cara em vez de medição.
    casos = fakes.carregar_casos()
    com_juiz = [c for c in casos if "juiz" in c["esperado"]]
    assert len(com_juiz) / len(casos) < 0.5, "juiz demais: prefira asserção estrutural"


# --- as asserções realmente reprovam ----------------------------------------

DADOS = fakes.carregar_dados("padrao")


def _ctx(resposta, tools=(), retornos=(), chamadas=(), erro=None, dados=None):
    obs = ObservacoesDoTurno()
    for i, r in enumerate(retornos):
        obs.registrar((f"t{i}", "{}"), r)
    return assercoes.Contexto(
        resposta=resposta, tools=list(tools), observacoes=obs,
        dados=dados or DADOS, erro=erro, chamadas=list(chamadas),
    )


def test_reprova_prato_inventado():
    ctx = _ctx("Recomendo a **Feijoada Completa**.", tools=["filtrar_pratos"], retornos=[DADOS["pratos"]])
    assert assercoes.conferir(ctx, {"sem_prato_inventado": True})


def test_aprova_prato_do_cardapio():
    ctx = _ctx("Recomendo o **Frango grelhado com ervas**.", tools=["filtrar_pratos"], retornos=[DADOS["pratos"]])
    assert assercoes.conferir(ctx, {"sem_prato_inventado": True}) == []


def test_alergeno_no_cardapio_nao_e_alergeno_recomendado():
    # A regra contratual OBRIGA listar o cardápio inteiro, que inclui o alérgeno.
    cardapio = "Cardapio: Frango grelhado, Salada de grao-de-bico com amendoim. Recomendo o Frango grelhado."
    assert assercoes.conferir(_ctx(cardapio), {"sem_alergeno": ["amendoim"]}) == []


def test_alergeno_recomendado_reprova():
    texto = "Cardapio: Frango grelhado, Salada de grao-de-bico com amendoim. Recomendo a Salada de grao-de-bico."
    falhas = assercoes.conferir(_ctx(texto), {"sem_alergeno": ["amendoim"]})
    assert falhas and "alérgeno" in falhas[0]


def test_restricao_violada_reprova():
    texto = "Recomendo o Estrogonofe de carne, é o mais proteico."
    falhas = assercoes.conferir(_ctx(texto), {"sem_restricao_violada": ["vegetariano"]})
    assert falhas and "não indicado" in falhas[0]


def test_cardapio_incompleto_reprova():
    falhas = assercoes.conferir(_ctx("Recomendo o Frango grelhado."), {"cita_todos_os_pratos": True})
    assert falhas and "contratual" in falhas[0]


def test_tools_proibidas():
    ctx = _ctx("...", tools=["meu_perfil", "listar_pratos_do_dia"])
    assert assercoes.conferir(ctx, {"tools_proibidas": ["meu_perfil"]})
    assert assercoes.conferir(ctx, {"tools_proibidas": ["meus_pontos"]}) == []


def test_previa_antes_de_gravar():
    ok = _ctx("Anotado!", chamadas=[("registrar_consumo", '{"k": {"confirmado": false}}'),
                                    ("registrar_consumo", '{"k": {"confirmado": true}}')])
    assert assercoes.conferir(ok, {"previa_antes_de_gravar": True}) == []

    direto = _ctx("Anotado!", chamadas=[("registrar_consumo", '{"k": {"confirmado": true}}')])
    assert assercoes.conferir(direto, {"previa_antes_de_gravar": True})

    nenhum = _ctx("Anotado!", chamadas=[("meu_perfil", "{}")])
    assert assercoes.conferir(nenhum, {"previa_antes_de_gravar": True})


def test_turno_com_erro_reprova_tudo():
    ctx = _ctx("...", erro="PrazoEsgotado")
    assert assercoes.conferir(ctx, {"sem_prato_inventado": True}) == ["turno falhou: PrazoEsgotado"]


def test_asercao_inexistente_no_caso_e_denunciada():
    falhas = assercoes.conferir(_ctx("ok"), {"asercao_que_nao_existe": True})
    assert falhas and "inexistente" in falhas[0]


@pytest.mark.parametrize("valor, deve_falhar", [(True, True), (False, False)])
def test_asercao_desligada_com_false_nao_roda(valor, deve_falhar):
    ctx = _ctx("Recomendo a **Feijoada Completa**.", tools=["filtrar_pratos"], retornos=[DADOS["pratos"]])
    assert bool(assercoes.conferir(ctx, {"sem_prato_inventado": valor})) is deve_falhar


def test_fake_de_consumo_responde_a_entrada(monkeypatch):
    """O fake precisa variar com o que recebe, senão anula checagens do produto.

    Enquanto ele devolvia o mesmo total para qualquer item, "1 colher" e "3
    conchas" saíam idênticos — e o caso de sobra maior que o consumo media 0/3
    com o código correto.
    """
    import app.agent.dominio.refeitorio.tools as t

    fakes.instalar(monkeypatch, fakes.carregar_dados("padrao"))
    pouco = t.go_api.calcular_consumo([{"alimento": "arroz", "medida": "colher de sopa", "quantidade": 1}])
    muito = t.go_api.calcular_consumo([{"alimento": "arroz", "medida": "concha", "quantidade": 3}])
    assert muito["gramas_totais"] > pouco["gramas_totais"] * 5
    assert muito["kcal"] > pouco["kcal"]


def test_fake_preserva_o_que_o_dataset_declara(monkeypatch):
    # Escalar os totais não pode apagar `itens_ignorados`/`completo`, que é o que
    # os casos de incerteza exercitam.
    import app.agent.dominio.refeitorio.tools as t

    fakes.instalar(monkeypatch, fakes.carregar_dados("consumo_fora_da_base"))
    out = t.go_api.calcular_consumo([{"alimento": "arroz", "medida": "concha", "quantidade": 2}])
    assert out["itens_ignorados"] == ["escondidinho da vovo"]
    assert out["completo"] is False


# --- juiz indisponível não é veredicto --------------------------------------

def test_juiz_indisponivel_e_registrado_separado_do_veredicto(monkeypatch):
    """Cota estourada devolve o mesmo False de "reprovado", e as duas coisas
    têm leitura oposta. Sem esta separação, 50 requisições/dia esgotadas
    leram como 53% de acurácia de um juiz que nunca respondeu."""
    from tests.eval import juiz

    juiz.limpar()

    class Quebrado:
        def invoke(self, _):
            raise RuntimeError("Error code: 429 - free-models-per-day")

    monkeypatch.setattr(juiz, "_modelo", lambda: Quebrado())
    assert juiz.julgar("qualquer resposta", "qualquer critério") is False
    assert len(juiz.INDISPONIVEIS) == 1
    assert "429" in juiz.INDISPONIVEIS[0]
    juiz.limpar()


def test_juiz_nao_cacheia_indisponibilidade(monkeypatch):
    # Guardar a falha no cache propagaria um 429 momentâneo para toda a rodada,
    # e a tentativa seguinte leria o erro antigo em vez de perguntar de novo.
    from tests.eval import juiz

    juiz.limpar()
    tentativas = []

    class Instavel:
        def invoke(self, _):
            tentativas.append(1)
            if len(tentativas) == 1:
                raise RuntimeError("429")
            return type("R", (), {"content": "SIM"})()

    monkeypatch.setattr(juiz, "_modelo", lambda: Instavel())
    assert juiz.julgar("r", "c") is False
    assert juiz.julgar("r", "c") is True, "a segunda tentativa leu o 429 do cache"
    juiz.limpar()


def test_juiz_cacheia_veredicto_de_verdade(monkeypatch):
    from tests.eval import juiz

    juiz.limpar()
    chamadas = []

    class Ok:
        def invoke(self, _):
            chamadas.append(1)
            return type("R", (), {"content": "NAO"})()

    monkeypatch.setattr(juiz, "_modelo", lambda: Ok())
    assert juiz.julgar("r", "c") is False
    assert juiz.julgar("r", "c") is False
    assert len(chamadas) == 1, "veredicto real deveria vir do cache"
    assert juiz.INDISPONIVEIS == []
    juiz.limpar()


# --- fornecedor compatível com OpenAI é configuração, não código -------------

def test_provider_compat_usa_a_url_configurada(monkeypatch):
    """Hugging Face, Together, Groq, vLLM e LiteLLM falam o mesmo protocolo.

    Um `if` por fornecedor viraria uma lista que envelhece sozinha, e o único
    lugar que precisava saber o nome deles era o `.env`.
    """
    from app import config
    from app.agent.motor import provedores

    capturado = {}
    monkeypatch.setattr(provedores, "_openai_compativel",
                        lambda base, chave, mod, t, mx: capturado.update(
                            base=base, chave=chave, modelo=mod, temp=t))
    monkeypatch.setattr(config, "LLM_BASE_URL", "https://router.huggingface.co/v1")
    monkeypatch.setattr(config, "LLM_API_KEY", "hf_xxx")
    monkeypatch.setattr(config, "LLM_MODEL", "google/gemma-4-31B-it")

    provedores.construir(temperatura=0, max_tokens=4, provider="openai_compat")
    assert capturado["base"] == "https://router.huggingface.co/v1"
    assert capturado["modelo"] == "google/gemma-4-31B-it"
    assert capturado["temp"] == 0


def test_provider_compat_sem_url_falha_dizendo_o_que_falta(monkeypatch):
    # Sem URL o cliente OpenAI iria para api.openai.com e falharia com 401 —
    # erro que não ensina nada sobre a configuração que faltou.
    import pytest as _pytest

    from app import config
    from app.agent.motor import provedores

    monkeypatch.setattr(config, "LLM_BASE_URL", "")
    with _pytest.raises(RuntimeError, match="LLM_BASE_URL"):
        provedores.construir(temperatura=0, max_tokens=4, provider="openai_compat")


def test_juiz_vazio_e_indisponibilidade_nao_severidade(monkeypatch):
    """Modelo de raciocínio gasta o teto de saída pensando e devolve ''.

    Contado como "reprovado", ele vira um juiz que parece severíssimo e nunca
    respondeu. Medido em Qwen 3.8 e GLM 5.2 com max_tokens=4.
    """
    from tests.eval import juiz

    for vazio in ("", "   ", "<think>", "Vou analisar o critério com cuidado"):
        juiz.limpar()
        monkeypatch.setattr(juiz, "_modelo",
                            lambda v=vazio: type("M", (), {"invoke": lambda s, _: type("R", (), {"content": v})()})())
        assert juiz.julgar("resposta", "criterio") is False
        assert len(juiz.INDISPONIVEIS) == 1, f"{vazio!r} deveria contar como não-medido"
    juiz.limpar()


def test_juiz_nao_reclama_de_resposta_valida(monkeypatch):
    from tests.eval import juiz

    for texto, esperado in (("SIM", True), ("NAO", False), ("não", False), (" sim ", True)):
        juiz.limpar()
        monkeypatch.setattr(juiz, "_modelo",
                            lambda t=texto: type("M", (), {"invoke": lambda s, _: type("R", (), {"content": t})()})())
        assert juiz.julgar("r", "c") is esperado
        assert juiz.INDISPONIVEIS == [], f"{texto!r} é resposta válida"
    juiz.limpar()
