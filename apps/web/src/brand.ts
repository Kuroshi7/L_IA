/**
 * Identidade da instalação — nome do assistente, produto e cores da marca.
 *
 * Por que isto existe (WEB-11 / regra "SaaS desde o 1º commit"):
 * antes, "Lia" estava escrito em oito arquivos JSX e a paleta em `styles.css`.
 * O segundo cliente exigiria fork ou refactor — exatamente o anti-padrão que a
 * gente evita. Aqui a marca vira **dado**, com um ponto de escopo só.
 *
 * Hoje (instalação por cliente): os valores vêm de constante + env de build.
 * Amanhã (multi-tenant): a mesma estrutura chega por unidade/tenant, do banco
 * (ex.: `GET /unidades/:id/tema`), e passa por `aplicarTema()` em runtime. Nada
 * de novo precisa ser escrito no CSS — os tokens já são custom properties, e
 * custom property se sobrescreve em runtime. O seam já está aberto; o que falta
 * é o endpoint do lado do Go.
 *
 * Regra prática: nenhum componente escreve "Lia" nem um `#hex`. Sempre daqui.
 */

export interface TemaMarca {
  marca?: string;
  marcaForte?: string;
  marcaSuave?: string;
  marcaContraste?: string;
  acento?: string;
  acentoTexto?: string;
  acentoSuave?: string;
}

export interface Marca {
  /** Nome do assistente, como o usuário o chama. */
  assistente: string;
  /** Uma letra para o selo. Derivada do nome, mas sobrescrevível. */
  monograma: string;
  /** Nome do produto/plataforma (aparece em título de aba e no console). */
  produto: string;
  /** Uma linha sobre o que o assistente faz — usada em `<meta description>`. */
  descricao: string;
  /** Cores. Vazio = usa o tema padrão de `tokens.css`. */
  tema?: TemaMarca;
}

const env = import.meta.env;

export const marca: Marca = {
  assistente: (env.VITE_MARCA_ASSISTENTE as string | undefined) || "Lia",
  monograma: (env.VITE_MARCA_MONOGRAMA as string | undefined) || "L",
  produto: (env.VITE_MARCA_PRODUTO as string | undefined) || "Menu-AI",
  descricao:
    (env.VITE_MARCA_DESCRICAO as string | undefined) ||
    "Assistente do refeitório: veja o cardápio do dia, receba recomendações que respeitam suas restrições e registre o que comeu.",
};

/** Mapa token da marca → custom property do CSS. */
const PROPRIEDADES: Record<keyof TemaMarca, string> = {
  marca: "--marca",
  marcaForte: "--marca-forte",
  marcaSuave: "--marca-suave",
  marcaContraste: "--marca-contraste",
  acento: "--acento",
  acentoTexto: "--acento-texto",
  acentoSuave: "--acento-suave",
};

/**
 * Aplica o tema de uma marca sobre os tokens do documento.
 *
 * Chamar com o tema de um tenant sobrescreve só o que veio; o resto continua no
 * padrão. Chamar sem argumento limpa as sobras — importante quando o usuário
 * troca de unidade dentro da mesma sessão e a unidade nova não tem tema próprio.
 */
export function aplicarTema(tema?: TemaMarca): void {
  const raiz = document.documentElement;
  for (const [chave, propriedade] of Object.entries(PROPRIEDADES)) {
    const valor = tema?.[chave as keyof TemaMarca];
    if (valor) raiz.style.setProperty(propriedade, valor);
    else raiz.style.removeProperty(propriedade);
  }
}
