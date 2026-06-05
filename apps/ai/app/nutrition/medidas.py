"""Legenda de medidas caseiras (pág. 2 do livro) e parser de rótulos.

Converte um rótulo cru como "COL S CH PICADO" em
{medida_cod: "COL S", tamanho: None, estado: "CH"} para preencher nutri_porcoes.
"""

import re
import unicodedata

# Prefixos de medida ordenados do mais longo para o mais curto (match guloso).
MEDIDA_PREFIXOS = [
    ("COL CAFE", "COL CAFE", "colher de café"),
    ("COL CHA", "COL CHA", "colher de chá"),
    ("COL SOB", "COL SOB", "colher de sobremesa"),
    ("COL PAU", "COL PAU", "colher de pau"),
    ("COL A", "COL A", "colher de arroz"),
    ("COL S", "COL S", "colher de sopa"),
    ("PT SOB", "PT SOB", "prato de sobremesa"),
    ("PT F", "PT F", "prato fundo"),
    ("PT R", "PT R", "prato raso"),
    ("COPO D", "COPO D", "copo duplo"),
    ("COPO P", "COPO P", "copo pequeno"),
    ("ESC", "ESC", "escumadeira"),
    ("CO", "CO", "concha"),
    ("FT", "FT", "fatia"),
    ("PED", "PED", "pedaço"),
    ("UND", "UND", "unidade"),
    ("FILE", "FILE", "filé"),
    ("POSTA", "POSTA", "posta"),
    ("FOLHA", "FOLHA", "folha"),
    ("RAMO", "RAMO", "ramo"),
    ("PEGADOR", "PEGADOR", "pegador"),
    ("PIRES", "PIRES", "pires"),
    ("COPO", "COPO", "copo"),
    ("X", "X", "xícara"),
]

_TAMANHOS = {"GG", "G", "M", "P", "D"}
_ESTADOS = {"CH", "N", "R"}


def normalizar(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", s.lower().strip())


def parse_medida_label(label: str) -> dict:
    """Extrai (medida_cod, tamanho, estado) de um rótulo cru. Não falha: o que não
    casar fica como None e o rótulo original é preservado pelo chamador."""
    up = re.sub(r"\s+", " ", label.upper().strip())
    up_norm = (
        unicodedata.normalize("NFKD", up).encode("ascii", "ignore").decode("ascii")
    )

    cod = None
    rest = up_norm
    for prefixo, code, _desc in MEDIDA_PREFIXOS:
        if up_norm == prefixo or up_norm.startswith(prefixo + " "):
            cod = code
            rest = up_norm[len(prefixo):].strip()
            break

    tamanho = None
    estado = None
    for tok in rest.split():
        if tok in _TAMANHOS and tamanho is None:
            tamanho = tok
        elif tok in _ESTADOS and estado is None:
            estado = tok

    return {"medida_cod": cod, "tamanho": tamanho, "estado": estado}
