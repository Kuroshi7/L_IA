import type {
  AdminUsuario,
  Alimento,
  AlimentoInput,
  CardapioDia,
  CardapioItemInput,
  CardapioSemana,
  ChatResponse,
  DesperdicioRelatorio,
  GamificacaoResumo,
  NutriAlimento,
  Prato,
  RankingEntry,
  Unidade,
  UsuarioComPerfil,
  UsuarioInput,
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

/**
 * Unidades com cache de processo.
 *
 * A lateral mostra o nome da unidade atual em toda tela; sem cache, cada
 * navegação repetiria o mesmo GET. A lista muda raramente (é o gestor que
 * cadastra), então uma promessa memoizada resolve — e `esquecerUnidades()`
 * limpa quando o admin mexe no cadastro.
 *
 * Multi-tenant: hoje o escopo do cache é a própria instalação (BASE_URL aponta
 * para um cliente). Quando a mesma origem servir vários tenants, esta variável
 * vira um Map com o tenant na chave — senão uma loja vê a lista da outra.
 */
let cacheUnidades: Promise<Unidade[]> | null = null;

export function listarUnidadesCache(): Promise<Unidade[]> {
  if (!cacheUnidades) {
    cacheUnidades = listarUnidades().catch((err) => {
      cacheUnidades = null; // erro não vira cache: a próxima tela tenta de novo
      throw err;
    });
  }
  return cacheUnidades;
}

export function esquecerUnidades(): void {
  cacheUnidades = null;
}

// ---- Unidade escolhida ------------------------------------------------------
// Guardada para o app abrir direto na conversa, como um aplicativo faria, em vez
// de perguntar "qual unidade?" toda vez que a pessoa entra.

const UNIDADE_ID_KEY = "menuai_unidade_id";

export function getUnidadeSalva(): number | null {
  try {
    const bruto = localStorage.getItem(UNIDADE_ID_KEY);
    const id = Number(bruto);
    return bruto && Number.isFinite(id) && id > 0 ? id : null;
  } catch {
    return null;
  }
}

export function setUnidadeSalva(id: number): void {
  try {
    localStorage.setItem(UNIDADE_ID_KEY, String(id));
  } catch {
    /* sem persistência (aba anônima): a sessão atual continua funcionando */
  }
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
  usuarioId?: number | null,
): Promise<ChatResponse> {
  const r = await fetch(`${BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      unidade_id: unidadeId,
      session_id: sessionId ?? "",
      mensagem,
      ...(usuarioId ? { usuario_id: usuarioId } : {}),
    }),
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

/**
 * Chamadas de gestão.
 *
 * Havia duas funções quase idênticas aqui (`adminFetch` e `adminRequest`), e a
 * diferença — só uma preservava o status HTTP — era invisível em quem chamava.
 * Resultado: metade das telas de admin não conseguia distinguir "token errado"
 * de "servidor fora", e mostrava a mesma frase genérica para as duas. Agora é
 * uma função só, e todo erro chega como `ApiError` com status.
 */
const adminFetch = <T,>(path: string, init?: RequestInit): Promise<T> => adminRequest<T>(path, init);

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

// ============================ Erros com status ============================

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

// ============================ Usuário / perfil ============================

const USUARIO_ID_KEY = "menuai_usuario_id";

export function getUsuarioIdSalvo(): number | null {
  const raw = localStorage.getItem(USUARIO_ID_KEY);
  const id = Number(raw);
  return raw && Number.isFinite(id) && id > 0 ? id : null;
}

export function setUsuarioIdSalvo(id: number): void {
  localStorage.setItem(USUARIO_ID_KEY, String(id));
}

export function limparUsuarioIdSalvo(): void {
  localStorage.removeItem(USUARIO_ID_KEY);
}

async function sendJSON<T>(path: string, method: "POST" | "PUT", body: unknown): Promise<T> {
  const r = await fetch(`${BASE_URL}${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new ApiError((await r.text()) || `${method} ${path} falhou (${r.status})`, r.status);
  return r.json() as Promise<T>;
}

export const criarUsuario = (body: UsuarioInput) =>
  sendJSON<UsuarioComPerfil>("/usuarios", "POST", body);

// Login por telefone + PIN — retorna o mesmo shape de criarUsuario.
// Erros vêm como ApiError (401 = credenciais incorretas).
export const loginUsuario = (telefone: string, pin: string) =>
  sendJSON<UsuarioComPerfil>("/usuarios/login", "POST", { telefone, pin });

export const getUsuario = (id: number) => getJSON<UsuarioComPerfil>(`/usuarios/${id}`);

export const atualizarUsuario = (id: number, body: UsuarioInput) =>
  sendJSON<UsuarioComPerfil>(`/usuarios/${id}`, "PUT", body);

export const getGamificacao = (usuarioId: number) =>
  getJSON<GamificacaoResumo>(`/usuarios/${usuarioId}/gamificacao`);

export const getRanking = (unidadeId: number, limit = 10) =>
  getJSON<{ ranking: RankingEntry[] | null }>(`/unidades/${unidadeId}/ranking?limit=${limit}`).then(
    (d) => d.ranking ?? [],
  );

// ============================ Admin: unidades / usuários / desperdício ============================

// Igual ao adminFetch, mas propaga o status HTTP (ex.: 409 de slug duplicado).
async function adminRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Admin-Token": getAdminToken(),
      ...(init?.headers || {}),
    },
  });
  if (r.status === 401) throw new ApiError("Não autorizado — verifique o token de admin.", 401);
  if (!r.ok) {
    throw new ApiError(
      (await r.text()) || `${init?.method ?? "GET"} ${path} falhou (${r.status})`,
      r.status,
    );
  }
  if (r.status === 204) return undefined as T;
  return r.json() as Promise<T>;
}

export const adminListarUnidades = () =>
  adminRequest<{ unidades: Unidade[] | null }>("/admin/unidades").then((d) => d.unidades ?? []);

export const adminCriarUnidade = (body: { nome: string; slug: string }) =>
  adminRequest<Unidade>("/admin/unidades", { method: "POST", body: JSON.stringify(body) });

export const adminAtualizarUnidade = (id: number, body: { nome: string; slug: string }) =>
  adminRequest<Unidade>(`/admin/unidades/${id}`, { method: "PUT", body: JSON.stringify(body) });

export const adminSetUnidadeAtiva = (id: number, ativo: boolean) =>
  adminRequest<{ id: number; ativo: boolean }>(`/admin/unidades/${id}/ativo`, {
    method: "PATCH",
    body: JSON.stringify({ ativo }),
  });

export const adminListarUsuarios = (unidadeId?: number) =>
  adminRequest<{ usuarios: AdminUsuario[] | null }>(
    `/admin/usuarios${unidadeId ? `?unidade_id=${unidadeId}` : ""}`,
  ).then((d) => d.usuarios ?? []);

export const adminGetDesperdicio = (unidadeId: number, de?: string, ate?: string) => {
  const qs = new URLSearchParams();
  if (de) qs.set("de", de);
  if (ate) qs.set("ate", ate);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  return adminRequest<DesperdicioRelatorio>(`/admin/unidades/${unidadeId}/desperdicio${suffix}`);
};
