"""Cliente HTTP da API interna do serviço Go (fonte da verdade do domínio).

As tools do agente obtêm cardápio, perfil do usuário e medidas caseiras por aqui,
em vez de ler arquivos locais. Isso mantém uma única fonte de schema/regra.
"""

import logging

import httpx

from app import config

log = logging.getLogger("go_api")

_client = httpx.Client(base_url=config.API_INTERNAL_URL, timeout=10.0)


def get_cardapio(unidade_id: int, dia: str = "hoje") -> dict:
    """Retorna o cardápio do dia de uma unidade: {id, unidade_id, data, dia_semana, pratos:[...]}."""
    r = _client.get(f"/internal/cardapio/{unidade_id}/{dia or 'hoje'}")
    r.raise_for_status()
    return r.json()


def get_pratos(unidade_id: int, dia: str = "hoje") -> list[dict]:
    return get_cardapio(unidade_id, dia).get("pratos") or []


def get_perfil(usuario_id: int) -> dict:
    """Perfil nutricional do usuário: {nome, restricoes, preferencias, alergias, imc, meta_calorica_kcal}."""
    r = _client.get(f"/internal/usuario/{usuario_id}/perfil")
    r.raise_for_status()
    return r.json()


def get_medidas_caseiras() -> list[dict]:
    r = _client.get("/internal/medidas-caseiras")
    r.raise_for_status()
    return r.json().get("medidas") or []


def calcular_consumo(itens: list[dict]) -> dict:
    """Envia itens estruturados ({alimento, medida, quantidade}) e recebe os totais
    nutricionais calculados deterministicamente contra a base de medidas caseiras."""
    r = _client.post("/internal/consumo/calcular", json={"itens": itens})
    r.raise_for_status()
    return r.json()
