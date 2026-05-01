const BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export function gerarSessionId() {
  return "user_" + Math.random().toString(36).substring(2, 11) + Date.now().toString(36);
}

export function getOuCriarSessionId() {
  let id = localStorage.getItem("lia_session_id");
  if (!id) {
    id = gerarSessionId();
    localStorage.setItem("lia_session_id", id);
  }
  return id;
}

export async function getSaudacao() {
  const r = await fetch(`${BASE_URL}/chat/saudacao`);
  if (!r.ok) throw new Error("Falha ao buscar saudação");
  const data = await r.json();
  return data.mensagem;
}

export async function enviarMensagem(sessionId, mensagem) {
  const r = await fetch(`${BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, mensagem }),
  });
  if (!r.ok) {
    const erro = await r.text();
    throw new Error(erro || "Erro ao enviar mensagem");
  }
  return r.json();
}

export async function limparConversa(sessionId) {
  await fetch(`${BASE_URL}/chat/${sessionId}`, { method: "DELETE" });
}
