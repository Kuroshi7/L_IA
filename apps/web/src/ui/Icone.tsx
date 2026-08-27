/**
 * Conjunto de ícones do produto — SVG inline, traço de 1.6, nada de emoji.
 *
 * O front antigo usava emoji como ícone (➤ ★ × 🏆 ⭐ 🙂). Emoji muda de desenho
 * a cada sistema operacional: o mesmo botão vira outra coisa entre um Android e
 * um iPhone, e nenhum deles combina com o resto da tela. Além disso o leitor de
 * tela lê "estrela branca de cinco pontas" onde deveria ler "proteína do dia".
 *
 * Aqui o traço é um só, a cor é sempre `currentColor` (herda do contexto, então
 * funciona nos dois temas de graça) e todo botão de ícone carrega `aria-label`.
 *
 * Emoji continua permitido num lugar: dentro do texto que a Lia escreve. Ali é
 * conteúdo dela, não interface nossa.
 */

export type NomeIcone =
  | "menu" | "fechar" | "nova" | "enviar" | "copiar" | "confere"
  | "baixo" | "esquerda" | "direita" | "busca"
  | "conversa" | "unidade" | "ranking" | "perfil" | "gestor" | "sair"
  | "sol" | "lua" | "sistema"
  | "estrela" | "pontos" | "info" | "remover" | "calendario" | "prato"
  | "usuarios" | "grafico" | "folha" | "veto" | "alvo";

const TRACOS: Record<NomeIcone, string> = {
  menu: "M3.5 7h17M3.5 12h17M3.5 17h17",
  fechar: "M6.5 6.5l11 11M17.5 6.5l-11 11",
  nova: "M4 20h4L18.6 9.4a2.05 2.05 0 0 0-2.9-2.9L5 17.1V20z M14.5 8l2 2",
  enviar: "M12 19.5v-15M5.5 11L12 4.5 18.5 11",
  copiar: "M9 8.5h9.5V20H9zM5.5 15.5V4h11",
  confere: "M5 12.5l4.5 4.5L19 7",
  baixo: "M6.5 9.5l5.5 5.5 5.5-5.5",
  esquerda: "M14.5 5.5L8 12l6.5 6.5",
  direita: "M9.5 5.5L16 12l-6.5 6.5",
  busca: "M15.5 15.5L20 20M4 10.5a6.5 6.5 0 1 0 13 0 6.5 6.5 0 0 0-13 0z",
  conversa: "M20.5 14.5a3 3 0 0 1-3 3H8.8L4 21V6.5a3 3 0 0 1 3-3h10.5a3 3 0 0 1 3 3z",
  unidade: "M3.5 20V9.2L12 3.5l8.5 5.7V20M3.5 20h17M9.2 20v-5.6h5.6V20",
  // Pódio: três degraus e a linha do chão. Substitui o troféu-emoji.
  ranking: "M3 20.5h18M5.5 20.5v-4.2h4v4.2M10 20.5V8.5h4v12M14.5 20.5v-6.6h4v6.6",
  perfil: "M4.8 20a7.2 7.2 0 0 1 14.4 0M8.4 8.2a3.6 3.6 0 1 0 7.2 0 3.6 3.6 0 0 0-7.2 0z",
  gestor: "M4 7.5h6.5M15 7.5h5M4 12h9M17.5 12h2.5M4 16.5h3M11.5 16.5h8.5M12.7 5.7v3.6M15.2 10.2v3.6M9.2 14.7v3.6",
  sair: "M14.5 16.5l4-4.5-4-4.5M18.5 12H9M12.5 4.5H6.5a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h6",
  sol: "M12 6.2a5.8 5.8 0 1 0 0 11.6 5.8 5.8 0 0 0 0-11.6zM12 2.5v1.6M12 19.9v1.6M4.8 4.8l1.2 1.2M18 18l1.2 1.2M2.5 12h1.6M19.9 12h1.6M4.8 19.2L6 18M18 6l1.2-1.2",
  lua: "M20.2 14.6A8.6 8.6 0 0 1 9.4 3.8a8.6 8.6 0 1 0 10.8 10.8z",
  sistema: "M3.5 5.5h17v10.5h-17zM9 20h6M12 16v4",
  estrela: "M12 3.8l2.5 5.4 5.7.7-4.2 4 1.1 5.8L12 16.9 6.9 19.7 8 13.9l-4.2-4 5.7-.7z",
  // Faísca — pontos ganhos. Não é a estrela do "proteína do dia": coisas
  // diferentes não podem usar o mesmo desenho.
  pontos: "M12 3l1.9 5.4 5.4 1.9-5.4 1.9L12 17.6l-1.9-5.4L4.7 10.3l5.4-1.9zM18.5 16.5l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z",
  info: "M12 3.8a8.2 8.2 0 1 0 0 16.4 8.2 8.2 0 0 0 0-16.4zM12 11v5.2M12 7.9v.1",
  remover: "M7 7l10 10M17 7L7 17",
  calendario: "M4 6.5a1.5 1.5 0 0 1 1.5-1.5h13A1.5 1.5 0 0 1 20 6.5v13a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 19.5zM8 3v4M16 3v4M4 10h16",
  prato: "M3.2 11.2h17.6a8.8 8.8 0 0 1-17.6 0zM8.6 7.6c0-1.3.8-2.1 1.8-2.6M13.4 7.3c.3-1 1.1-1.7 2-2",
  usuarios: "M2.8 19.5a5.6 5.6 0 0 1 11.2 0M5.6 8.6a2.8 2.8 0 1 0 5.6 0 2.8 2.8 0 0 0-5.6 0zM15.5 19.5a5.5 5.5 0 0 0-2.4-4.5M14.8 8.9a2.8 2.8 0 0 0 .8-5.4",
  grafico: "M4 3.5v17h16.5M7.5 16.5l3.8-4.4 3.2 2.6 4.8-6.2",
  folha: "M4.5 19.5C3 14 6 5.5 19.5 4.5c1 10.5-5 14.5-11 14.2M8.5 15.5c2-3.5 4.8-5.8 8-7",
  veto: "M4.6 4.6a10.5 10.5 0 1 0 14.8 14.8A10.5 10.5 0 0 0 4.6 4.6zM5.4 5.4l13.2 13.2",
  alvo: "M12 3.6a8.4 8.4 0 1 0 0 16.8 8.4 8.4 0 0 0 0-16.8zM12 8.2a3.8 3.8 0 1 0 0 7.6 3.8 3.8 0 0 0 0-7.6zM12 11.4v1.2",
};

interface Props {
  nome: NomeIcone;
  /** Lado do quadrado, em px. 20 é o tamanho de UI; 16 para texto miúdo. */
  tam?: number;
  className?: string;
}

export default function Icone({ nome, tam = 20, className }: Props) {
  return (
    <svg
      className={className}
      width={tam}
      height={tam}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      /* Decorativo por definição: quem precisa de nome é o botão em volta,
         via aria-label. Anunciar o ícone também seria ler tudo duas vezes. */
      aria-hidden="true"
      focusable="false"
    >
      <path d={TRACOS[nome]} />
    </svg>
  );
}
