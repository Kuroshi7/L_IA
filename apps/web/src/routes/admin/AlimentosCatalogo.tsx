import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useParams } from "react-router-dom";
import {
  adminAtualizarAlimento,
  adminBuscarNutri,
  adminCriarAlimento,
  adminListarAlimentos,
  adminSetAlimentoAtivo,
} from "../../lib/api";
import type { Alimento, AlimentoInput, NutriAlimento, PorcaoInput } from "../../types";

type RefMode = "manter" | "novo" | "vincular";

type PorcaoForm = {
  medida_label: string;
  quantidade_g: number;
  kcal: number;
  proteina_g: number;
  carboidrato_g: number;
  gordura_g: number;
};

const porcaoVazia = (): PorcaoForm => ({
  medida_label: "",
  quantidade_g: 0,
  kcal: 0,
  proteina_g: 0,
  carboidrato_g: 0,
  gordura_g: 0,
});

const csvToArr = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
const arrToCsv = (a: string[]) => a.join(", ");

export default function AlimentosCatalogo() {
  const unidadeId = Number(useParams().unidadeId);
  const [alimentos, setAlimentos] = useState<Alimento[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);

  // Campos do menu
  const [nome, setNome] = useState("");
  const [categoria, setCategoria] = useState("");
  const [ingredientes, setIngredientes] = useState("");
  const [alergenos, setAlergenos] = useState("");
  const [restricoes, setRestricoes] = useState("");
  const [naoIndicado, setNaoIndicado] = useState("");
  const [calorias, setCalorias] = useState(0);
  const [proteinas, setProteinas] = useState(0);
  const [carbo, setCarbo] = useState(0);
  const [gordura, setGordura] = useState(0);
  const [ativo, setAtivo] = useState(true);

  // Referência nutricional (medidas caseiras)
  const [refMode, setRefMode] = useState<RefMode>("novo");
  const [porcoes, setPorcoes] = useState<PorcaoForm[]>([porcaoVazia()]);
  const [busca, setBusca] = useState("");
  const [resultados, setResultados] = useState<NutriAlimento[]>([]);
  const [vinculo, setVinculo] = useState<NutriAlimento | null>(null);

  const carregar = useCallback(() => {
    setCarregando(true);
    adminListarAlimentos(unidadeId)
      .then(setAlimentos)
      .catch((e: Error) => setErro(e.message))
      .finally(() => setCarregando(false));
  }, [unidadeId]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  function resetForm() {
    setEditingId(null);
    setNome("");
    setCategoria("");
    setIngredientes("");
    setAlergenos("");
    setRestricoes("");
    setNaoIndicado("");
    setCalorias(0);
    setProteinas(0);
    setCarbo(0);
    setGordura(0);
    setAtivo(true);
    setRefMode("novo");
    setPorcoes([porcaoVazia()]);
    setBusca("");
    setResultados([]);
    setVinculo(null);
  }

  function editar(a: Alimento) {
    setEditingId(a.id);
    setNome(a.nome);
    setCategoria(a.categoria);
    setIngredientes(arrToCsv(a.ingredientes));
    setAlergenos(arrToCsv(a.alergenos));
    setRestricoes(arrToCsv(a.restricoes_atendidas));
    setNaoIndicado(arrToCsv(a.nao_indicado_para));
    setCalorias(a.calorias);
    setProteinas(a.proteinas_g);
    setCarbo(a.carboidratos_g);
    setGordura(a.gorduras_g);
    setAtivo(a.ativo);
    setRefMode("manter");
    setPorcoes([porcaoVazia()]);
    setVinculo(null);
    setBusca("");
    setResultados([]);
    window.scrollTo({ top: 0 });
  }

  function buscarNutri() {
    if (busca.trim().length < 2) return;
    adminBuscarNutri(busca.trim()).then(setResultados).catch((e: Error) => setErro(e.message));
  }

  function setPorcao(i: number, campo: keyof PorcaoForm, valor: string) {
    setPorcoes((prev) =>
      prev.map((p, idx) =>
        idx === i ? { ...p, [campo]: campo === "medida_label" ? valor : Number(valor) || 0 } : p,
      ),
    );
  }

  function montarPayload(): AlimentoInput | string {
    if (!nome.trim()) return "Informe o nome do alimento.";

    const base: AlimentoInput = {
      nome: nome.trim(),
      categoria: categoria.trim(),
      ingredientes: csvToArr(ingredientes),
      alergenos: csvToArr(alergenos),
      restricoes_atendidas: csvToArr(restricoes),
      nao_indicado_para: csvToArr(naoIndicado),
      calorias: Number(calorias) || 0,
      proteinas_g: Number(proteinas) || 0,
      carboidratos_g: Number(carbo) || 0,
      gorduras_g: Number(gordura) || 0,
      ativo,
    };

    if (refMode === "vincular") {
      if (!vinculo) return "Selecione uma referência nutricional para vincular.";
      base.nutri_alimento_id = vinculo.id;
    } else if (refMode === "novo") {
      const validas: PorcaoInput[] = porcoes
        .filter((p) => p.medida_label.trim() && p.quantidade_g > 0)
        .map((p) => ({
          medida_label: p.medida_label.trim(),
          quantidade_g: p.quantidade_g,
          kcal: p.kcal,
          proteina_g: p.proteina_g,
          carboidrato_g: p.carboidrato_g,
          gordura_g: p.gordura_g,
        }));
      if (validas.length === 0) {
        return "Cadastre ao menos uma medida caseira (rótulo + gramas).";
      }
      base.nova_ref = { nome: nome.trim(), categoria: categoria.trim(), porcoes: validas };
    } else if (editingId === null) {
      // criação exige medidas caseiras ou vínculo
      return "Cadastre as medidas caseiras (porções) ou vincule uma referência existente.";
    }
    return base;
  }

  function salvar(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    const payload = montarPayload();
    if (typeof payload === "string") {
      setErro(payload);
      return;
    }
    setSalvando(true);
    const req =
      editingId === null
        ? adminCriarAlimento(unidadeId, payload)
        : adminAtualizarAlimento(editingId, payload);
    req
      .then(() => {
        resetForm();
        carregar();
      })
      .catch((err: Error) => setErro(err.message))
      .finally(() => setSalvando(false));
  }

  function alternarAtivo(a: Alimento) {
    adminSetAlimentoAtivo(a.id, !a.ativo)
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
              <h1 className="brand-name">Catálogo de alimentos</h1>
              <span className="status status-on"><span className="status-dot" />{editingId ? "editando" : "novo cadastro"}</span>
            </div>
          </div>
          <div className="header-actions">
            <Link className="btn-ghost" to={`/admin/u/${unidadeId}/cardapio`}>Cardápio</Link>
            <Link className="btn-ghost" to="/admin">Admin</Link>
          </div>
        </header>

        <main className="messages admin-body">
          {erro && <p className="msg-p bubble-warning" style={{ padding: 12, borderRadius: 8 }}>{erro}</p>}

          <form className="form-card" onSubmit={salvar}>
            <h3 className="form-section">{editingId ? "Editar alimento" : "Novo alimento"}</h3>

            <div className="form-grid">
              <div className="field field-2">
                <label className="field-label">Nome*</label>
                <input className="text-input" value={nome} onChange={(e) => setNome(e.target.value)} required />
              </div>
              <div className="field">
                <label className="field-label">Categoria</label>
                <input className="text-input" value={categoria} onChange={(e) => setCategoria(e.target.value)} placeholder="Proteína, Acompanhamento…" />
              </div>

              <div className="field field-3">
                <label className="field-label">Ingredientes (separados por vírgula)</label>
                <input className="text-input" value={ingredientes} onChange={(e) => setIngredientes(e.target.value)} placeholder="arroz, alho, azeite" />
              </div>
              <div className="field">
                <label className="field-label">Alérgenos</label>
                <input className="text-input" value={alergenos} onChange={(e) => setAlergenos(e.target.value)} placeholder="lactose, gluten" />
              </div>
              <div className="field">
                <label className="field-label">Restrições atendidas</label>
                <input className="text-input" value={restricoes} onChange={(e) => setRestricoes(e.target.value)} placeholder="vegetariano, sem lactose" />
              </div>
              <div className="field">
                <label className="field-label">Não indicado para</label>
                <input className="text-input" value={naoIndicado} onChange={(e) => setNaoIndicado(e.target.value)} placeholder="vegano" />
              </div>

              <div className="field">
                <label className="field-label">Calorias (kcal)</label>
                <input className="text-input" type="number" min={0} value={calorias} onChange={(e) => setCalorias(Number(e.target.value) || 0)} />
              </div>
              <div className="field">
                <label className="field-label">Proteínas (g)</label>
                <input className="text-input" type="number" min={0} step="0.1" value={proteinas} onChange={(e) => setProteinas(Number(e.target.value) || 0)} />
              </div>
              <div className="field">
                <label className="field-label">Carboidratos (g)</label>
                <input className="text-input" type="number" min={0} step="0.1" value={carbo} onChange={(e) => setCarbo(Number(e.target.value) || 0)} />
              </div>
              <div className="field">
                <label className="field-label">Gorduras (g)</label>
                <input className="text-input" type="number" min={0} step="0.1" value={gordura} onChange={(e) => setGordura(Number(e.target.value) || 0)} />
              </div>

              <div className="field check-field">
                <label className="check-label">
                  <input type="checkbox" checked={ativo} onChange={(e) => setAtivo(e.target.checked)} /> Ativo
                </label>
              </div>
            </div>

            <h3 className="form-section">Medidas caseiras (trabalho do nutricionista)</h3>
            <div className="ref-mode">
              {(["novo", "vincular", ...(editingId ? (["manter"] as RefMode[]) : [])] as RefMode[]).map((m) => (
                <label key={m} className="radio-label">
                  <input type="radio" name="refmode" checked={refMode === m} onChange={() => setRefMode(m)} />
                  {m === "novo" ? "Cadastrar porções" : m === "vincular" ? "Vincular existente" : "Manter atual"}
                </label>
              ))}
            </div>

            {refMode === "novo" && (
              <div className="porcoes">
                <div className="porcao-row porcao-head">
                  <span>Medida (ex.: concha)</span><span>g</span><span>kcal</span><span>Prot</span><span>Carb</span><span>Gord</span><span />
                </div>
                {porcoes.map((p, i) => (
                  <div className="porcao-row" key={i}>
                    <input className="text-input" value={p.medida_label} onChange={(e) => setPorcao(i, "medida_label", e.target.value)} placeholder="concha" />
                    <input className="text-input" type="number" min={0} value={p.quantidade_g} onChange={(e) => setPorcao(i, "quantidade_g", e.target.value)} />
                    <input className="text-input" type="number" min={0} value={p.kcal} onChange={(e) => setPorcao(i, "kcal", e.target.value)} />
                    <input className="text-input" type="number" min={0} step="0.1" value={p.proteina_g} onChange={(e) => setPorcao(i, "proteina_g", e.target.value)} />
                    <input className="text-input" type="number" min={0} step="0.1" value={p.carboidrato_g} onChange={(e) => setPorcao(i, "carboidrato_g", e.target.value)} />
                    <input className="text-input" type="number" min={0} step="0.1" value={p.gordura_g} onChange={(e) => setPorcao(i, "gordura_g", e.target.value)} />
                    <button type="button" className="item-remove" onClick={() => setPorcoes((prev) => prev.filter((_, idx) => idx !== i))}>×</button>
                  </div>
                ))}
                <button type="button" className="btn-ghost btn-mini" onClick={() => setPorcoes((prev) => [...prev, porcaoVazia()])}>
                  + adicionar medida
                </button>
              </div>
            )}

            {refMode === "vincular" && (
              <div className="vincular">
                <div className="token-row">
                  <input className="text-input" value={busca} onChange={(e) => setBusca(e.target.value)} placeholder="buscar referência (ex.: arroz)" />
                  <button type="button" className="btn-ghost" onClick={buscarNutri}>Buscar</button>
                </div>
                {vinculo && <p className="msg-p">Vinculado a: <strong>{vinculo.nome}</strong></p>}
                <div className="busca-resultados">
                  {resultados.map((r) => (
                    <button type="button" key={r.id} className={`chip${vinculo?.id === r.id ? " chip-on" : ""}`} onClick={() => setVinculo(r)}>
                      {r.nome}{r.categoria ? ` · ${r.categoria}` : ""}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="form-actions">
              <button className="btn-primary" type="submit" disabled={salvando}>
                {salvando ? "Salvando…" : editingId ? "Salvar alterações" : "Cadastrar alimento"}
              </button>
              {editingId && (
                <button className="btn-ghost" type="button" onClick={resetForm}>Cancelar edição</button>
              )}
            </div>
          </form>

          <h3 className="form-section">Alimentos cadastrados</h3>
          {carregando && <p className="msg-p">Carregando…</p>}
          {!carregando && alimentos.length === 0 && <p className="msg-p">Nenhum alimento ainda.</p>}
          <div className="cat-list">
            {alimentos.map((a) => (
              <div className={`cat-row${a.ativo ? "" : " cat-inativo"}`} key={a.id}>
                <div className="cat-info">
                  <span className="cat-nome">
                    {a.nome}
                    {a.categoria && <span className="cat-cat"> · {a.categoria}</span>}
                    {a.nutri_alimento_id && <span className="cat-badge" title="Medidas caseiras vinculadas">⚖ medidas</span>}
                  </span>
                  <span className="cat-macros">
                    {a.calorias} kcal · P {a.proteinas_g} · C {a.carboidratos_g} · G {a.gorduras_g}
                  </span>
                </div>
                <div className="cat-actions">
                  <button className="btn-ghost btn-mini" onClick={() => editar(a)}>Editar</button>
                  <button className="btn-ghost btn-mini" onClick={() => alternarAtivo(a)}>
                    {a.ativo ? "Desativar" : "Ativar"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </main>
      </div>
    </div>
  );
}
