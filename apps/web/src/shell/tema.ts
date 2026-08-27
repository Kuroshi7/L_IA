/**
 * Tema claro/escuro.
 *
 * Três estados na interface (claro / escuro / seguir o sistema), mas um só no
 * DOM: `data-tema` sempre vale "claro" ou "escuro". Resolver "sistema" aqui, e
 * não no CSS, evita duplicar a paleta inteira dentro de um `prefers-color-scheme`
 * e é o que permite o usuário escolher um tema diferente do sistema — que é
 * comportamento de app, não de site.
 *
 * O preço é o flash de tela branca antes do bundle carregar; pago por um script
 * inline no `index.html`, que lê a mesma chave.
 */

export type Preferencia = "claro" | "escuro" | "sistema";

export const CHAVE_TEMA = "menuai_tema";

export function lerPreferencia(): Preferencia {
  try {
    const bruto = localStorage.getItem(CHAVE_TEMA);
    return bruto === "claro" || bruto === "escuro" ? bruto : "sistema";
  } catch {
    // Safari em navegação privada bloqueia localStorage. Tema não é motivo para
    // derrubar o app.
    return "sistema";
  }
}

export function sistemaEscuro(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

export function aplicarPreferencia(pref: Preferencia): void {
  const escuro = pref === "escuro" || (pref === "sistema" && sistemaEscuro());
  document.documentElement.setAttribute("data-tema", escuro ? "escuro" : "claro");
  // A barra do navegador no Android/iOS acompanha o tema — sem isso, a moldura
  // do sistema fica branca em volta de um app escuro.
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute("content", escuro ? "#151310" : "#f4f0e8");
}

export function salvarPreferencia(pref: Preferencia): void {
  try {
    if (pref === "sistema") localStorage.removeItem(CHAVE_TEMA);
    else localStorage.setItem(CHAVE_TEMA, pref);
  } catch {
    /* sem persistência; a sessão atual continua respeitando a escolha */
  }
  aplicarPreferencia(pref);
}
