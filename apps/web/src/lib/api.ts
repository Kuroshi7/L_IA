import type { ChatResponse, Prato, Unidade } from "../types";

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
