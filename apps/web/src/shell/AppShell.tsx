import { useCallback, useEffect, useState, type ReactNode } from "react";
import { useLocation } from "react-router-dom";
import Icone from "../ui/Icone";
import Lateral, { type Area } from "./Lateral";

interface Props {
  /** Define a navegação da lateral. */
  area?: Area;
  /** Unidade em foco; sem ela, a lateral esconde o que é por unidade. */
  unidadeId?: number | null;
  /** Título da barra superior — no celular é a única pista de onde a pessoa está. */
  titulo: string;
  /** Ações à direita da barra superior. */
  acoes?: ReactNode;
  /** "conversa" entrega a altura toda ao filho; "pagina" rola normalmente. */
  variante?: "conversa" | "pagina";
  aoNovaConversa?: () => void;
  novaConversaOcupada?: boolean;
  children: ReactNode;
}

/**
 * A moldura de todas as telas: lateral fixa no desktop, gaveta no celular.
 *
 * Um shell só, para as duas áreas (cliente e gestor), porque a alternativa —
 * cada tela desenhando o próprio cabeçalho — é exatamente o que existia antes:
 * seis rotas repetindo o mesmo `<header>` com listas de links diferentes, sem
 * jeito de saber onde você está.
 */
export default function AppShell({
  area = "cliente",
  unidadeId = null,
  titulo,
  acoes,
  variante = "pagina",
  aoNovaConversa,
  novaConversaOcupada,
  children,
}: Props) {
  const [menuAberto, setMenuAberto] = useState(false);
  const { pathname } = useLocation();

  const fechar = useCallback(() => setMenuAberto(false), []);

  // Navegou: a gaveta não pode ficar aberta por cima da tela nova.
  useEffect(() => { setMenuAberto(false); }, [pathname]);

  // Esc fecha — é o que qualquer sobreposição precisa oferecer a quem usa teclado.
  useEffect(() => {
    if (!menuAberto) return;
    const aoTeclar = (e: KeyboardEvent) => { if (e.key === "Escape") setMenuAberto(false); };
    window.addEventListener("keydown", aoTeclar);
    return () => window.removeEventListener("keydown", aoTeclar);
  }, [menuAberto]);

  return (
    <div className="shell">
      <Lateral
        area={area}
        unidadeId={unidadeId}
        aberta={menuAberto}
        aoFechar={fechar}
        aoNovaConversa={aoNovaConversa}
        novaConversaOcupada={novaConversaOcupada}
      />

      {menuAberto && <button className="veu" onClick={fechar} aria-label="Fechar menu" tabIndex={-1} />}

      <div className="principal">
        <header className={`barra-topo${variante === "pagina" ? " barra-topo--com-linha" : ""}`}>
          <button
            className="btn-icone abre-menu"
            onClick={() => setMenuAberto(true)}
            aria-label="Abrir menu"
            aria-expanded={menuAberto}
            aria-controls="menu-lateral"
          >
            <Icone nome="menu" />
          </button>
          <span className="barra-topo__titulo">{titulo}</span>
          {acoes && <div className="barra-topo__acoes">{acoes}</div>}
        </header>

        {children}
      </div>
    </div>
  );
}
