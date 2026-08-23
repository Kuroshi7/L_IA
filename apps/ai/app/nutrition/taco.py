"""Referência TACO (Tabela Brasileira de Composição de Alimentos, NEPA/UNICAMP).

Por que existe: a base do produto vem da *Tabela para Avaliação de Consumo
Alimentar em Medidas Caseiras* (Atheneu), que é excelente para MEDIDA CASEIRA —
quantas gramas tem uma concha — mas cujas linhas de fonte `*` (cálculo dos
autores, não medição laboratorial) trazem valores que não sobrevivem a
conferência. Exemplo real: "ARROZ INTEGRAL COZIDO" a 257 kcal/100 g contra
123,5 kcal na TACO, e contra 164 kcal do próprio arroz branco cozido da mesma
tabela — arroz integral cozido não tem 42% mais carboidrato que o branco.

A TACO não substitui a outra: ela não tem medidas caseiras. Serve como CONTRA-
PROVA por 100 g, que é o denominador comum entre as duas.

Dados: github.com/marcelosanto/tabela_taco (MIT), enxugado para os campos que
usamos. A TACO em si é publicação pública do NEPA/UNICAMP.
"""

import json
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ARQUIVO = Path(__file__).parent / "dados" / "taco.json"

# Palavras que só descrevem o corte e atrapalham o casamento por nome.
_RUIDO = {"tipo", "com", "sem", "de", "da", "do", "e", "em", "no", "na"}

# Estado de preparo. Comparar o cru com o cozido é o erro mais fácil de cometer
# aqui e o mais caro: cozimento muda o teor de água, então os valores por 100 g
# divergem legitimamente e a auditoria acusaria um problema que não existe.
_PREPARO = {
    "cru": "cru", "crua": "cru", "cruas": "cru", "crus": "cru", "fresca": "cru", "fresco": "cru",
    "cozido": "cozido", "cozida": "cozido", "cozidos": "cozido", "cozidas": "cozido",
    "refogado": "refogado", "refogada": "refogado",
    "frito": "frito", "frita": "frito", "fritas": "frito",
    "assado": "assado", "assada": "assado",
    "grelhado": "grelhado", "grelhada": "grelhado",
}


def _preparo(texto: str) -> str | None:
    for palavra in normalizar(texto).split():
        if palavra in _PREPARO:
            return _PREPARO[palavra]
    return None


def preparos_compativeis(a: str, b: str) -> bool:
    """Com os dois estados declarados, precisam ser o mesmo.

    "cru" é assimétrico: os alimentos da nossa base são pratos SERVIDOS, então
    nome sem preparo declarado significa preparado, não cru. Sem esta exceção,
    "Croquete de Carne" casava com "Croquete, de carne, cru" da TACO e a
    auditoria acusaria uma divergência que é só a água do cozimento."""
    pa, pb = _preparo(a), _preparo(b)
    if "cru" in (pa, pb):
        return pa == pb
    return pa is None or pb is None or pa == pb


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    limpo = "".join(c if c.isalnum() or c.isspace() else " " for c in sem_acento.lower())
    return " ".join(limpo.split())


def tokens(texto: str) -> frozenset[str]:
    return frozenset(t for t in normalizar(texto).split() if t not in _RUIDO and len(t) > 2)


@dataclass(frozen=True)
class Referencia:
    nome: str
    categoria: str | None
    kcal: float
    proteina_g: float | None
    carboidrato_g: float | None
    gordura_g: float | None
    umidade_perc: float | None
    tokens: frozenset[str]


@lru_cache(maxsize=1)
def carregar() -> tuple[Referencia, ...]:
    dados = json.loads(ARQUIVO.read_text(encoding="utf-8"))
    return tuple(
        Referencia(
            nome=a["nome"], categoria=a.get("categoria"), kcal=a["kcal"],
            proteina_g=a.get("proteina_g"), carboidrato_g=a.get("carboidrato_g"),
            gordura_g=a.get("gordura_g"), umidade_perc=a.get("umidade_perc"),
            tokens=tokens(a["nome"]),
        )
        for a in dados
    )


def procurar(nome: str, minimo: float = 0.65) -> tuple[Referencia | None, float]:
    """Melhor correspondência por sobreposição de tokens (Jaccard).

    Casamento por token, não por substring: "Arroz Integral Cozido" e
    "Arroz, integral, cozido" são o mesmo alimento com pontuação diferente, e
    "Arroz Doce" NÃO pode casar com "Arroz Cozido" só porque compartilham a
    primeira palavra. O piso alto é de propósito — uma auditoria que compara
    alimentos errados é pior que auditoria nenhuma.
    """
    alvo = tokens(nome)
    if not alvo:
        return None, 0.0

    melhor, melhor_score = None, 0.0
    for ref in carregar():
        uniao = alvo | ref.tokens
        if not uniao:
            continue
        if not preparos_compativeis(nome, ref.nome):
            continue
        score = len(alvo & ref.tokens) / len(uniao)
        if score > melhor_score:
            melhor, melhor_score = ref, score
    return (melhor, melhor_score) if melhor_score >= minimo else (None, melhor_score)
