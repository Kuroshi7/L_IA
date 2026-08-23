import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  adminAtualizarUnidade,
  adminCriarUnidade,
  adminListarUnidades,
  adminSetUnidadeAtiva,
} from "../../lib/api";
import type { Unidade } from "../../types";

const SLUG_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

export default function UnidadesAdmin() {
  const [unidades, setUnidades] = useState<Unidade[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  const [nome, setNome] = useState("");
  const [slug, setSlug] = useState("");

  const carregar = useCallback(() => {
    setCarregando(true);
    adminListarUnidades()
      .then(setUnidades)
      .catch((e: Error) => setErro(e.message))
      .finally(() => setCarregando(false));
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  function resetForm() {
    setEditingId(null);
    setNome("");
    setSlug("");
  }

  function editar(u: Unidade) {
    setEditingId(u.id);
    setNome(u.nome);
    setSlug(u.slug);
    window.scrollTo({ top: 0 });
  }

  const slugValido = slug === "" || SLUG_RE.test(slug);

  function salvar(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    if (!nome.trim()) {
      setErro("Informe o nome da unidade.");
      return;
    }
    if (!SLUG_RE.test(slug)) {
      setErro("Slug inválido — use apenas minúsculas, números e hífens (ex.: unidade-centro).");
      return;
    }
    setSalvando(true);
    const body = { nome: nome.trim(), slug };
    const req = editingId === null ? adminCriarUnidade(body) : adminAtualizarUnidade(editingId, body);
    req
      .then(() => {
        resetForm();
        carregar();
      })
      .catch((err: Error) => {
        if (err instanceof ApiError && err.status === 409) {
          setErro(`O slug "${slug}" já está em uso por outra unidade — escolha outro.`);
        } else {
          setErro(err.message);
        }
      })
      .finally(() => setSalvando(false));
  }

  function alternarAtiva(u: Unidade) {
    const acao = u.ativo ? "desativar" : "ativar";
    if (!window.confirm(`Tem certeza que deseja ${acao} a unidade "${u.nome}"?`)) return;
    adminSetUnidadeAtiva(u.id, !u.ativo)
      .then(() => carregar())
      .catch((err: Error) => setErro(err.message));
  }

  return (
    <div className="app">
      <div className="chat-card admin-card">
        <header className="chat-header">
          <div className="brand">
            <div className="avatar avatar-lia"><span className="avatar-letter">L</span></div>
            <div className="brand-text">
              <h1 className="brand-name">Unidades</h1>
              <span className="status status-on"><span className="status-dot" />{editingId ? "editando unidade" : "gestão de unidades"}</span>
            </div>
          </div>
          <div className="header-actions">
            <Link className="btn-ghost" to="/admin/usuarios">Usuários</Link>
            <Link className="btn-ghost" to="/admin">Admin</Link>
          </div>
        </header>

        <main className="messages admin-body">
          {erro && <p className="msg-p bubble-warning" style={{ padding: 12, borderRadius: 8 }}>{erro}</p>}

          <form className="form-card" onSubmit={salvar}>
            <h3 className="form-section">{editingId ? "Editar unidade" : "Nova unidade"}</h3>
            <div className="form-grid">
              <div className="field field-2">
                <label className="field-label">Nome*</label>
                <input className="text-input" value={nome} onChange={(e) => setNome(e.target.value)} placeholder="Restaurante Centro" required />
              </div>
              <div className="field field-2">
                <label className="field-label">Slug* (minúsculas, números e hífens)</label>
                <input
                  className="text-input"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value.toLowerCase())}
                  placeholder="restaurante-centro"
                  required
                />
                {!slugValido && <span className="field-error">Use apenas minúsculas, números e hífens.</span>}
              </div>
            </div>
            <div className="form-actions">
              <button className="btn-primary" type="submit" disabled={salvando}>
                {salvando ? "Salvando…" : editingId ? "Salvar alterações" : "Criar unidade"}
              </button>
              {editingId && (
                <button className="btn-ghost" type="button" onClick={resetForm}>Cancelar edição</button>
              )}
            </div>
          </form>

          <h3 className="form-section">Unidades cadastradas</h3>
          {carregando && <p className="msg-p">Carregando…</p>}
          {!carregando && unidades.length === 0 && !erro && <p className="msg-p">Nenhuma unidade ainda.</p>}

          {unidades.length > 0 && (
            <div className="table-wrap">
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Nome</th>
                    <th>Slug</th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {unidades.map((u) => (
                    <tr key={u.id} className={u.ativo ? "" : "linha-inativa"}>
                      <td>{u.nome}</td>
                      <td className="celula-mono">{u.slug}</td>
                      <td>
                        <span className={`status-badge ${u.ativo ? "status-badge-on" : "status-badge-off"}`}>
                          {u.ativo ? "ativa" : "inativa"}
                        </span>
                      </td>
                      <td className="celula-acoes">
                        <button className="btn-ghost btn-mini" onClick={() => editar(u)}>Editar</button>
                        <button className="btn-ghost btn-mini" onClick={() => alternarAtiva(u)}>
                          {u.ativo ? "Desativar" : "Ativar"}
                        </button>
                      </td>
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
