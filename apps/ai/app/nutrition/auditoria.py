"""Auditoria da base nutricional contra a TACO.

A promessa do produto é "não invento número, resolvo contra a base". Ela só vale
se a base estiver certa — e a validação de 2026-08-23 mostrou que não está em
todos os casos: "ARROZ INTEGRAL COZIDO" sai a 257 kcal/100 g (o livro-fonte diz
isso mesmo, fonte `*` = cálculo dos autores) contra 123,5 kcal na TACO.

O agente entregava esse número com `confianca: "alta"`, porque a confiança media
a certeza do CASAMENTO do nome, nunca a plausibilidade do DADO.

Este módulo cruza cada alimento da base com a TACO por 100 g e marca
`nutri_porcoes.suspeito` onde a divergência é grande demais para ser diferença
de preparo. Não corrige valor: sem a medição primária, corrigir seria trocar um
palpite por outro. Rebaixa a confiança e entrega a lista para revisão humana —
que é o papel da nutricionista no produto.

Uso:
    python -m app.nutrition.auditoria            # só relatório
    python -m app.nutrition.auditoria --aplicar  # marca suspeito no banco
"""

import argparse
import logging
from dataclasses import dataclass

from app import config
from app.nutrition import taco

log = logging.getLogger("auditoria")

# Acima disto, a diferença deixa de ser explicável por preparo (mais óleo, mais
# sal, ponto de cozimento) e passa a indicar erro de valor. 40% é folgado de
# propósito: a tabela de medidas caseiras registra pratos brasileiros preparados,
# a TACO registra o alimento — refogar arroz em óleo muda o número legitimamente.
DIVERGENCIA_MAXIMA = 0.40

# Piso de similaridade de nome. Alto porque comparar alimentos diferentes produz
# alarme falso, que é pior que não auditar.
# 0.65 casa "Abobrinha Cozida" com "Abobrinha, italiana, cozida" — a TACO só
# acrescenta a variedade. Dobra a cobertura (14% → 27%) sem perder precisão,
# porque a incompatibilidade de PREPARO é barrada antes da pontuação.
SIMILARIDADE_MINIMA = 0.65


@dataclass
class Divergencia:
    alimento_id: int
    nome: str
    fonte: str
    kcal_base: float
    kcal_taco: float
    nome_taco: str
    similaridade: float

    @property
    def razao(self) -> float:
        return self.kcal_base / self.kcal_taco if self.kcal_taco else float("inf")

    def __str__(self) -> str:
        return (
            f"{self.nome[:34]:<36} fonte={self.fonte or '-':<5} "
            f"base={self.kcal_base:>7.1f}  taco={self.kcal_taco:>7.1f}  "
            f"{self.razao:>5.2f}x   ({self.nome_taco[:32]})"
        )


def _conectar():
    import psycopg

    return psycopg.connect(config.DATABASE_URL)


def _alimentos_por_100g(cur) -> list[tuple]:
    cur.execute(
        """
        SELECT a.id, a.nome, COALESCE(a.fonte,''), p.kcal
          FROM nutri_alimentos a
          JOIN nutri_porcoes p ON p.alimento_id = a.id
         WHERE p.medida_label = '100g' AND p.kcal > 0
         ORDER BY a.nome
        """
    )
    return cur.fetchall()


def auditar() -> tuple[list[Divergencia], int, int]:
    """Devolve (divergências, casados, total)."""
    divergencias: list[Divergencia] = []
    casados = 0

    with _conectar() as conn, conn.cursor() as cur:
        linhas = _alimentos_por_100g(cur)

    for alimento_id, nome, fonte, kcal in linhas:
        ref, score = taco.procurar(nome, minimo=SIMILARIDADE_MINIMA)
        if ref is None:
            continue
        casados += 1
        if not ref.kcal:
            continue
        if abs(float(kcal) - ref.kcal) / ref.kcal > DIVERGENCIA_MAXIMA:
            divergencias.append(
                Divergencia(alimento_id, nome, fonte, float(kcal), ref.kcal, ref.nome, score)
            )

    return divergencias, casados, len(linhas)


def aplicar(divergencias: list[Divergencia]) -> int:
    """Marca como suspeitas TODAS as porções dos alimentos divergentes.

    A porção herda o erro do alimento: se o valor por 100 g está errado, a concha
    e a colher derivadas dele também estão.
    """
    if not divergencias:
        return 0
    ids = [d.alimento_id for d in divergencias]
    with _conectar() as conn, conn.cursor() as cur:
        cur.execute("UPDATE nutri_porcoes SET suspeito = true WHERE alimento_id = ANY(%s)", (ids,))
        afetadas = cur.rowcount
        conn.commit()
    return afetadas


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aplicar", action="store_true", help="marca suspeito no banco")
    args = ap.parse_args()

    divergencias, casados, total = auditar()
    divergencias.sort(key=lambda d: abs(d.razao - 1), reverse=True)

    print()
    print("AUDITORIA DA BASE NUTRICIONAL vs TACO (por 100 g)")
    print("=" * 96)
    print(f"alimentos na base: {total} | com correspondência na TACO: {casados} "
          f"({casados / total:.0%}) | divergentes acima de {DIVERGENCIA_MAXIMA:.0%}: {len(divergencias)}")
    print("-" * 96)
    for d in divergencias:
        print(d)
    print("-" * 96)
    print(f"{total - casados} alimentos sem correspondência — preparações brasileiras que a TACO "
          "não cataloga; ficam para revisão manual.")

    if args.aplicar:
        n = aplicar(divergencias)
        print(f"\n{n} porções marcadas como suspeitas (confiança do cálculo cai para 'media').")
    else:
        print("\n(relatório apenas; use --aplicar para marcar no banco)")


if __name__ == "__main__":
    main()
