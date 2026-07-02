import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { adminListarUnidades, adminListarUsuarios } from "../../lib/api";
import type { AdminUsuario, Unidade } from "../../types";

const csv = (a: string[] | null | undefined) => {
  const arr = a ?? [];
  return arr.length ? arr.join(", ") : "—";
};

export default function UsuariosAdmin() {
  const [usuarios, setUsuarios] = useState<AdminUsuario[]>([]);
  const [unidades, setUnidades] = useState<Unidade[]>([]);
  const [filtroUnidade, setFiltroUnidade] = useState("");
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    adminListarUnidades().then(setUnidades).catch(() => setUnidades([]));
  }, []);

  useEffect(() => {
    setCarregando(true);
    setErro(null);
    adminListarUsuarios(filtroUnidade ? Number(filtroUnidade) : undefined)
      .then(setUsuarios)
      .catch((e: Error) => setErro(e.message))
      .finally(() => setCarregando(false));
  }, [filtroUnidade]);

  return (
    <div className="app">
      <div className="chat-card admin-card">
        <header className="chat-header">
          <div className="brand">
            <div className="avatar avatar-lia"><span className="avatar-letter">L</span></div>
            <div className="brand-text">
              <h1 className="brand-name">Usuários</h1>
              <span className="status status-on"><span className="status-dot" />perfis e gamificação</span>
            </div>
          </div>
          <div className="header-actions">
            <Link className="btn-ghost" to="/admin/unidades">Unidades</Link>
            <Link className="btn-ghost" to="/admin">Admin</Link>
          </div>
        </header>

        <main className="messages admin-body">
          {erro && <p className="msg-p bubble-warning" style={{ padding: 12, borderRadius: 8 }}>{erro}</p>}

          <div className="semana-toolbar">
            <label className="field-label" htmlFor="filtro-unidade">Filtrar por unidade</label>
            <select
              id="filtro-unidade"
              className="select-input"
              style={{ maxWidth: 260 }}
              value={filtroUnidade}
              onChange={(e) => setFiltroUnidade(e.target.value)}
            >
              <option value="">Todas as unidades</option>
              {unidades.map((u) => (
                <option key={u.id} value={u.id}>{u.nome}</option>
              ))}
            </select>
            <span className="toolbar-spacer" />
            {!carregando && <span className="composer-hint" style={{ margin: 0 }}>{usuarios.length} usuário(s)</span>}
          </div>

          {carregando && <p className="msg-p">Carregando usuários…</p>}
          {!carregando && !erro && usuarios.length === 0 && (
            <p className="msg-p">Nenhum usuário encontrado{filtroUnidade ? " nesta unidade" : ""}.</p>
          )}

          {usuarios.length > 0 && (
            <div className="table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Nome</th>
                    <th>Restrições</th>
                    <th>Alergias</th>
                    <th className="celula-num">Pontos</th>
                    <th className="celula-num">Nível</th>
                    <th className="celula-num">Streak</th>
                    <th className="celula-num">Registros</th>
                  </tr>
                </thead>
                <tbody>
                  {usuarios.map((u) => (
                    <tr key={u.id}>
                      <td className="celula-mono">{u.id}</td>
                      <td>{u.nome}</td>
                      <td>{csv(u.restricoes)}</td>
                      <td>{csv(u.alergias)}</td>
                      <td className="celula-num">{u.pontos.toLocaleString("pt-BR")}</td>
                      <td className="celula-num">{u.nivel}</td>
                      <td className="celula-num">{u.streak_dias > 0 ? `${u.streak_dias} dia(s)` : "—"}</td>
                      <td className="celula-num">{u.registros_consumo}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
