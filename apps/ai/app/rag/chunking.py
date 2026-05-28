"""Chunking simples por caracteres com leve overlap.

Boas práticas 2026: pedaços ~512 tokens com recursive splitting e overlap pequeno
funcionam tão bem quanto estratégias mais caras. Aqui usamos uma aproximação por
caracteres (sem dependência extra) adequada aos guias curtos da Fase 1.
"""

_SEPARADORES = ["\n\n", "\n", ". ", " "]


def chunk(texto: str, tamanho: int = 800, overlap: int = 100) -> list[str]:
    texto = texto.strip()
    if len(texto) <= tamanho:
        return [texto] if texto else []

    pedacos: list[str] = []
    inicio = 0
    while inicio < len(texto):
        fim = min(inicio + tamanho, len(texto))
        corte = fim
        if fim < len(texto):
            for sep in _SEPARADORES:
                idx = texto.rfind(sep, inicio, fim)
                if idx > inicio:
                    corte = idx + len(sep)
                    break
        pedacos.append(texto[inicio:corte].strip())
        if corte >= len(texto):
            break
        inicio = max(corte - overlap, inicio + 1)
    return [p for p in pedacos if p]
