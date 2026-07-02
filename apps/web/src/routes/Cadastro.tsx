import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  atualizarUsuario,
  criarUsuario,
  getUsuario,
  getUsuarioIdSalvo,
  limparUsuarioIdSalvo,
  listarUnidades,
  setUsuarioIdSalvo,
} from "../lib/api";
import type { NivelAtividade, PerfilNutricional, Sexo, Unidade, UsuarioInput } from "../types";

const csvToArr = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
const arrToCsv = (a: string[] | null | undefined) => (a ?? []).join(", ");

const NIVEIS: { value: NivelAtividade; label: string }[] = [
  { value: "sedentario", label: "Sedentário" },
  { value: "leve", label: "Leve" },
  { value: "moderado", label: "Moderado" },
  { value: "intenso", label: "Intenso" },
  { value: "muito_intenso", label: "Muito intenso" },
];

export default function Cadastro() {
  const [usuarioId, setUsuarioId] = useState<number | null>(() => getUsuarioIdSalvo());
  const [carregando, setCarregando] = useState(usuarioId !== null);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [perfil, setPerfil] = useState<PerfilNutricional | null>(null);
  const [unidades, setUnidades] = useState<Unidade[]>([]);

  // Campos do formulário
  const [nome, setNome] = useState("");
  const [peso, setPeso] = useState("");
  const [altura, setAltura] = useState("");
  const [idade, setIdade] = useState("");
  const [sexo, setSexo] = useState<"" | Sexo>("");
  const [nivel, setNivel] = useState<"" | NivelAtividade>("");
  const [restricoes, setRestricoes] = useState("");
  const [preferencias, setPreferencias] = useState("");
  const [alergias, setAlergias] = useState("");
  const [unidadeId, setUnidadeId] = useState("");

  useEffect(() => {
    listarUnidades().then(setUnidades).catch(() => setUnidades([]));
  }, []);

  useEffect(() => {
    if (usuarioId === null) return;
    setCarregando(true);
    getUsuario(usuarioId)
      .then(({ usuario, perfil: p }) => {
        setNome(usuario.nome);
        setPeso(usuario.peso_kg ? String(usuario.peso_kg) : "");
        setAltura(usuario.altura_cm ? String(usuario.altura_cm) : "");
        setIdade(usuario.idade ? String(usuario.idade) : "");
        setSexo(usuario.sexo ?? "");
        setNivel(usuario.nivel_atividade ?? "");
        setRestricoes(arrToCsv(usuario.restricoes));
        setPreferencias(arrToCsv(usuario.preferencias));
        setAlergias(arrToCsv(usuario.alergias));
        setUnidadeId(usuario.unidade_id ? String(usuario.unidade_id) : "");
        setPerfil(p);
      })
      .catch((err: Error) => {
        if (err.message.includes("(404)")) {
          // Perfil não existe mais no backend — volta para modo criação.
          limparUsuarioIdSalvo();
          setUsuarioId(null);
        } else {
          setErro("Não foi possível carregar seu perfil. O backend está rodando?");
        }
      })
      .finally(() => setCarregando(false));
  }, [usuarioId]);

  function montarPayload(): UsuarioInput | string {
    if (!nome.trim()) return "Informe o seu nome.";
    const body: UsuarioInput = {
      nome: nome.trim(),
      restricoes: csvToArr(restricoes),
      preferencias: csvToArr(preferencias),
      alergias: csvToArr(alergias),
    };
    if (Number(peso) > 0) body.peso_kg = Number(peso);
    if (Number(altura) > 0) body.altura_cm = Number(altura);
    if (Number(idade) > 0) body.idade = Number(idade);
    if (sexo) body.sexo = sexo;
    if (nivel) body.nivel_atividade = nivel;
    if (Number(unidadeId) > 0) body.unidade_id = Number(unidadeId);
    return body;
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
    const req = usuarioId === null ? criarUsuario(payload) : atualizarUsuario(usuarioId, payload);
    req
      .then(({ usuario, perfil: p }) => {
        setUsuarioIdSalvo(usuario.id);
        setUsuarioId(usuario.id);
        setPerfil(p);
      })
      .catch((err: Error) => setErro(err.message))
      .finally(() => setSalvando(false));
  }

  function sair() {
    limparUsuarioIdSalvo();
    setUsuarioId(null);
    setPerfil(null);
    setNome("");
    setPeso("");
    setAltura("");
    setIdade("");
    setSexo("");
    setNivel("");
    setRestricoes("");
    setPreferencias("");
    setAlergias("");
    setUnidadeId("");
    setErro(null);
  }

  const editando = usuarioId !== null;

  return (
    <div className="app">
      <div className="chat-card admin-card">
        <header className="chat-header">
          <div className="brand">
            <div className="avatar avatar-lia"><span className="avatar-letter">L</span></div>
            <div className="brand-text">
              <h1 className="brand-name">Meu perfil</h1>
              <span className="status status-on">
                <span className="status-dot" />
                {editando ? "editando seu perfil" : "crie seu perfil nutricional"}
              </span>
            </div>
          </div>
          <div className="header-actions">
            {editando && <button className="btn-ghost" onClick={sair}>Sair</button>}
            <Link className="btn-ghost" to="/">Início</Link>
          </div>
        </header>

        <main className="messages admin-body">
          {erro && <p className="msg-p bubble-warning" style={{ padding: 12, borderRadius: 8 }}>{erro}</p>}
          {carregando && <p className="msg-p">Carregando seu perfil…</p>}

          {!carregando && perfil && (
            <div className="perfil-result">
              <h3 className="form-section">Perfil salvo ✓</h3>
              <div className="stat-tiles">
                <div className="stat-tile">
                  <span className="stat-label">IMC</span>
                  <span className="stat-value">{perfil.imc != null ? perfil.imc.toFixed(1) : "—"}</span>
                  <span className="stat-hint">{perfil.classificacao_imc || "informe peso e altura"}</span>
                </div>
                <div className="stat-tile">
                  <span className="stat-label">Meta calórica diária</span>
                  <span className="stat-value">
                    {perfil.meta_calorica_kcal != null ? perfil.meta_calorica_kcal.toLocaleString("pt-BR") : "—"}
                  </span>
                  <span className="stat-hint">
                    {perfil.meta_calorica_kcal != null ? "kcal/dia (Mifflin-St Jeor)" : "complete os dados físicos"}
                  </span>
                </div>
              </div>
              <p className="msg-p">
                Suas recomendações no chat agora são personalizadas.{" "}
                <Link to="/">Escolher unidade e conversar com a Lia →</Link>
              </p>
            </div>
          )}

          {!carregando && (
            <form className="form-card" onSubmit={salvar}>
              <h3 className="form-section">{editando ? "Editar dados" : "Seus dados"}</h3>
              <div className="form-grid">
                <div className="field field-2">
                  <label className="field-label">Nome*</label>
                  <input className="text-input" value={nome} onChange={(e) => setNome(e.target.value)} required />
                </div>
                <div className="field field-2">
                  <label className="field-label">Unidade preferida</label>
                  <select className="select-input" value={unidadeId} onChange={(e) => setUnidadeId(e.target.value)}>
                    <option value="">— sem unidade —</option>
                    {unidades.map((u) => (
                      <option key={u.id} value={u.id}>{u.nome}</option>
                    ))}
                  </select>
                </div>

                <div className="field">
                  <label className="field-label">Peso (kg)</label>
                  <input className="text-input" type="number" min={0} step="0.1" value={peso} onChange={(e) => setPeso(e.target.value)} placeholder="70" />
                </div>
                <div className="field">
                  <label className="field-label">Altura (cm)</label>
                  <input className="text-input" type="number" min={0} step="1" value={altura} onChange={(e) => setAltura(e.target.value)} placeholder="170" />
                </div>
                <div className="field">
                  <label className="field-label">Idade</label>
                  <input className="text-input" type="number" min={0} step="1" value={idade} onChange={(e) => setIdade(e.target.value)} placeholder="30" />
                </div>
                <div className="field">
                  <label className="field-label">Sexo</label>
                  <select className="select-input" value={sexo} onChange={(e) => setSexo(e.target.value as "" | Sexo)}>
                    <option value="">—</option>
                    <option value="M">Masculino</option>
                    <option value="F">Feminino</option>
                    <option value="O">Outro</option>
                  </select>
                </div>

                <div className="field field-2">
                  <label className="field-label">Nível de atividade</label>
                  <select className="select-input" value={nivel} onChange={(e) => setNivel(e.target.value as "" | NivelAtividade)}>
                    <option value="">—</option>
                    {NIVEIS.map((n) => (
                      <option key={n.value} value={n.value}>{n.label}</option>
                    ))}
                  </select>
                </div>
                <div className="field field-2">
                  <label className="field-label">Restrições (separadas por vírgula)</label>
                  <input className="text-input" value={restricoes} onChange={(e) => setRestricoes(e.target.value)} placeholder="vegetariano, sem lactose" />
                </div>
                <div className="field field-2">
                  <label className="field-label">Preferências</label>
                  <input className="text-input" value={preferencias} onChange={(e) => setPreferencias(e.target.value)} placeholder="frango, saladas" />
                </div>
                <div className="field field-2">
                  <label className="field-label">Alergias</label>
                  <input className="text-input" value={alergias} onChange={(e) => setAlergias(e.target.value)} placeholder="amendoim, camarão" />
                </div>
              </div>

              <div className="form-actions">
                <button className="btn-primary" type="submit" disabled={salvando}>
                  {salvando ? "Salvando…" : editando ? "Salvar alterações" : "Criar perfil"}
                </button>
              </div>
            </form>
          )}

          {!carregando && !perfil && (
            <p className="msg-p">
              Com peso, altura e idade calculamos seu <strong>IMC</strong> e a{" "}
              <strong>meta calórica diária</strong> — a Lia usa isso para personalizar as recomendações.
            </p>
          )}
        </main>
      </div>
    </div>
  );
}
