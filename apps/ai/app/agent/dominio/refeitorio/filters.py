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
    """Versão enxuta para listagem. O aviso de conflito com o perfil SEMPRE
    acompanha — é a única informação da listagem que pode evitar um acidente."""
    resumo = {"id": prato["id"], "nome": prato["nome"], "categoria": prato.get("categoria", "")}
    if prato.get("conflita_com_perfil"):
        resumo["conflita_com_perfil"] = prato["conflita_com_perfil"]
    return resumo


def conflitos_com_perfil(prato: dict, perfil: dict | None) -> list[str]:
    """Por que este prato é inadequado para esta pessoa, na voz certa.

    Existe porque filtrar não bastou. `filtrar_pratos` já devolve só o que é
    seguro, mas o modelo às vezes recomenda a partir da lista crua — e o produto
    não pode esconder o prato, porque a pessoa tem o direito de saber o que está
    sendo servido.

    O texto é escrito para ser PARAFRASEADO pela Lia, e por isso já vem na
    posição de autoridade correta: quem declarou a alergia foi a pessoa, e o
    ingrediente é fato verificável do prato. O assistente não determina o que
    alguém pode comer — ele cruza as duas coisas e devolve o motivo.
    """
    if not perfil:
        return []

    motivos = []
    alergias = [a for a in (perfil.get("alergias") or []) if a]
    if not prato_seguro_para_alergias(prato, alergias):
        alergenos = {normalizar(a) for a in prato.get("alergenos", [])}
        culpadas = [
            a for a in alergias
            if normalizar(a).replace("alergico a ", "") in alergenos
            or any(normalizar(a).replace("alergico a ", "") in x for x in alergenos)
        ] or alergias
        motivos.append(
            f"você informou alergia a {', '.join(culpadas)} — e este prato leva "
            f"{', '.join(sorted(prato.get('alergenos') or culpadas))}"
        )

    for restricao in (perfil.get("restricoes") or []):
        if restricao and not prato_atende_restricao(prato, restricao):
            ingredientes = [i for i in (prato.get("ingredientes") or [])][:3]
            porque = f" — leva {', '.join(ingredientes)}" if ingredientes else ""
            motivos.append(f"você informou a restrição '{restricao}', e este prato não atende{porque}")

    return motivos
