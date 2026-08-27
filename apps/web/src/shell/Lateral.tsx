import { Link, NavLink, useLocation } from "react-router-dom";
import { marca } from "../brand";
import Icone, { type NomeIcone } from "../ui/Icone";
import { getUnidadeSalva } from "../lib/api";
import { usePerfil } from "./PerfilContexto";
import { useUnidade } from "./useUnidade";
import { useTema } from "./useTema";
import type { Preferencia } from "./tema";

export type Area = "cliente" | "gestor";

interface Props {
  area: Area;
  unidadeId: number | null;
  aberta: boolean;
  aoFechar: () => void;
  /** Só a conversa oferece isto; nas demais telas o botão não aparece. */
  aoNovaConversa?: () => void;
  novaConversaOcupada?: boolean;
}

function ItemNav({ para, icone, children, extra }: {
  para: string;
  icone: NomeIcone;
  children: string;
  extra?: string;
}) {
  return (
    <NavLink to={para} className={({ isActive }) => `nav-item${isActive ? " ativo" : ""}`} end>
      <Icone nome={icone} className="nav-item__icone" />
      <span className="nav-item__rotulo">{children}</span>
      {extra && <span className="nav-item__extra">{extra}</span>}
    </NavLink>
  );
}

const TEMAS: { valor: Preferencia; icone: NomeIcone; titulo: string }[] = [
  { valor: "claro", icone: "sol", titulo: "Tema claro" },
  { valor: "escuro", icone: "lua", titulo: "Tema escuro" },
  { valor: "sistema", icone: "sistema", titulo: "Seguir o sistema" },
];

function iniciais(nome: string): string {
  const partes = nome.trim().split(/\s+/).filter(Boolean);
  if (partes.length === 0) return "?";
  if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
  return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
}

export default function Lateral({ area, unidadeId, aberta, aoFechar, aoNovaConversa, novaConversaOcupada }: Props) {
  const { usuarioId, nome, gami, progressoNivel } = usePerfil();
  // Telas sem unidade na URL (o perfil, por exemplo) ainda precisam do caminho
  // de volta para a conversa — senão a navegação some justo onde a pessoa foi
  // parar sozinha. A última unidade usada é essa memória.
  const unidadeEfetiva = unidadeId ?? getUnidadeSalva();
  const unidade = useUnidade(unidadeEfetiva);
  const [tema, escolherTema] = useTema();
  const { pathname } = useLocation();

  const noChat = pathname.includes("/chat");

  return (
    <aside
      className={`lateral${aberta ? " aberta" : ""}`}
      id="menu-lateral"
      /* Fechada no celular, a gaveta some com `visibility: hidden` (ver
         shell.css) — o que também a tira da ordem de tabulação. Sem isso o
         teclado navegaria para dentro de um menu invisível. */
    >
      <div className="lateral__topo">
        <Link to="/" className="marca" onClick={aoFechar}>
          <span className="marca__selo" aria-hidden="true">{marca.monograma}</span>
          <span className="marca__texto">
            <span className="marca__nome">{area === "gestor" ? "Gestão" : marca.assistente}</span>
            <span className="marca__linha">{marca.produto}</span>
          </span>
        </Link>
        <button className="btn-icone abre-menu" style={{ marginLeft: "auto" }} onClick={aoFechar} aria-label="Fechar menu">
          <Icone nome="fechar" />
        </button>
      </div>

      <div className="lateral__corpo">
        {area === "cliente" ? (
          <>
            {aoNovaConversa && noChat && (
              <button className="nav-acao" onClick={aoNovaConversa} disabled={novaConversaOcupada}>
                <Icone nome="nova" className="nav-acao__icone" />
                Nova conversa
              </button>
            )}

            {unidadeEfetiva != null && (
              <Link to="/unidades" className="unidade-atual" onClick={aoFechar}>
                <Icone nome="unidade" />
                <span className="unidade-atual__texto">
                  <span className="unidade-atual__rotulo">Unidade</span>
                  <span className="unidade-atual__nome">{unidade?.nome ?? "—"}</span>
                </span>
                <Icone nome="baixo" tam={16} />
              </Link>
            )}

            <nav className="nav-grupo">
              {unidadeEfetiva != null && (
                <>
                  <ItemNav para={`/u/${unidadeEfetiva}/chat`} icone="conversa">Conversa</ItemNav>
                  <ItemNav para={`/u/${unidadeEfetiva}/ranking`} icone="ranking">Ranking</ItemNav>
                </>
              )}
              <ItemNav para="/perfil" icone="perfil">Meu perfil</ItemNav>
            </nav>
          </>
        ) : (
          <>
            <nav className="nav-grupo">
              <span className="nav-titulo">Rede</span>
              <ItemNav para="/admin" icone="grafico">Visão geral</ItemNav>
              <ItemNav para="/admin/unidades" icone="unidade">Unidades</ItemNav>
              <ItemNav para="/admin/usuarios" icone="usuarios">Usuários</ItemNav>
            </nav>

            {unidadeId != null && (
              <nav className="nav-grupo">
                <span className="nav-titulo">{unidade?.nome ?? "Unidade"}</span>
                <ItemNav para={`/admin/u/${unidadeId}/cardapio`} icone="calendario">Cardápio da semana</ItemNav>
                <ItemNav para={`/admin/u/${unidadeId}/alimentos`} icone="prato">Alimentos</ItemNav>
                <ItemNav para={`/admin/u/${unidadeId}/desperdicio`} icone="grafico">Desperdício</ItemNav>
              </nav>
            )}
          </>
        )}
      </div>

      <div className="lateral__base">
        {area === "cliente" ? (
          <>
            <Link to="/perfil" className="usuario-bloco" onClick={aoFechar}>
              <span className="iniciais" aria-hidden="true">
                {usuarioId ? iniciais(nome) : <Icone nome="perfil" tam={16} />}
              </span>
              <span className="usuario-bloco__texto">
                <span className="usuario-bloco__nome">{usuarioId ? nome || "Meu perfil" : "Criar meu perfil"}</span>
                <span className="usuario-bloco__meta">
                  {gami
                    ? `${gami.pontos.toLocaleString("pt-BR")} pts · nível ${gami.nivel}`
                    : "para recomendações sob medida"}
                </span>
              </span>
            </Link>
            {gami && (
              <div
                className="progresso"
                role="progressbar"
                aria-label={`Progresso para o nível ${gami.nivel + 1}`}
                aria-valuenow={Math.round(progressoNivel * 100)}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div className="progresso__barra" style={{ width: `${Math.round(progressoNivel * 100)}%` }} />
              </div>
            )}
          </>
        ) : (
          <Link to="/" className="nav-item" onClick={aoFechar}>
            <Icone nome="esquerda" className="nav-item__icone" />
            <span className="nav-item__rotulo">Voltar à conversa</span>
          </Link>
        )}

        <div className="tema-troca" role="group" aria-label="Tema da interface">
          {TEMAS.map((t) => (
            <button
              key={t.valor}
              className={`tema-troca__op${tema === t.valor ? " ativo" : ""}`}
              onClick={() => escolherTema(t.valor)}
              aria-label={t.titulo}
              aria-pressed={tema === t.valor}
              title={t.titulo}
            >
              <Icone nome={t.icone} tam={16} />
            </button>
          ))}
        </div>

        {area === "cliente" && (
          <Link to="/admin" className="nav-item" onClick={aoFechar}>
            <Icone nome="gestor" className="nav-item__icone" />
            <span className="nav-item__rotulo">Área do gestor</span>
          </Link>
        )}
      </div>
    </aside>
  );
}
