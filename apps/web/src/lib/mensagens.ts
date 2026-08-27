import { ApiError } from "./api";

/**
 * Traduz a falha técnica para o que a pessoa precisa saber.
 *
 * O front antigo jogava na tela o corpo cru da resposta HTTP e frases como
 * "O backend está rodando?" — texto escrito para quem tem o servidor na mão, não
 * para quem está usando o produto. O detalhe técnico continua existindo: vai
 * para o `console.error` de quem chamou, onde é útil.
 */
export function mensagemAdmin(erro: unknown): string {
  if (erro instanceof ApiError) {
    if (erro.status === 401) return "Sua chave de acesso não foi aceita. Confira o token de gestão e tente de novo.";
    if (erro.status === 403) return "Esta conta não tem permissão para esta ação.";
    if (erro.status === 404) return "Não encontrei este registro — ele pode ter sido removido por outra pessoa.";
    if (erro.status === 409) return "Alguém alterou este registro antes de você. Recarregue a tela para ver o estado atual.";
    if (erro.status === 422 || erro.status === 400) return "Algum campo ficou fora do formato esperado. Revise os dados e tente de novo.";
    if (erro.status >= 500) return "O servidor não conseguiu concluir. Tente de novo em alguns segundos.";
  }
  return "Não consegui completar a operação. Verifique sua conexão e tente de novo.";
}

/** Versão para as telas do cliente, onde nem "token" nem "registro" fazem sentido. */
export function mensagemCliente(): string {
  return "Não consegui carregar isso agora. Verifique sua conexão e tente de novo.";
}
