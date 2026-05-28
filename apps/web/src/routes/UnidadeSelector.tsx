import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listarUnidades } from "../lib/api";
import type { Unidade } from "../types";

export default function UnidadeSelector() {
  const [unidades, setUnidades] = useState<Unidade[]>([]);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    listarUnidades()
      .then((u) => setUnidades(u))
      .catch(() => setErro("Não foi possível carregar as unidades. O backend está rodando?"))
      .finally(() => setCarregando(false));
  }, []);

  return (
    <div className="app">
      <div className="chat-card selector-card">
        <header className="chat-header">
          <div className="brand">
            <div className="avatar avatar-lia"><span className="avatar-letter">L</span></div>
            <div className="brand-text">
              <h1 className="brand-name">Lia</h1>
              <span className="status status-on"><span className="status-dot" />escolha sua unidade</span>
            </div>
          </div>
          <div className="header-actions">
            <Link className="btn-ghost" to="/cadastro">Cadastro</Link>
            <Link className="btn-ghost" to="/admin">Admin</Link>
          </div>
        </header>

        <main className="messages selector-body">
          <p className="suggestions-title">De qual unidade você quer ver o cardápio?</p>

          {carregando && <p className="msg-p">Carregando unidades…</p>}
          {erro && <p className="msg-p bubble-warning" style={{ padding: 12, borderRadius: 8 }}>{erro}</p>}

          <div className="unidade-grid">
            {unidades.map((u) => (
              <button key={u.id} className="unidade-card" onClick={() => navigate(`/u/${u.id}/chat`)}>
                <span className="unidade-nome">{u.nome}</span>
                <span className="unidade-slug">{u.slug}</span>
              </button>
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
