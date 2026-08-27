import type { ReactNode } from "react";
import Icone, { type NomeIcone } from "./Icone";

/** Corpo rolável de uma tela que não é a conversa. */
export function Pagina({ children, estreita }: { children: ReactNode; estreita?: boolean }) {
  return (
    <div className="pagina">
      <div className={`pagina__interno${estreita ? " pagina__interno--estreito" : ""}`}>{children}</div>
    </div>
  );
}

/** Título em serifa + uma linha dizendo o que a tela resolve. A linha de apoio
 *  não é enfeite: é onde o gestor descobre para que serve a tela sem treino. */
export function Cabecalho({ titulo, apoio, acoes }: { titulo: string; apoio?: string; acoes?: ReactNode }) {
  return (
    <header className="cabecalho">
      <div className="cabecalho__texto">
        <h1 className="cabecalho__titulo">{titulo}</h1>
        {apoio && <p className="cabecalho__apoio">{apoio}</p>}
      </div>
      {acoes && <div className="cabecalho__acoes">{acoes}</div>}
    </header>
  );
}

export type TomAviso = "neutro" | "erro" | "atencao" | "ok";

const ICONE_DO_TOM: Record<TomAviso, NomeIcone> = {
  neutro: "info",
  erro: "info",
  atencao: "info",
  ok: "confere",
};

/**
 * Aviso em linguagem de gente.
 *
 * O front antigo mostrava "O backend está rodando?" e "Rode o seed do backend"
 * para o cliente final, além de despejar o corpo cru da resposta HTTP. Texto de
 * desenvolvedor na tela do usuário destrói a percepção de produto pronto — e não
 * ajuda quem lê, porque ele não pode fazer nada com essa informação. Aqui o
 * usuário vê o que aconteceu e o que fazer; o detalhe técnico vai para o console.
 */
export function Aviso({ tom = "neutro", titulo, children, acao }: {
  tom?: TomAviso;
  titulo?: string;
  children?: ReactNode;
  acao?: ReactNode;
}) {
  return (
    <div className={`aviso${tom === "neutro" ? "" : ` aviso--${tom}`}`} role={tom === "erro" ? "alert" : undefined}>
      <Icone nome={ICONE_DO_TOM[tom]} className="aviso__icone" />
      <div className="aviso__corpo">
        {titulo && <strong>{titulo}</strong>}
        {children}
      </div>
      {acao && <div className="aviso__acao">{acao}</div>}
    </div>
  );
}

/** Estado vazio com saída: nunca só "nenhum registro". */
export function Vazio({ titulo, children, acao }: { titulo: string; children?: ReactNode; acao?: ReactNode }) {
  return (
    <div className="vazio">
      <p className="vazio__titulo">{titulo}</p>
      {children && <p className="vazio__texto">{children}</p>}
      {acao}
    </div>
  );
}

/** Silhueta de carregamento. Repete a forma do conteúdo que vai chegar, para a
 *  tela não pular de "vazia" para "cheia". */
export function Silhueta({ linhas = 3, altura = 64 }: { linhas?: number; altura?: number }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }} aria-hidden="true">
      {Array.from({ length: linhas }, (_, i) => (
        <div key={i} className="esqueleto" style={{ height: altura }} />
      ))}
      <span className="vis-oculto">Carregando…</span>
    </div>
  );
}
