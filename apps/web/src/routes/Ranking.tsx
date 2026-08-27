import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getRanking } from "../lib/api";
import AppShell from "../shell/AppShell";
import { usePerfil } from "../shell/PerfilContexto";
import { Aviso, Cabecalho, Pagina, Silhueta, Vazio } from "../ui/Pagina";
import type { RankingEntry } from "../types";

export default function Ranking() {
  const unidadeId = Number(useParams().unidadeId);
  const { usuarioId } = usePerfil();
  const [ranking, setRanking] = useState<RankingEntry[] | null>(null);
  const [falhou, setFalhou] = useState(false);

  const carregar = useCallback(() => {
    setFalhou(false);
    setRanking(null);
    getRanking(unidadeId)
      .then(setRanking)
      .catch((err) => { console.error("falha ao carregar ranking", err); setFalhou(true); });
  }, [unidadeId]);

  useEffect(carregar, [carregar]);

  return (
    <AppShell titulo="Ranking" unidadeId={unidadeId}>
      <Pagina estreita>
        <Cabecalho
          titulo="Ranking da unidade"
          apoio="Os dez primeiros em pontos. Você pontua ao registrar suas refeições na conversa — comer o que serviu no prato e manter a sequência de dias valem bônus."
        />

        {falhou && (
          <Aviso
            tom="erro"
            titulo="Não consegui carregar o ranking"
            acao={<button className="btn btn--contorno btn--mini" onClick={carregar}>Tentar de novo</button>}
          >
            Verifique sua conexão e tente de novo.
          </Aviso>
        )}

        {!ranking && !falhou && <Silhueta linhas={5} altura={52} />}

        {ranking?.length === 0 && (
          <Vazio
            titulo="Ninguém pontuou ainda"
            acao={<Link className="btn btn--primario" to={`/u/${unidadeId}/chat`}>Registrar minha refeição</Link>}
          >
            Seja o primeiro: conte na conversa o que você comeu e quanto sobrou no prato.
          </Vazio>
        )}

        {ranking && ranking.length > 0 && (
          <ol className="rank">
            {ranking.map((r, i) => (
              <li
                key={r.usuario_id}
                className={`rank__linha${i < 3 ? " rank__linha--podio" : ""}${usuarioId === r.usuario_id ? " rank__linha--eu" : ""}`}
              >
                <span className="rank__pos">{i + 1}</span>
                <span className="rank__nome">
                  {r.nome}
                  {usuarioId === r.usuario_id && <span className="rank__eu"> · você</span>}
                </span>
                <span className="rank__nivel">nível {r.nivel}</span>
                <span className="rank__pontos">{r.pontos.toLocaleString("pt-BR")} pts</span>
              </li>
            ))}
          </ol>
        )}
      </Pagina>
    </AppShell>
  );
}
