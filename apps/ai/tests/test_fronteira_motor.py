"""A fronteira motor/domínio, defendida por teste.

O motor só é reaproveitável no próximo produto se ele não souber o que é comida.
Isso não se garante com um princípio escrito no README: sob pressão de prazo,
alguém vai passar `unidade_id` "só desta vez" e em três sprints o motor sabe o
que é um prato de novo.

Este teste varre os fontes de `app/agent/motor/` procurando vocabulário do
domínio atual. Se falhar, a correção quase nunca é adicionar exceção aqui — é
mover o código para `app/agent/dominio/<produto>/` ou generalizar o nome
(`CATALOGO` em vez de "cardápio", `item` em vez de "prato", `valor` em vez de
"kcal").
"""

import re
from pathlib import Path

MOTOR = Path(__file__).resolve().parents[1] / "app" / "agent" / "motor"

# Cada padrão vem com o motivo, para a falha ensinar em vez de só acusar.
TERMOS_DE_DOMINIO = [
    (r"cardapio|cardápio", "use 'catalogo' — o motor não sabe o que é cardápio"),
    (r"refeit[óo]rio", "nome do produto atual não pertence ao motor"),
    (r"\bpratos?\b", "use 'item' — 'prato' é vocabulário deste domínio"),
    (r"aliment", "use 'item' — o motor não sabe que os itens são comida"),
    (r"nutri", "nutrição é domínio"),
    (r"\bkcal\b|caloria", "use 'valor' — unidade nutricional é domínio"),
    (r"unidade_id|\bunidades?\b", "escopo do domínio; o motor trata contexto como opaco"),
    # `(?-i:...)` porque a varredura roda em IGNORECASE: sem isso a segunda
    # alternativa — que existe para pegar CamelCase tipo `LiaTimingCallback` —
    # vira `lia[a-z]` e acusa "famílias", "aliados", "familiar".
    (r"\bLia\b|(?-i:Lia[A-Z])", "persona do produto atual não pertence ao motor"),
    (r"restri[çc][ãa]o|restricao", "restrição alimentar é domínio"),
    (r"alergi", "alergia é domínio"),
]


def _fontes_do_motor() -> list[Path]:
    return sorted(MOTOR.rglob("*.py"))


def test_motor_existe_e_tem_fontes():
    """Guarda contra o teste virar vacuamente verde se o diretório sumir/renomear."""
    assert MOTOR.is_dir(), f"diretório do motor não encontrado: {MOTOR}"
    assert _fontes_do_motor(), "nenhum fonte .py encontrado em motor/"


def test_motor_nao_conhece_o_dominio():
    violacoes = []
    for arquivo in _fontes_do_motor():
        for n, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
            for padrao, motivo in TERMOS_DE_DOMINIO:
                if re.search(padrao, linha, re.IGNORECASE):
                    violacoes.append(f"{arquivo.name}:{n} — {motivo}\n    {linha.strip()}")

    assert not violacoes, (
        "vocabulário de domínio dentro de motor/ (a fronteira que torna o motor "
        "reaproveitável):\n\n" + "\n".join(violacoes)
    )


def test_motor_nao_importa_o_dominio():
    """Vocabulário é o sintoma; import é a doença. Um `from ...dominio...` no
    motor amarra o motor a este produto mesmo com todos os nomes genéricos."""
    violacoes = []
    for arquivo in _fontes_do_motor():
        for n, linha in enumerate(arquivo.read_text(encoding="utf-8").splitlines(), 1):
            if re.match(r"\s*(from|import)\s+.*\bdominio\b", linha):
                violacoes.append(f"{arquivo.name}:{n} — {linha.strip()}")

    assert not violacoes, "motor/ importando de dominio/:\n" + "\n".join(violacoes)


def test_varredura_nao_acusa_palavra_comum():
    """A varredura precisa doer só quando há violação de verdade.

    Termo curto casado como substring transforma o guardião em ruído, e teste
    que grita à toa é teste que alguém desliga. "famílias" chegou a reprovar um
    comentário legítimo do motor.
    """
    inocentes = ["dezenas de famílias de modelos", "os aliados do processo",
                 "contexto familiar", "avalia o resultado"]
    for linha in inocentes:
        for padrao, motivo in TERMOS_DE_DOMINIO:
            assert not re.search(padrao, linha, re.IGNORECASE), \
                f"falso positivo em {linha!r}: {motivo}"


def test_varredura_ainda_pega_a_persona():
    # E o contrário: afrouxar não pode cegar o teste para o caso real.
    for linha in ["a Lia responde", "class LiaTimingCallback:", "resposta da LIA"]:
        assert any(re.search(p, linha, re.IGNORECASE) for p, _ in TERMOS_DE_DOMINIO), \
            f"violação real não detectada: {linha!r}"
