import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useParams } from "react-router-dom";
import {
  adminAtualizarAlimento,
  adminBuscarNutri,
  adminCriarAlimento,
  adminListarAlimentos,
  adminSetAlimentoAtivo,
} from "../../lib/api";
import AppShell from "../../shell/AppShell";
import { Aviso, Cabecalho, Pagina, Silhueta, Vazio } from "../../ui/Pagina";
import { mensagemAdmin } from "../../lib/mensagens";
import Icone from "../../ui/Icone";
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
      .catch((e: Error) => { console.error("falha ao listar alimentos", e); setErro(mensagemAdmin(e)); })
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
    adminBuscarNutri(busca.trim())
      .then(setResultados)
      .catch((e: Error) => { console.error("falha na busca de referências", e); setErro(mensagemAdmin(e)); });
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
      .catch((err: Error) => { console.error("falha ao salvar alimento", err); setErro(mensagemAdmin(err)); })
      .finally(() => setSalvando(false));
  }

  function alternarAtivo(a: Alimento) {
    adminSetAlimentoAtivo(a.id, !a.ativo)
      .then(() => carregar())
      .catch((err: Error) => { console.error("falha ao alternar alimento", err); setErro(mensagemAdmin(err)); });
  }

  return (
    <AppShell area="gestor" unidadeId={unidadeId} titulo="Alimentos">
      <Pagina>
        <Cabecalho
          titulo="Catálogo de alimentos"
          apoio="O que existe aqui é o que pode entrar no cardápio. As medidas caseiras são o que permite a Lia responder “2 conchas” sem inventar número."
        />

        {erro && <Aviso tom="erro" titulo="Não deu certo">{erro}</Aviso>}

        <form className="bloco" onSubmit={salvar}>
          <h2 className="bloco__titulo">{editingId ? "Editar alimento" : "Novo alimento"}</h2>

          <div className="form-grid">
            <div className="campo campo-2">
              <label className="campo-rotulo" htmlFor="al-nome">Nome *</label>
              <input id="al-nome" className="entrada" value={nome} onChange={(e) => setNome(e.target.value)} required />
            </div>
            <div className="campo campo-2">
              <label className="campo-rotulo" htmlFor="al-cat">Categoria</label>
              <input id="al-cat" className="entrada" value={categoria} onChange={(e) => setCategoria(e.target.value)} placeholder="Proteína, Acompanhamento…" />
            </div>

            <div className="campo campo-4">
              <label className="campo-rotulo" htmlFor="al-ing">Ingredientes</label>
              <input id="al-ing" className="entrada" value={ingredientes} onChange={(e) => setIngredientes(e.target.value)} placeholder="arroz, alho, azeite" />
              <span className="campo-ajuda">Separe por vírgula.</span>
            </div>

            <div className="campo campo-2">
              <label className="campo-rotulo" htmlFor="al-alerg">Alérgenos</label>
              <input id="al-alerg" className="entrada" value={alergenos} onChange={(e) => setAlergenos(e.target.value)} placeholder="lactose, glúten" />
              <span className="campo-ajuda">A Lia nunca oferece este prato a quem declarou alergia a um destes.</span>
            </div>
            <div className="campo campo-2">
              <label className="campo-rotulo" htmlFor="al-restr">Restrições atendidas</label>
              <input id="al-restr" className="entrada" value={restricoes} onChange={(e) => setRestricoes(e.target.value)} placeholder="vegetariano, sem lactose" />
              <span className="campo-ajuda">Escreva como o cliente escreveria — é contra isto que a restrição dele é comparada.</span>
            </div>
            <div className="campo campo-2">
              <label className="campo-rotulo" htmlFor="al-nao">Não indicado para</label>
              <input id="al-nao" className="entrada" value={naoIndicado} onChange={(e) => setNaoIndicado(e.target.value)} placeholder="vegano" />
            </div>
            <div className="campo campo-2" style={{ justifyContent: "flex-end" }}>
              <label className="marcador">
                <input type="checkbox" checked={ativo} onChange={(e) => setAtivo(e.target.checked)} />
                Disponível para uso no cardápio
              </label>
            </div>

            <div className="campo">
              <label className="campo-rotulo" htmlFor="al-kcal">Calorias (kcal)</label>
              <input id="al-kcal" className="entrada" type="number" min={0} value={calorias} onChange={(e) => setCalorias(Number(e.target.value) || 0)} />
            </div>
            <div className="campo">
              <label className="campo-rotulo" htmlFor="al-prot">Proteínas (g)</label>
              <input id="al-prot" className="entrada" type="number" min={0} step="0.1" value={proteinas} onChange={(e) => setProteinas(Number(e.target.value) || 0)} />
            </div>
            <div className="campo">
              <label className="campo-rotulo" htmlFor="al-carb">Carboidratos (g)</label>
              <input id="al-carb" className="entrada" type="number" min={0} step="0.1" value={carbo} onChange={(e) => setCarbo(Number(e.target.value) || 0)} />
            </div>
            <div className="campo">
              <label className="campo-rotulo" htmlFor="al-gord">Gorduras (g)</label>
              <input id="al-gord" className="entrada" type="number" min={0} step="0.1" value={gordura} onChange={(e) => setGordura(Number(e.target.value) || 0)} />
            </div>
          </div>

          <div>
            <span className="secao-rotulo">Medidas caseiras</span>
            <p className="bloco__apoio">
              Sem elas a Lia não consegue converter “uma concha” em gramas — e prefere dizer que não sabe a chutar.
            </p>
          </div>

          <div className="barra-ferramentas" role="radiogroup" aria-label="Origem das medidas caseiras">
            {(["novo", "vincular", ...(editingId ? (["manter"] as RefMode[]) : [])] as RefMode[]).map((m) => (
              <label key={m} className="marcador">
                <input type="radio" name="refmode" checked={refMode === m} onChange={() => setRefMode(m)} />
                {m === "novo" ? "Cadastrar agora" : m === "vincular" ? "Usar uma já existente" : "Manter a atual"}
              </label>
            ))}
          </div>

          {refMode === "novo" && (
            <div className="porcoes">
              <div className="porcao-linha porcao-cabecalho">
                <span>Medida (ex.: concha)</span><span>g</span><span>kcal</span><span>Prot</span><span>Carb</span><span>Gord</span><span />
              </div>
              {porcoes.map((p, i) => (
                <div className="porcao-linha" key={i}>
                  <input className="entrada" value={p.medida_label} onChange={(e) => setPorcao(i, "medida_label", e.target.value)} placeholder="concha" aria-label="Nome da medida" />
                  <input className="entrada" type="number" min={0} value={p.quantidade_g} onChange={(e) => setPorcao(i, "quantidade_g", e.target.value)} aria-label="Gramas" />
                  <input className="entrada" type="number" min={0} value={p.kcal} onChange={(e) => setPorcao(i, "kcal", e.target.value)} aria-label="Calorias" />
                  <input className="entrada" type="number" min={0} step="0.1" value={p.proteina_g} onChange={(e) => setPorcao(i, "proteina_g", e.target.value)} aria-label="Proteínas" />
                  <input className="entrada" type="number" min={0} step="0.1" value={p.carboidrato_g} onChange={(e) => setPorcao(i, "carboidrato_g", e.target.value)} aria-label="Carboidratos" />
                  <input className="entrada" type="number" min={0} step="0.1" value={p.gordura_g} onChange={(e) => setPorcao(i, "gordura_g", e.target.value)} aria-label="Gorduras" />
                  <button
                    type="button"
                    className="remove"
                    aria-label={`Remover a medida ${p.medida_label || i + 1}`}
                    onClick={() => setPorcoes((prev) => prev.filter((_, idx) => idx !== i))}
                  >
                    <Icone nome="remover" tam={14} />
                  </button>
                </div>
              ))}
              <div>
                <button type="button" className="btn btn--contorno btn--mini" onClick={() => setPorcoes((prev) => [...prev, porcaoVazia()])}>
                  Adicionar medida
                </button>
              </div>
            </div>
          )}

          {refMode === "vincular" && (
            <div className="campo">
              <label className="campo-rotulo" htmlFor="al-busca">Buscar referência já cadastrada</label>
              <div className="barra-ferramentas">
                <input
                  id="al-busca"
                  className="entrada"
                  style={{ flex: 1, minWidth: 220 }}
                  value={busca}
                  onChange={(e) => setBusca(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); buscarNutri(); } }}
                  placeholder="ex.: arroz"
                />
                <button type="button" className="btn btn--contorno" onClick={buscarNutri}>
                  <Icone nome="busca" tam={16} /> Buscar
                </button>
              </div>
              {vinculo && <p className="campo-ajuda">Vinculado a <strong>{vinculo.nome}</strong>.</p>}
              <div className="busca-resultados">
                {resultados.map((r) => (
                  <button
                    type="button"
                    key={r.id}
                    className={`pilula${vinculo?.id === r.id ? " pilula--ativa" : ""}`}
                    aria-pressed={vinculo?.id === r.id}
                    onClick={() => setVinculo(r)}
                  >
                    {r.nome}{r.categoria ? ` · ${r.categoria}` : ""}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div className="form-acoes">
            <button className="btn btn--primario" type="submit" disabled={salvando}>
              {salvando ? "Salvando…" : editingId ? "Salvar alterações" : "Cadastrar alimento"}
            </button>
            {editingId && (
              <button className="btn btn--fantasma" type="button" onClick={resetForm}>Cancelar</button>
            )}
          </div>
        </form>

        <section className="bloco bloco--plano">
          <span className="secao-rotulo">Cadastrados</span>

          {carregando && <Silhueta linhas={4} altura={56} />}

          {!carregando && alimentos.length === 0 && !erro && (
            <Vazio titulo="Nenhum alimento cadastrado">
              Cadastre o primeiro no formulário acima. Sem catálogo não há cardápio.
            </Vazio>
          )}

          <div className="cat-lista">
            {alimentos.map((a) => (
              <div className={`cat-linha${a.ativo ? "" : " cat-inativo"}`} key={a.id}>
                <div className="cat-info">
                  <span className="cat-nome">
                    {a.nome}
                    {a.categoria && <span className="cat-cat"> · {a.categoria}</span>}
                    {a.nutri_alimento_id != null && (
                      <span className="etiqueta etiqueta--acento" style={{ marginLeft: 8 }}>medidas caseiras</span>
                    )}
                  </span>
                  <span className="cat-macros">
                    {a.calorias} kcal · P {a.proteinas_g} g · C {a.carboidratos_g} g · G {a.gorduras_g} g
                  </span>
                </div>
                <div className="cat-acoes">
                  <button className="btn btn--fantasma btn--mini" onClick={() => editar(a)}>Editar</button>
                  <button className="btn btn--fantasma btn--mini" onClick={() => alternarAtivo(a)}>
                    {a.ativo ? "Desativar" : "Ativar"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>
      </Pagina>
    </AppShell>
  );
}
