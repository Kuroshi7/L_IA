"""Filtragem determinística de pratos por restrição/alergia/preferência.

Opera sobre o shape de prato retornado pela API Go (nutrição em campos planos:
calorias, proteinas_g, carboidratos_g, gorduras_g). Garante que, ex., um
vegetariano nunca veja um prato com carne — a regra está no código, não no prompt.
"""

import unicodedata


def normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.lower().strip()


_EQUIVALENCIAS = {
    "celiaco": "sem gluten",
    "intolerante a gluten": "sem gluten",
    "intolerante ao gluten": "sem gluten",
    "intolerante a lactose": "sem lactose",
    "sem leite": "sem lactose",
}


def prato_atende_restricao(prato: dict, restricao: str) -> bool:
    r = normalizar(restricao)
    nao_indicado = {normalizar(x) for x in prato.get("nao_indicado_para", [])}
    if r in nao_indicado:
        return False
    atendidas = {normalizar(x) for x in prato.get("restricoes_atendidas", [])}
    if r in atendidas:
        return True
    eq = _EQUIVALENCIAS.get(r)
    return bool(eq and eq in atendidas)


def prato_seguro_para_alergias(prato: dict, alergias: list[str]) -> bool:
    alergenos_prato = {normalizar(a) for a in prato.get("alergenos", [])}
    for alergia in alergias:
        a = normalizar(alergia)
        a_limpo = a.replace("alergico a ", "").replace("alergia a ", "").strip()
        if a in alergenos_prato or a_limpo in alergenos_prato:
            return False
        if any(a_limpo and (a_limpo in alg or alg in a_limpo) for alg in alergenos_prato):
            return False
    return True


def prato_combina_preferencia(prato: dict, preferencia: str) -> bool:
    p = normalizar(preferencia)
    atendidas = {normalizar(x) for x in prato.get("restricoes_atendidas", [])}
    if p in atendidas:
        return True
    ingredientes = {normalizar(i) for i in prato.get("ingredientes", [])}
    return p in ingredientes or any(p in ing for ing in ingredientes)


def resumir(prato: dict) -> dict:
    return {"id": prato["id"], "nome": prato["nome"], "categoria": prato.get("categoria", "")}
