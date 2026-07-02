import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getAdminToken, listarUnidades, setAdminToken } from "../lib/api";
import type { Unidade } from "../types";

export default function Admin() {
  const [unidades, setUnidades] = useState<Unidade[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [token, setToken] = useState(getAdminToken());
  const [tokenSalvo, setTokenSalvo] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    listarUnidades()
      .then(setUnidades)
      .catch(() => setErro("Não foi possível carregar as unidades. O backend está rodando?"))
      .finally(() => setCarregando(false));
  }, []);

  function salvarToken() {
    setAdminToken(token);
    setTokenSalvo(true);
    setTimeout(() => setTokenSalvo(false), 1800);
  }

  return (
    <div className="app">
      <div className="chat-card admin-card">
        <header className="chat-header">
          <div className="brand">
            <div className="avatar avatar-lia"><span className="avatar-letter">L</span></div>
            <div className="brand-text">
              <h1 className="brand-name">Admin</h1>
              <span className="status status-on"><span className="status-dot" />gestão de cardápio e alimentos</span>
            </div>
          </div>
          <div className="header-actions">
            <Link className="btn-ghost" to="/admin/unidades">Unidades</Link>
            <Link className="btn-ghost" to="/admin/usuarios">Usuários</Link>
            <Link className="btn-ghost" to="/">Início</Link>
          </div>
        </header>

        <main className="messages admin-body">
          <div className="token-bar">
            <label className="field-label" htmlFor="admin-token">Token de admin</label>
            <div className="token-row">
              <input
                id="admin-token"
                className="text-input"
                type="password"
                placeholder="X-Admin-Token (deixe vazio se o gate estiver desabilitado)"
                value={token}
                onChange={(e) => setToken(e.target.value)}
              />
              <button className="btn-primary" onClick={salvarToken}>
                {tokenSalvo ? "Salvo ✓" : "Salvar"}
              </button>
            </div>
          </div>

          <p className="suggestions-title">Escolha a unidade para gerenciar</p>
          {carregando && <p className="msg-p">Carregando unidades…</p>}
          {erro && <p className="msg-p bubble-warning" style={{ padding: 12, borderRadius: 8 }}>{erro}</p>}

          <div className="unidade-grid">
            {unidades.map((u) => (
              <div key={u.id} className="unidade-card admin-unidade">
                <span className="unidade-nome">{u.nome}</span>
                <span className="unidade-slug">{u.slug}</span>
                <div className="admin-unidade-actions">
                  <button className="btn-primary btn-mini" onClick={() => navigate(`/admin/u/${u.id}/cardapio`)}>
                    Cardápio
                  </button>
                  <button className="btn-ghost btn-mini" onClick={() => navigate(`/admin/u/${u.id}/alimentos`)}>
                    Alimentos
                  </button>
                  <button className="btn-ghost btn-mini" onClick={() => navigate(`/admin/u/${u.id}/desperdicio`)}>
                    Desperdício
                  </button>
                </div>
              </div>
            ))}
          </div>

          {!carregando && !erro && unidades.length === 0 && (
            <p className="msg-p">Nenhuma unidade cadastrada ainda. Rode o seed do backend.</p>
          )}
        </main>
      </div>
    </div>
  );
}
