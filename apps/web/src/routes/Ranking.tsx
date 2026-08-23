import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getRanking, getUsuarioIdSalvo } from "../lib/api";
import type { RankingEntry } from "../types";

const MEDALHAS = ["🥇", "🥈", "🥉"];

export default function Ranking() {
  const unidadeId = Number(useParams().unidadeId);
  const [ranking, setRanking] = useState<RankingEntry[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [meuId] = useState<number | null>(() => getUsuarioIdSalvo());

  useEffect(() => {
    setCarregando(true);
    getRanking(unidadeId)
      .then(setRanking)
      .catch(() => setErro("Não foi possível carregar o ranking. O backend está rodando?"))
      .finally(() => setCarregando(false));
  }, [unidadeId]);

  return (
    <div className="app">
      <div className="chat-card selector-card">
        <header className="chat-header">
          <div className="brand">
            <div className="avatar avatar-lia"><span className="avatar-letter">L</span></div>
            <div className="brand-text">
              <h1 className="brand-name">Ranking</h1>
              <span className="status status-on"><span className="status-dot" />top 10 da unidade</span>
            </div>
          </div>
          <div className="header-actions">
            <Link className="btn-ghost" to={`/u/${unidadeId}/chat`}>Voltar ao chat</Link>
            <Link className="btn-ghost" to="/">Início</Link>
          </div>
        </header>

        <main className="messages selector-body">
          {carregando && <p className="msg-p">Carregando ranking…</p>}
          {erro && <p className="msg-p bubble-warning" style={{ padding: 12, borderRadius: 8 }}>{erro}</p>}

          {!carregando && !erro && ranking.length === 0 && (
            <p className="msg-p">
              Ninguém pontuou ainda nesta unidade. Registre suas refeições pelo chat para entrar no ranking! 🍽️
            </p>
          )}

          {ranking.length > 0 && (
            <div className="rank-list">
              {ranking.map((r, i) => (
                <div
                  key={r.usuario_id}
                  className={`rank-row${i < 3 ? " rank-top" : ""}${meuId === r.usuario_id ? " rank-me" : ""}`}
                >
                  <span className="rank-pos">{MEDALHAS[i] ?? `${i + 1}º`}</span>
                  <span className="rank-nome">
                    {r.nome}
                    {meuId === r.usuario_id && <span className="rank-voce"> (você)</span>}
                  </span>
                  <span className="rank-nivel">nível {r.nivel}</span>
                  <span className="rank-pontos">{r.pontos.toLocaleString("pt-BR")} pts</span>
                </div>
              ))}
            </div>
          )}

          {!carregando && !erro && (
            <p className="composer-hint" style={{ textAlign: "left", margin: "4px 4px 0" }}>
              Pontos são ganhos ao registrar consumo no chat — prato limpo e sequência diária valem bônus.
            </p>
          )}
        </main>
      </div>
    </div>
  );
}
