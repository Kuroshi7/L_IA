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


def registrar_consumo(
    unidade_id: int,
    itens: list[dict],
    usuario_id: int | None = None,
    sobras: list[dict] | None = None,
) -> dict:
    """Registra o consumo (e sobras) de uma refeição: calcula, persiste, pontua o
    usuário (gamificação) e alimenta o agregado de desperdício do admin."""
    body: dict = {"unidade_id": unidade_id, "itens": itens}
    if usuario_id:
        body["usuario_id"] = usuario_id
    if sobras:
        body["sobras"] = sobras
    r = _client.post("/internal/consumo/registrar", json=body)
    r.raise_for_status()
    return r.json()


def get_cardapio_semana(unidade_id: int, inicio: str = "") -> dict:
    """Grade seg–sex do cardápio: {unidade_id, inicio, dias: [{data, dia_semana, pratos}]}.
    `inicio` = segunda-feira ISO; vazio usa a semana atual."""
    params = {"inicio": inicio} if inicio else None
    r = _client.get(f"/internal/cardapio-semana/{unidade_id}", params=params)
    r.raise_for_status()
    return r.json()


def get_gamificacao(usuario_id: int) -> dict:
    """Estado de gamificação: {gamificacao: {pontos, nivel, streak_dias}, eventos: [...]}"""
    r = _client.get(f"/internal/usuario/{usuario_id}/gamificacao")
    r.raise_for_status()
    return r.json()


def get_unidades() -> list[dict]:
    """Unidades ativas (rota pública servida pelo mesmo host): [{id, nome, slug}]."""
    r = _client.get("/unidades")
    r.raise_for_status()
    return r.json().get("unidades") or []


def get_usuario_por_telegram(chat_id: int) -> dict | None:
    """Usuário vinculado a um chat do Telegram, ou None se não houver vínculo."""
    r = _client.get(f"/internal/usuario/por-telegram/{chat_id}")
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def vincular_telegram(usuario_id: int, chat_id: int) -> dict:
    """Associa um chat do Telegram a um usuário cadastrado."""
    r = _client.post(f"/internal/usuario/{usuario_id}/vincular-telegram", json={"chat_id": chat_id})
    r.raise_for_status()
    return r.json()
