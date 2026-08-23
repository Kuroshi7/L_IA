import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { adminGetDesperdicio } from "../../lib/api";
import { addDaysISO, fmtISO, rotuloCurto } from "../../lib/datas";
import type { ClassificacaoDesperdicio, DesperdicioRelatorio } from "../../types";

const PERIODOS = [7, 14, 30] as const;

const CLASSIFICACAO_LABEL: Record<ClassificacaoDesperdicio, string> = {
  otimo: "Ótimo",
  bom: "Bom",
  atencao: "Atenção",
  critico: "Crítico",
};

const num = (v: number, casas = 0) =>
  v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });

export default function DesperdicioDashboard() {
  const unidadeId = Number(useParams().unidadeId);
  const [periodo, setPeriodo] = useState<(typeof PERIODOS)[number]>(14);
  const [rel, setRel] = useState<DesperdicioRelatorio | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    const hoje = fmtISO(new Date());
    const de = addDaysISO(hoje, -(periodo - 1));
    setCarregando(true);
    setErro(null);
    adminGetDesperdicio(unidadeId, de, hoje)
      .then(setRel)
      .catch((e: Error) => setErro(e.message))
      .finally(() => setCarregando(false));
  }, [unidadeId, periodo]);

  const dias = rel?.dias ?? [];
  const top = rel?.top_desperdicados ?? [];
  const maxResto = Math.max(...dias.map((d) => d.resto_g), 0);
  const semRegistros = !carregando && !erro && rel !== null && rel.refeicoes === 0;
  // Com muitos dias, rotular todos os eixos vira ruído — mostra 1 a cada N.
  const labelStep = Math.max(1, Math.ceil(dias.length / 10));

  return (
    <div className="app">
      <div className="chat-card admin-card">
        <header className="chat-header">
          <div className="brand">
            <div className="avatar avatar-lia"><span className="avatar-letter">L</span></div>
            <div className="brand-text">
              <h1 className="brand-name">Desperdício</h1>
              <span className="status status-on">
                <span className="status-dot" />
                {rel ? `${rotuloCurto(rel.de)} a ${rotuloCurto(rel.ate)}` : "resto-ingesta da unidade"}
              </span>
            </div>
          </div>
          <div className="header-actions">
            <Link className="btn-ghost" to={`/admin/u/${unidadeId}/cardapio`}>Cardápio</Link>
            <Link className="btn-ghost" to={`/admin/u/${unidadeId}/alimentos`}>Alimentos</Link>
            <Link className="btn-ghost" to="/admin">Admin</Link>
          </div>
        </header>

        <main className="messages admin-body">
          {erro && <p className="msg-p bubble-warning" style={{ padding: 12, borderRadius: 8 }}>{erro}</p>}

          <div className="semana-toolbar">
            <span className="suggestions-title" style={{ margin: 0 }}>Período</span>
            {PERIODOS.map((p) => (
              <button
                key={p}
                className={`chip${periodo === p ? " chip-on" : ""}`}
                onClick={() => setPeriodo(p)}
              >
                {p} dias
              </button>
            ))}
          </div>

          {carregando && <p className="msg-p">Carregando relatório…</p>}

          {semRegistros && (
            <div className="form-card">
              <p className="msg-p">
                <strong>Sem registros no período</strong> — o desperdício aparece quando os clientes
                registram consumo/sobras no chat. Incentive os registros para acompanhar o resto-ingesta. 🍽️
              </p>
            </div>
          )}

          {!carregando && rel && !semRegistros && (
            <>
              <div className="stat-tiles">
                <div className={`stat-tile tile-${rel.classificacao}`}>
                  <span className="stat-label">Índice resto-ingesta</span>
                  <span className="stat-value">{num(rel.indice_resto_perc, 1)}%</span>
                  <span className="stat-hint">{CLASSIFICACAO_LABEL[rel.classificacao]}</span>
                </div>
                <div className="stat-tile">
                  <span className="stat-label">Refeições registradas</span>
                  <span className="stat-value">{num(rel.refeicoes)}</span>
                  <span className="stat-hint">no período</span>
                </div>
                <div className="stat-tile">
                  <span className="stat-label">Resto per capita</span>
                  <span className="stat-value">{num(rel.resto_per_capita_g)} g</span>
                  <span className="stat-hint">por refeição</span>
                </div>
                <div className="stat-tile">
                  <span className="stat-label">Resto total</span>
                  <span className="stat-value">{num(rel.resto_kcal)} kcal</span>
                  <span className="stat-hint">{num(rel.resto_g)} g desperdiçados</span>
                </div>
              </div>

              {dias.length > 0 && maxResto > 0 && (
                <div className="form-card">
                  <h3 className="form-section">Resto por dia (g)</h3>
                  <div className="chart-bars">
                    {dias.map((d, i) => (
                      <div
                        className="chart-col"
                        key={d.data}
                        title={`${rotuloCurto(d.data)} · ${num(d.resto_g)} g de resto · ${d.refeicoes} refeição(ões)`}
                      >
                        <div className="chart-track">
                          {d.resto_g === maxResto && (
                            <span className="chart-value">{num(d.resto_g)}</span>
                          )}
                          <div
                            className="chart-bar"
                            style={{ height: `${Math.max((d.resto_g / maxResto) * 85, d.resto_g > 0 ? 2 : 0)}%` }}
                          />
                        </div>
                        <span className="chart-label">{i % labelStep === 0 ? rotuloCurto(d.data) : " "}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {top.length > 0 && (
                <>
                  <h3 className="form-section">Top alimentos desperdiçados</h3>
                  <div className="table-wrap">
                    <table className="admin-table">
                      <thead>
                        <tr>
                          <th>Alimento</th>
                          <th className="celula-num">Ocorrências</th>
                          <th className="celula-num">Resto (g)</th>
                          <th className="celula-num">Resto (kcal)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {top.map((t) => (
                          <tr key={t.alimento}>
                            <td>{t.alimento}</td>
                            <td className="celula-num">{num(t.ocorrencias)}</td>
                            <td className="celula-num">{num(t.resto_g)}</td>
                            <td className="celula-num">{num(t.resto_kcal)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </>
          )}

          {!carregando && rel && (
            <p className="composer-hint" style={{ textAlign: "left", margin: "0 4px" }}>
              Índice de resto-ingesta = resto ÷ total servido. Referência para UANs: até 10% é considerado bom;
              acima disso indica porcionamento ou aceitação do cardápio a revisar.
            </p>
          )}
        </main>
      </div>
    </div>
  );
}
