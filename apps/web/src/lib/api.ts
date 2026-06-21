import type {
  Alimento,
  AlimentoInput,
  CardapioDia,
  CardapioItemInput,
  CardapioSemana,
  ChatResponse,
  NutriAlimento,
  Prato,
  Unidade,
} from "../types";

const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8080";

async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(`${BASE_URL}${path}`);
  if (!r.ok) throw new Error(`GET ${path} falhou (${r.status})`);
  return r.json() as Promise<T>;
}

export async function listarUnidades(): Promise<Unidade[]> {
  const data = await getJSON<{ unidades: Unidade[] | null }>("/unidades");
  return data.unidades ?? [];
}

export async function getCardapio(unidadeId: number): Promise<Prato[]> {
  const data = await getJSON<{ pratos: Prato[] | null }>(`/unidades/${unidadeId}/cardapio`);
  return data.pratos ?? [];
}

export async function getSaudacao(): Promise<string> {
  const data = await getJSON<{ mensagem: string }>("/chat/saudacao");
  return data.mensagem;
}

export async function enviarMensagem(
  unidadeId: number,
  sessionId: string | null,
  mensagem: string,
): Promise<ChatResponse> {
  const r = await fetch(`${BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ unidade_id: unidadeId, session_id: sessionId ?? "", mensagem }),
  });
  if (!r.ok) throw new Error((await r.text()) || "Erro ao enviar mensagem");
  return r.json() as Promise<ChatResponse>;
}

export async function limparConversa(sessionId: string): Promise<void> {
  if (!sessionId) return;
  await fetch(`${BASE_URL}/chat/${sessionId}`, { method: "DELETE" });
}

// ============================ Admin ============================

const ADMIN_TOKEN_KEY = "menuai_admin_token";

export function getAdminToken(): string {
  return (
    localStorage.getItem(ADMIN_TOKEN_KEY) ||
    (import.meta.env.VITE_ADMIN_TOKEN as string | undefined) ||
    ""
  );
}

export function setAdminToken(token: string): void {
  localStorage.setItem(ADMIN_TOKEN_KEY, token.trim());
}

async function adminFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Admin-Token": getAdminToken(),
      ...(init?.headers || {}),
    },
  });
  if (r.status === 401) throw new Error("Não autorizado — verifique o token de admin.");
  if (!r.ok) throw new Error((await r.text()) || `${init?.method ?? "GET"} ${path} falhou (${r.status})`);
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

export const adminListarAlimentos = (unidadeId: number) =>
  adminFetch<{ alimentos: Alimento[] | null }>(`/admin/unidades/${unidadeId}/alimentos`).then(
    (d) => d.alimentos ?? [],
  );

export const adminCriarAlimento = (unidadeId: number, body: AlimentoInput) =>
  adminFetch<Alimento>(`/admin/unidades/${unidadeId}/alimentos`, {
    method: "POST",
    body: JSON.stringify(body),
  });

export const adminAtualizarAlimento = (alimentoId: number, body: AlimentoInput) =>
  adminFetch<Alimento>(`/admin/alimentos/${alimentoId}`, {
    method: "PUT",
    body: JSON.stringify(body),
  });

export const adminSetAlimentoAtivo = (alimentoId: number, ativo: boolean) =>
  adminFetch<{ id: number; ativo: boolean }>(`/admin/alimentos/${alimentoId}/ativo`, {
    method: "PATCH",
    body: JSON.stringify({ ativo }),
  });

export const adminBuscarNutri = (q: string) =>
  adminFetch<{ nutri_alimentos: NutriAlimento[] | null }>(
    `/admin/nutri-alimentos?q=${encodeURIComponent(q)}`,
  ).then((d) => d.nutri_alimentos ?? []);

export const adminGetCardapioSemana = (unidadeId: number, inicio: string) =>
  adminFetch<CardapioSemana>(`/admin/unidades/${unidadeId}/cardapio-semana?inicio=${inicio}`);

export const adminSetCardapioItens = (unidadeId: number, data: string, itens: CardapioItemInput[]) =>
  adminFetch<CardapioDia>(`/admin/unidades/${unidadeId}/cardapio-dia/${data}/itens`, {
    method: "PUT",
    body: JSON.stringify({ itens }),
  });

export const adminCopiarSemana = (unidadeId: number, origem: string, destino: string) =>
  adminFetch<CardapioSemana>(`/admin/unidades/${unidadeId}/cardapio-semana/copiar`, {
    method: "POST",
    body: JSON.stringify({ origem, destino }),
  });
