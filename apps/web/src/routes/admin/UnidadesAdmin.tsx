import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  ApiError,
  adminAtualizarUnidade,
  adminCriarUnidade,
  adminListarUnidades,
  adminSetUnidadeAtiva,
} from "../../lib/api";
import AppShell from "../../shell/AppShell";
import { Aviso, Cabecalho, Pagina, Silhueta, Vazio } from "../../ui/Pagina";
import { mensagemAdmin } from "../../lib/mensagens";
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
      .catch((e: Error) => { console.error("falha ao listar unidades", e); setErro(mensagemAdmin(e)); })
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
          console.error("falha ao salvar unidade", err);
          setErro(mensagemAdmin(err));
        }
      })
      .finally(() => setSalvando(false));
  }

  function alternarAtiva(u: Unidade) {
    const acao = u.ativo ? "desativar" : "ativar";
    if (!window.confirm(`Tem certeza que deseja ${acao} a unidade "${u.nome}"?`)) return;
    adminSetUnidadeAtiva(u.id, !u.ativo)
      .then(() => carregar())
      .catch((err: Error) => { console.error("falha ao alternar unidade", err); setErro(mensagemAdmin(err)); });
  }

  return (
    <AppShell area="gestor" titulo="Unidades">
      <Pagina>
        <Cabecalho
          titulo="Unidades"
          apoio="Cada unidade é um refeitório com cardápio e catálogo próprios. Desativar não apaga nada: só tira a unidade da lista que o cliente vê."
        />

        {erro && <Aviso tom="erro" titulo="Não deu certo">{erro}</Aviso>}

        <form className="bloco" onSubmit={salvar}>
          <h2 className="bloco__titulo">{editingId ? "Editar unidade" : "Nova unidade"}</h2>
          <div className="form-grid">
            <div className="campo campo-2">
              <label className="campo-rotulo" htmlFor="un-nome">Nome *</label>
              <input
                id="un-nome"
                className="entrada"
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                placeholder="Restaurante Centro"
                required
              />
            </div>
            <div className="campo campo-2">
              <label className="campo-rotulo" htmlFor="un-slug">Identificador *</label>
              <input
                id="un-slug"
                className="entrada"
                value={slug}
                onChange={(e) => setSlug(e.target.value.toLowerCase())}
                placeholder="restaurante-centro"
                aria-describedby="un-slug-ajuda"
                required
              />
              {slugValido ? (
                <span className="campo-ajuda" id="un-slug-ajuda">
                  Aparece no endereço da unidade. Minúsculas, números e hífens.
                </span>
              ) : (
                <span className="campo-erro" id="un-slug-ajuda">
                  Use apenas minúsculas, números e hífens — por exemplo, unidade-centro.
                </span>
              )}
            </div>
          </div>
          <div className="form-acoes">
            <button className="btn btn--primario" type="submit" disabled={salvando}>
              {salvando ? "Salvando…" : editingId ? "Salvar alterações" : "Criar unidade"}
            </button>
            {editingId && (
              <button className="btn btn--fantasma" type="button" onClick={resetForm}>Cancelar</button>
            )}
          </div>
        </form>

        {carregando && <Silhueta linhas={3} altura={44} />}

        {!carregando && unidades.length === 0 && !erro && (
          <Vazio titulo="Nenhuma unidade cadastrada">
            Crie a primeira acima — sem unidade não há cardápio nem conversa.
          </Vazio>
        )}

        {unidades.length > 0 && (
          <div className="tabela-caixa">
            <table className="tabela">
              <thead>
                <tr>
                  <th>Nome</th>
                  <th>Identificador</th>
                  <th>Situação</th>
                  <th><span className="vis-oculto">Ações</span></th>
                </tr>
              </thead>
              <tbody>
                {unidades.map((u) => (
                  <tr key={u.id} className={u.ativo ? "" : "linha-inativa"}>
                    <td>{u.nome}</td>
                    <td className="celula-mono">{u.slug}</td>
                    <td>
                      <span className={`etiqueta${u.ativo ? " etiqueta--ok" : ""}`}>
                        {u.ativo ? "ativa" : "inativa"}
                      </span>
                    </td>
                    <td className="celula-acoes">
                      <button className="btn btn--fantasma btn--mini" onClick={() => editar(u)}>Editar</button>
                      <button className="btn btn--fantasma btn--mini" onClick={() => alternarAtiva(u)}>
                        {u.ativo ? "Desativar" : "Ativar"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Pagina>
    </AppShell>
  );
}
