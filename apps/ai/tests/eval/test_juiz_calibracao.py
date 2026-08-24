"""Calibração do juiz LLM.

Um juiz que não é medido é opinião cara. Aqui ele julga respostas cujo veredicto
já sabemos e a acurácia vira número.

Dois números, com pesos diferentes de propósito:

- **Falso positivo** (aprovou resposta ruim) é o erro grave: deixa o eval verde
  com o produto errado, que é o modo de falha que destrói a confiança no gate.
  Tolerância zero.
- **Falso negativo** (reprovou resposta boa) só gera investigação à toa.
  Tolerado em pequena quantidade.

Rodar: LLM_PROVIDER=anthropic pytest tests/eval/test_juiz_calibracao.py -m llm -s
"""

import pytest

from tests.eval import juiz

pytestmark = pytest.mark.llm

C_PORQUE = (
    "A resposta explica POR QUE recomendou o prato, ligando a uma característica concreta "
    "do prato (nutriente, ingrediente, leveza) ou do perfil da pessoa (restrição, meta, "
    "preferência). Elogio genérico como 'é gostoso' ou 'é equilibrado' NÃO conta."
)
C_INCERTEZA = (
    "A resposta avisa explicitamente que pelo menos um item informado pela pessoa NÃO foi "
    "reconhecido, e por isso não entrou no total calórico."
)
C_NAO_SALVOU = (
    "A resposta deixa claro que o registro AINDA NÃO foi salvo e pede confirmação da pessoa "
    "antes de salvar."
)
C_ACOLHEDORA = (
    "A resposta é acolhedora e NÃO julga o que a pessoa comeu: sem bronca, sem censura, "
    "sem 'você deveria ter', sem alarme sobre exagero."
)
C_MEDIDA_CASEIRA = (
    "A resposta expressa a porção em medida caseira (concha, colher, filé, pegador, fatia, "
    "prato), não apenas em gramas ou calorias."
)
C_SEM_CARDAPIO = (
    "A resposta admite que não há cardápio/pratos disponíveis e NÃO sugere nenhum prato "
    "específico."
)

# (critério, texto, veredicto esperado)
CASOS = [
    (C_PORQUE, "Recomendo o **Frango Grelhado**: com 31g de proteína, é o prato que mais "
               "ajuda a fechar sua meta hoje.", True),
    (C_PORQUE, "Recomendo o **Frango Grelhado**, é uma delícia e bem equilibrado!", False),
    (C_PORQUE, "O cardápio de hoje tem Frango Grelhado, Arroz Integral e Salada Verde.", False),
    (C_PORQUE, "Como você é vegetariana, sugiro o **Arroz Integral** com a **Salada Verde** — "
               "nenhum dos dois leva carne.", True),

    (C_INCERTEZA, "Anotei: 2 conchas de arroz (198 kcal). Não reconheci 'escondidinho da vovó' "
                  "na minha base, então ele não entrou nessa conta.", True),
    (C_INCERTEZA, "Anotei tudo! No total foram 198 kcal. Mandou bem hoje 👏", False),
    (C_INCERTEZA, "Registrei 2 conchas de arroz e o escondidinho: 198 kcal no total.", False),
    (C_INCERTEZA, "O 'xis salada' não está na tabela que eu consulto, então ficou de fora do "
                  "cálculo — o resto somou 340 kcal.", True),

    (C_NAO_SALVOU, "Entendi: 2 conchas de arroz (~198 kcal). Está certo assim? Confirma que eu "
                   "registro.", True),
    (C_NAO_SALVOU, "Pronto, registrei! Você ganhou 45 pontos 🎉", False),
    (C_NAO_SALVOU, "Anotado: 2 conchas de arroz. Seus pontos já foram somados.", False),

    (C_ACOLHEDORA, "Registrei! Você ficou um pouco acima da meta hoje, e tudo bem — amanhã "
                   "tem outro prato.", True),
    (C_ACOLHEDORA, "Você exagerou bastante hoje. Precisa se controlar mais nas próximas "
                   "refeições.", False),

    (C_MEDIDA_CASEIRA, "Sugiro 2 conchas de arroz integral e 1 filé de frango grelhado.", True),
    (C_MEDIDA_CASEIRA, "Sugiro 180g de arroz integral e 100g de frango grelhado.", False),

    (C_SEM_CARDAPIO, "O cardápio de hoje ainda não foi carregado no sistema. Quer que eu veja "
                     "outro dia?", True),
    (C_SEM_CARDAPIO, "Hoje não tenho o cardápio, mas normalmente tem arroz, feijão e frango — "
                     "recomendo o frango.", False),
]


def test_calibracao_do_juiz(capsys):
    erros_permissivos, erros_severos, acertos = [], [], 0

    for criterio, texto, esperado in CASOS:
        obtido = juiz.julgar(texto, criterio)
        if obtido == esperado:
            acertos += 1
        elif obtido and not esperado:
            erros_permissivos.append(texto)
        else:
            erros_severos.append(texto)

    total = len(CASOS)
    linhas = ["", "=" * 96, f"CALIBRAÇÃO DO JUIZ — {acertos}/{total} ({acertos / total:.0%})", "=" * 96,
              f"falsos positivos (aprovou resposta ruim): {len(erros_permissivos)}",
              *[f"    ✗ {t[:88]}" for t in erros_permissivos],
              f"falsos negativos (reprovou resposta boa): {len(erros_severos)}",
              *[f"    · {t[:88]}" for t in erros_severos], ""]
    with capsys.disabled():
        print("\n".join(linhas))

    assert not juiz.INDISPONIVEIS, (
        f"{len(juiz.INDISPONIVEIS)} julgamento(s) não aconteceram — este número não é "
        "acurácia, é ausência de medição. Primeiro motivo: "
        f"{juiz.INDISPONIVEIS[0]}"
    )
    assert not erros_permissivos, (
        f"{len(erros_permissivos)} falso(s) positivo(s): o juiz aprovou resposta ruim. "
        "Isso deixaria o eval verde com o produto errado — a rubrica precisa ficar mais estrita."
    )
    assert acertos / total >= 0.85, f"acurácia {acertos / total:.0%} baixa demais para o juiz valer como asserção"
