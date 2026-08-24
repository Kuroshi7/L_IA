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
    """Por que este prato é incompatível com o perfil desta pessoa.

    Existe porque filtrar não bastou. `filtrar_pratos` já devolve só o que é
    seguro, mas o modelo às vezes recomenda a partir da lista CRUA de
    `listar_pratos_do_dia` — e a regra contratual obriga mostrar essa lista
    completa. Medido: numa a cada três conversas a salada com amendoim era
    recomendada a quem tem alergia a amendoim no perfil.

    Esconder o prato não é opção (a regra contratual manda listar tudo). Então o
    aviso vai junto do item, no mesmo dicionário que o modelo lê. Segurança
    alimentar não pode depender de o modelo lembrar de chamar a tool certa.
    """
    if not perfil:
        return []

    motivos = []
    alergias = [a for a in (perfil.get("alergias") or []) if a]
    if not prato_seguro_para_alergias(prato, alergias):
        alergenos = {normalizar(a) for a in prato.get("alergenos", [])}
        culpadas = [a for a in alergias if normalizar(a).replace("alergico a ", "") in alergenos
                    or any(normalizar(a).replace("alergico a ", "") in x for x in alergenos)]
        motivos.append(f"ALERGIA: contém {', '.join(culpadas or alergias)}")

    for restricao in (perfil.get("restricoes") or []):
        if restricao and not prato_atende_restricao(prato, restricao):
            motivos.append(f"RESTRIÇÃO: não atende '{restricao}'")

    return motivos
