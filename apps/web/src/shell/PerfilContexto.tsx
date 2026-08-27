import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { getGamificacao, getUsuario, getUsuarioIdSalvo, limparUsuarioIdSalvo, setUsuarioIdSalvo } from "../lib/api";
import type { Gamificacao } from "../types";

/**
 * Quem está usando o app, e quanto já pontuou.
 *
 * Antes, três telas liam `localStorage` por conta própria e a conversa buscava
 * a gamificação de novo a cada render de rota. Com a lateral fixa mostrando
 * nome e pontos em TODAS as telas, isso viraria uma requisição por navegação.
 * Aqui o estado é buscado uma vez, na raiz, e lido por quem precisar.
 *
 * O contexto também é o único lugar que escreve o id do usuário no storage —
 * entrar e sair passam por aqui, então nenhuma tela fica com dado velho.
 */

/** Espelha `PontosPorNivel` em apps/api/internal/domain/gamificacao.go:13.
 *  É duplicação consciente: serve só para desenhar a barra de progresso. Se um
 *  dia o nível virar regra configurável, o valor tem que vir junto da resposta
 *  de /gamificacao — e esta constante sai. */
const PONTOS_POR_NIVEL = 500;

export interface Brinde {
  texto: string;
  nivelUp: boolean;
}

interface Perfil {
  usuarioId: number | null;
  nome: string;
  gami: Gamificacao | null;
  /** Quanto falta para o próximo nível, de 0 a 1. */
  progressoNivel: number;
  /** Aviso temporário de pontos ganhos; some sozinho. */
  brinde: Brinde | null;
  /** Rebusca a pontuação. Com `notificar`, compara com o valor anterior e
   *  dispara o brinde se o usuário ganhou pontos. */
  atualizar: (notificar?: boolean) => void;
  entrar: (id: number) => void;
  sair: () => void;
}

const Contexto = createContext<Perfil | null>(null);

export function PerfilProvider({ children }: { children: ReactNode }) {
  const [usuarioId, setUsuarioId] = useState<number | null>(() => getUsuarioIdSalvo());
  const [nome, setNome] = useState("");
  const [gami, setGami] = useState<Gamificacao | null>(null);
  const [brinde, setBrinde] = useState<Brinde | null>(null);
  const anteriorRef = useRef<Gamificacao | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => () => { if (timerRef.current !== null) window.clearTimeout(timerRef.current); }, []);

  // Nome do usuário. Um 404 aqui significa perfil apagado no backend: em vez de
  // insistir com um id fantasma, esquece o id e volta ao estado anônimo.
  useEffect(() => {
    if (usuarioId === null) { setNome(""); return; }
    let vivo = true;
    getUsuario(usuarioId)
      .then((d) => { if (vivo) setNome(d.usuario.nome); })
      .catch((err: Error) => {
        if (vivo && err.message.includes("(404)")) {
          limparUsuarioIdSalvo();
          setUsuarioId(null);
        }
      });
    return () => { vivo = false; };
  }, [usuarioId]);

  const atualizar = useCallback(
    (notificar = false) => {
      if (usuarioId === null) return;
      getGamificacao(usuarioId)
        .then((d) => {
          const anterior = anteriorRef.current;
          anteriorRef.current = d.gamificacao;
          setGami(d.gamificacao);

          if (!notificar || !anterior || d.gamificacao.pontos <= anterior.pontos) return;

          const delta = d.gamificacao.pontos - anterior.pontos;
          const subiu = d.gamificacao.nivel > anterior.nivel;
          const partes = [`+${delta} pts`];
          const ev = d.eventos?.[0];
          if (ev?.bonus_prato_limpo) partes.push(`prato limpo +${ev.bonus_prato_limpo}`);
          if (ev?.bonus_streak) partes.push(`sequência +${ev.bonus_streak}`);

          setBrinde({
            texto: subiu
              ? `Nível ${d.gamificacao.nivel} · ${partes.join(" · ")}`
              : partes.join(" · "),
            nivelUp: subiu,
          });
          if (timerRef.current !== null) window.clearTimeout(timerRef.current);
          timerRef.current = window.setTimeout(() => setBrinde(null), 6000);
        })
        .catch(() => undefined); // pontuação é acessório: falhar aqui não atrapalha a conversa
    },
    [usuarioId],
  );

  useEffect(() => { atualizar(); }, [atualizar]);

  const entrar = useCallback((id: number) => {
    setUsuarioIdSalvo(id);
    anteriorRef.current = null;
    setGami(null);
    setUsuarioId(id);
  }, []);

  const sair = useCallback(() => {
    limparUsuarioIdSalvo();
    anteriorRef.current = null;
    setGami(null);
    setNome("");
    setUsuarioId(null);
  }, []);

  const valor = useMemo<Perfil>(() => {
    const pontos = gami?.pontos ?? 0;
    return {
      usuarioId,
      nome,
      gami,
      progressoNivel: (pontos % PONTOS_POR_NIVEL) / PONTOS_POR_NIVEL,
      brinde,
      atualizar,
      entrar,
      sair,
    };
  }, [usuarioId, nome, gami, brinde, atualizar, entrar, sair]);

  return <Contexto.Provider value={valor}>{children}</Contexto.Provider>;
}

export function usePerfil(): Perfil {
  const ctx = useContext(Contexto);
  if (!ctx) throw new Error("usePerfil precisa estar dentro de <PerfilProvider>");
  return ctx;
}
