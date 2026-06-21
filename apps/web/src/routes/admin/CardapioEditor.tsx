import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  adminCopiarSemana,
  adminGetCardapioSemana,
  adminListarAlimentos,
  adminSetCardapioItens,
} from "../../lib/api";
import { addDaysISO, mondayISO, rotuloCurto } from "../../lib/datas";
import type { Alimento, CardapioDia, CardapioItemInput, CardapioSemana } from "../../types";

function itensDe(dia: CardapioDia): CardapioItemInput[] {
  return dia.pratos.map((p) => ({ alimento_id: p.id, is_proteina_do_dia: p.is_proteina_do_dia }));
}

export default function CardapioEditor() {
  const unidadeId = Number(useParams().unidadeId);
  const [inicio, setInicio] = useState(() => mondayISO(new Date()));
  const [semana, setSemana] = useState<CardapioSemana | null>(null);
  const [catalogo, setCatalogo] = useState<Alimento[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);

  const carregar = useCallback(() => {
    setCarregando(true);
    setErro(null);
    Promise.all([adminGetCardapioSemana(unidadeId, inicio), adminListarAlimentos(unidadeId)])
      .then(([sem, cat]) => {
        setSemana(sem);
        setCatalogo(cat);
      })
      .catch((e: Error) => setErro(e.message))
      .finally(() => setCarregando(false));
  }, [unidadeId, inicio]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  function salvarDia(diaIdx: number, itens: CardapioItemInput[]) {
    if (!semana) return;
    const dia = semana.dias[diaIdx];
    setSalvando(true);
    setErro(null);
    adminSetCardapioItens(unidadeId, dia.data, itens)
      .then((atualizado) => {
        setSemana((prev) => {
          if (!prev) return prev;
          const dias = [...prev.dias];
          dias[diaIdx] = atualizado;
          return { ...prev, dias };
        });
      })
      .catch((e: Error) => setErro(e.message))
      .finally(() => setSalvando(false));
  }

  function adicionar(diaIdx: number, alimentoId: number) {
    if (!alimentoId || !semana) return;
    const dia = semana.dias[diaIdx];
    salvarDia(diaIdx, [...itensDe(dia), { alimento_id: alimentoId, is_proteina_do_dia: false }]);
  }

  function remover(diaIdx: number, alimentoId: number) {
    if (!semana) return;
    const dia = semana.dias[diaIdx];
    salvarDia(diaIdx, itensDe(dia).filter((i) => i.alimento_id !== alimentoId));
  }

  function alternarProteina(diaIdx: number, alimentoId: number) {
    if (!semana) return;
    const dia = semana.dias[diaIdx];
    const atual = dia.pratos.find((p) => p.id === alimentoId)?.is_proteina_do_dia ?? false;
    salvarDia(
      diaIdx,
      dia.pratos.map((p) => ({ alimento_id: p.id, is_proteina_do_dia: p.id === alimentoId ? !atual : false })),
    );
  }

  function copiarProximaSemana() {
    const destino = addDaysISO(inicio, 7);
    setSalvando(true);
    adminCopiarSemana(unidadeId, inicio, destino)
      .then(() => setInicio(destino))
      .catch((e: Error) => setErro(e.message))
      .finally(() => setSalvando(false));
  }

  return (
    <div className="app">
      <div className="chat-card admin-card">
        <header className="chat-header">
          <div className="brand">
            <div className="avatar avatar-lia"><span className="avatar-letter">L</span></div>
            <div className="brand-text">
              <h1 className="brand-name">Cardápio da semana</h1>
              <span className="status status-on">
                <span className="status-dot" />
                {salvando ? "salvando…" : `semana de ${rotuloCurto(inicio)}`}
              </span>
            </div>
          </div>
          <div className="header-actions">
            <Link className="btn-ghost" to={`/admin/u/${unidadeId}/alimentos`}>Alimentos</Link>
            <Link className="btn-ghost" to="/admin">Admin</Link>
          </div>
        </header>

        <main className="messages admin-body">
          <div className="semana-toolbar">
            <button className="btn-ghost" onClick={() => setInicio(addDaysISO(inicio, -7))}>← Semana anterior</button>
            <button className="btn-ghost" onClick={() => setInicio(mondayISO(new Date()))}>Semana atual</button>
            <button className="btn-ghost" onClick={() => setInicio(addDaysISO(inicio, 7))}>Próxima semana →</button>
            <span className="toolbar-spacer" />
            <button className="btn-primary" disabled={salvando} onClick={copiarProximaSemana}>
              Copiar p/ próxima semana
            </button>
          </div>

          {erro && <p className="msg-p bubble-warning" style={{ padding: 12, borderRadius: 8 }}>{erro}</p>}
          {carregando && <p className="msg-p">Carregando semana…</p>}

          {semana && (
            <div className="semana-grid">
              {semana.dias.map((dia, idx) => {
                const presentes = new Set(dia.pratos.map((p) => p.id));
                const disponiveis = catalogo.filter((a) => a.ativo && !presentes.has(a.id));
                return (
                  <div className="dia-col" key={dia.data}>
                    <div className="dia-head">
                      <strong>{dia.dia_semana}</strong>
                      <span className="dia-data">{rotuloCurto(dia.data)}</span>
                    </div>

                    <div className="dia-itens">
                      {dia.pratos.length === 0 && <p className="dia-vazio">Sem itens</p>}
                      {dia.pratos.map((p) => (
                        <div className={`item-row${p.ativo ? "" : " item-inativo"}`} key={p.id}>
                          <button
                            className={`star${p.is_proteina_do_dia ? " star-on" : ""}`}
                            title="Proteína do dia (1 por dia)"
                            onClick={() => alternarProteina(idx, p.id)}
                          >
                            ★
                          </button>
                          <span className="item-nome">
                            {p.nome}
                            {!p.ativo && <em className="item-tag"> inativo</em>}
                          </span>
                          <button className="item-remove" title="Remover" onClick={() => remover(idx, p.id)}>×</button>
                        </div>
                      ))}
                    </div>

                    <select
                      className="select-input dia-add"
                      value=""
                      disabled={salvando || disponiveis.length === 0}
                      onChange={(e) => adicionar(idx, Number(e.target.value))}
                    >
                      <option value="">
                        {disponiveis.length === 0 ? "— catálogo vazio —" : "+ adicionar alimento"}
                      </option>
                      {disponiveis.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.categoria ? `${a.categoria} · ` : ""}{a.nome}
                        </option>
                      ))}
                    </select>
                  </div>
                );
              })}
            </div>
          )}

          {semana && catalogo.length === 0 && (
            <p className="msg-p">
              Catálogo vazio. Cadastre alimentos em{" "}
              <Link to={`/admin/u/${unidadeId}/alimentos`}>Alimentos</Link> antes de montar o cardápio.
            </p>
          )}
        </main>
      </div>
    </div>
  );
}
