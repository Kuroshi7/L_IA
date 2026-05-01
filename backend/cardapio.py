import json
import unicodedata
from datetime import date
from functools import lru_cache
from pathlib import Path

CARDAPIO_PATH = Path(__file__).parent / "data" / "cardapio.json"


@lru_cache(maxsize=1)
def carregar_cardapio() -> dict:
    with open(CARDAPIO_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    return sem_acento.lower().strip()


def get_pratos_do_dia(dia: str = "hoje") -> list[dict]:
    cardapio = carregar_cardapio()
    dias = cardapio["dias"]
    if not dias:
        return []

    alvo = _normalizar(dia)
    if alvo in {"hoje", "today", ""}:
        hoje_iso = date.today().strftime("%Y-%m-%d")
        for d in dias:
            if d["data"] == hoje_iso:
                return d["pratos"]
        return dias[0]["pratos"]

    for d in dias:
        if d["data"] == dia or _normalizar(d["dia_semana"]) == alvo:
            return d["pratos"]

    return dias[0]["pratos"]


def get_cardapio_semana() -> list[dict]:
    return carregar_cardapio()["dias"]


def get_prato_por_id(prato_id: int) -> dict | None:
    for dia in carregar_cardapio()["dias"]:
        for prato in dia["pratos"]:
            if prato["id"] == prato_id:
                return prato
    return None


def vocabulario_dominio() -> set[str]:
    """Tokens normalizados extraídos do cardápio para o guardrail de escopo."""
    tokens: set[str] = set()
    for dia in carregar_cardapio()["dias"]:
        for prato in dia["pratos"]:
            tokens.update(_normalizar(prato["nome"]).split())
            tokens.update(_normalizar(ing) for ing in prato.get("ingredientes", []))
            tokens.update(_normalizar(a) for a in prato.get("alergenos", []))
            tokens.update(_normalizar(r) for r in prato.get("restricoes_atendidas", []))
    return {t for t in tokens if len(t) >= 3}


def formatar_pratos_resumido(pratos: list[dict]) -> list[dict]:
    return [
        {"id": p["id"], "nome": p["nome"], "categoria": p["categoria"]}
        for p in pratos
    ]


def prato_atende_restricao(prato: dict, restricao: str) -> bool:
    r = _normalizar(restricao)
    nao_indicado = {_normalizar(x) for x in prato.get("nao_indicado_para", [])}
    if r in nao_indicado:
        return False
    atendidas = {_normalizar(x) for x in prato.get("restricoes_atendidas", [])}
    return r in atendidas or _equivalencia_restricao(r, atendidas, nao_indicado)


def _equivalencia_restricao(r: str, atendidas: set[str], nao_indicado: set[str]) -> bool:
    equivalencias = {
        "celiaco": "sem gluten",
        "intolerante a gluten": "sem gluten",
        "intolerante ao gluten": "sem gluten",
        "intolerante a lactose": "sem lactose",
        "sem leite": "sem lactose",
    }
    eq = equivalencias.get(r)
    if not eq:
        return False
    if eq in atendidas:
        return True
    return False


def prato_seguro_para_alergias(prato: dict, alergias: list[str]) -> bool:
    alergenos_prato = {_normalizar(a) for a in prato.get("alergenos", [])}
    for alergia in alergias:
        a = _normalizar(alergia)
        a_limpo = a.replace("alergico a ", "").replace("alergia a ", "").strip()
        if a in alergenos_prato or a_limpo in alergenos_prato:
            return False
        if any(a_limpo in alg or alg in a_limpo for alg in alergenos_prato if alg):
            return False
    return True


def prato_combina_preferencia(prato: dict, preferencia: str) -> bool:
    p = _normalizar(preferencia)
    atendidas = {_normalizar(x) for x in prato.get("restricoes_atendidas", [])}
    if p in atendidas:
        return True
    ingredientes = {_normalizar(i) for i in prato.get("ingredientes", [])}
    return p in ingredientes or any(p in ing for ing in ingredientes)
