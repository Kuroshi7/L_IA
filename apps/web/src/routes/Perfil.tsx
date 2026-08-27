import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  ApiError,
  atualizarUsuario,
  criarUsuario,
  getUsuario,
  listarUnidadesCache,
  loginUsuario,
} from "../lib/api";
import { marca } from "../brand";
import AppShell from "../shell/AppShell";
import { usePerfil } from "../shell/PerfilContexto";
import { Aviso, Cabecalho, Pagina } from "../ui/Pagina";
import CampoTags from "../ui/CampoTags";
import type { NivelAtividade, PerfilNutricional, Sexo, Unidade, UsuarioInput } from "../types";

const NIVEIS: { valor: NivelAtividade; rotulo: string }[] = [
  { valor: "sedentario", rotulo: "Sedentário — trabalho parado, pouco exercício" },
  { valor: "leve", rotulo: "Leve — caminhadas, 1 a 2 treinos por semana" },
  { valor: "moderado", rotulo: "Moderado — 3 a 5 treinos por semana" },
  { valor: "intenso", rotulo: "Intenso — treino quase todo dia" },
  { valor: "muito_intenso", rotulo: "Muito intenso — trabalho físico ou treino duplo" },
];

/** Exemplos, não vocabulário fechado — ver a nota em ui/CampoTags.tsx. */
const RESTRICOES_COMUNS = ["vegetariano", "vegano", "sem glúten", "sem lactose"];
const ALERGIAS_COMUNS = ["amendoim", "frutos do mar", "ovo", "soja"];

export default function Perfil() {
  const { usuarioId, entrar, sair } = usePerfil();

  const [carregando, setCarregando] = useState(usuarioId !== null);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [perfil, setPerfil] = useState<PerfilNutricional | null>(null);
  const [unidades, setUnidades] = useState<Unidade[]>([]);

  const [nome, setNome] = useState("");
  const [peso, setPeso] = useState("");
  const [altura, setAltura] = useState("");
  const [idade, setIdade] = useState("");
  const [sexo, setSexo] = useState<"" | Sexo>("");
  const [nivel, setNivel] = useState<"" | NivelAtividade>("");
  const [restricoes, setRestricoes] = useState<string[]>([]);
  const [preferencias, setPreferencias] = useState<string[]>([]);
  const [alergias, setAlergias] = useState<string[]>([]);
  const [unidadeId, setUnidadeId] = useState("");
  const [telefone, setTelefone] = useState("");
  const [pin, setPin] = useState("");

  // Bloco "já tenho cadastro" (telefone + PIN)
  const [loginTelefone, setLoginTelefone] = useState("");
  const [loginPin, setLoginPin] = useState("");
  const [entrando, setEntrando] = useState(false);
  const [erroLogin, setErroLogin] = useState<string | null>(null);

  useEffect(() => {
    listarUnidadesCache().then(setUnidades).catch(() => setUnidades([]));
  }, []);

  useEffect(() => {
    if (usuarioId === null) { setCarregando(false); return; }
    setCarregando(true);
    getUsuario(usuarioId)
      .then(({ usuario, perfil: p }) => {
        setNome(usuario.nome);
        setPeso(usuario.peso_kg ? String(usuario.peso_kg) : "");
        setAltura(usuario.altura_cm ? String(usuario.altura_cm) : "");
        setIdade(usuario.idade ? String(usuario.idade) : "");
        setSexo(usuario.sexo ?? "");
        setNivel(usuario.nivel_atividade ?? "");
        setRestricoes(usuario.restricoes ?? []);
        setPreferencias(usuario.preferencias ?? []);
        setAlergias(usuario.alergias ?? []);
        setUnidadeId(usuario.unidade_id ? String(usuario.unidade_id) : "");
        setTelefone(usuario.telefone ?? "");
        setPin(""); // na edição o PIN só é enviado se a pessoa quiser trocar
        setPerfil(p);
      })
      .catch((err: Error) => {
        console.error("falha ao carregar perfil", err);
        // 404 = perfil não existe mais; o contexto já devolve ao estado anônimo.
        if (!err.message.includes("(404)")) {
          setErro("Não consegui carregar seu perfil agora. Verifique sua conexão e recarregue a página.");
        }
      })
      .finally(() => setCarregando(false));
  }, [usuarioId]);

  function montarPayload(): UsuarioInput | string {
    if (!nome.trim()) return "Informe o seu nome.";
    const body: UsuarioInput = {
      nome: nome.trim(),
      restricoes,
      preferencias,
      alergias,
    };
    if (Number(peso) > 0) body.peso_kg = Number(peso);
    if (Number(altura) > 0) body.altura_cm = Number(altura);
    if (Number(idade) > 0) body.idade = Number(idade);
    if (sexo) body.sexo = sexo;
    if (nivel) body.nivel_atividade = nivel;
    if (Number(unidadeId) > 0) body.unidade_id = Number(unidadeId);

    const tel = telefone.trim();
    const pinLimpo = pin.trim();
    if (pinLimpo && !/^\d{4,6}$/.test(pinLimpo)) return "O PIN precisa ter de 4 a 6 números.";
    if (usuarioId === null && tel && !pinLimpo) {
      return "Para cadastrar um telefone, escolha também um PIN de 4 a 6 números.";
    }
    if (tel) body.telefone = tel;
    if (pinLimpo) body.pin = pinLimpo;
    return body;
  }

  function salvar(e: FormEvent) {
    e.preventDefault();
    setErro(null);
    const payload = montarPayload();
    if (typeof payload === "string") { setErro(payload); return; }

    setSalvando(true);
    const req = usuarioId === null ? criarUsuario(payload) : atualizarUsuario(usuarioId, payload);
    req
      .then(({ usuario, perfil: p }) => {
        entrar(usuario.id);
        setPin("");
        setPerfil(p);
      })
      .catch((err: Error) => {
        console.error("falha ao salvar perfil", err);
        setErro(
          err instanceof ApiError && err.status === 409
            ? 'Este telefone já tem cadastro — use "Já tenho cadastro" para entrar.'
            : "Não consegui salvar agora. Tente de novo em alguns segundos.",
        );
      })
      .finally(() => setSalvando(false));
  }

  function fazerLogin(e: FormEvent) {
    e.preventDefault();
    setErroLogin(null);
    const tel = loginTelefone.trim();
    const pinLogin = loginPin.trim();
    if (!tel || !pinLogin) { setErroLogin("Informe telefone e PIN para entrar."); return; }

    setEntrando(true);
    loginUsuario(tel, pinLogin)
      .then(({ usuario }) => {
        setLoginTelefone("");
        setLoginPin("");
        entrar(usuario.id); // o efeito acima carrega o resto do perfil
      })
      .catch((err: Error) => {
        console.error("falha no login", err);
        setErroLogin(
          err instanceof ApiError && err.status === 401
            ? "Telefone ou PIN incorretos."
            : "Não consegui entrar agora. Verifique sua conexão e tente de novo.",
        );
      })
      .finally(() => setEntrando(false));
  }

  function desconectar() {
    sair();
    setPerfil(null);
    setNome(""); setPeso(""); setAltura(""); setIdade("");
    setSexo(""); setNivel("");
    setRestricoes([]); setPreferencias([]); setAlergias([]);
    setUnidadeId(""); setTelefone(""); setPin("");
    setErro(null); setErroLogin(null);
  }

  const editando = usuarioId !== null;

  return (
    <AppShell
      titulo="Meu perfil"
      acoes={editando ? <button className="btn btn--fantasma btn--mini" onClick={desconectar}>Sair</button> : undefined}
    >
      <Pagina estreita>
        <Cabecalho
          titulo={editando ? "Meu perfil" : "Criar meu perfil"}
          apoio={`Com seus dados a ${marca.assistente} para de responder “em geral” e passa a responder para você: pula o que faz mal, sugere a porção que cabe na sua meta e conta seus pontos.`}
        />

        {erro && <Aviso tom="erro" titulo="Não deu certo">{erro}</Aviso>}

        {carregando ? (
          <div className="esqueleto" style={{ height: 220 }} aria-label="Carregando perfil" />
        ) : (
          <>
            {perfil && (
              <section className="bloco">
                <div>
                  <h2 className="bloco__titulo">O que calculamos com seus dados</h2>
                  <p className="bloco__apoio">
                    Números de referência, não diagnóstico. Para orientação de saúde, procure um profissional.
                  </p>
                </div>
                <div className="mosaico">
                  <div className="numero">
                    <span className="numero__rotulo">IMC</span>
                    <span className="numero__valor">{perfil.imc != null ? perfil.imc.toFixed(1) : "—"}</span>
                    <span className="numero__apoio">{perfil.classificacao_imc || "informe peso e altura"}</span>
                  </div>
                  <div className="numero">
                    <span className="numero__rotulo">Meta calórica diária</span>
                    <span className="numero__valor">
                      {perfil.meta_calorica_kcal != null ? perfil.meta_calorica_kcal.toLocaleString("pt-BR") : "—"}
                    </span>
                    <span className="numero__apoio">
                      {perfil.meta_calorica_kcal != null ? "kcal/dia · Mifflin-St Jeor" : "complete os dados físicos"}
                    </span>
                  </div>
                </div>
                <Link className="btn btn--primario" to="/">Conversar com a {marca.assistente}</Link>
              </section>
            )}

            {!editando && (
              <form className="bloco" onSubmit={fazerLogin}>
                <div>
                  <h2 className="bloco__titulo">Já tenho cadastro</h2>
                  <p className="bloco__apoio">Criou seu perfil em outro aparelho? Entre com telefone e PIN.</p>
                </div>

                {erroLogin && <Aviso tom="erro">{erroLogin}</Aviso>}

                <div className="form-grid">
                  <div className="campo campo-2">
                    <label className="campo-rotulo" htmlFor="login-tel">Telefone com DDD</label>
                    <input
                      id="login-tel"
                      className="entrada"
                      type="tel"
                      inputMode="tel"
                      value={loginTelefone}
                      onChange={(e) => setLoginTelefone(e.target.value)}
                      placeholder="11 91234-5678"
                      autoComplete="tel"
                    />
                  </div>
                  <div className="campo campo-2">
                    <label className="campo-rotulo" htmlFor="login-pin">PIN</label>
                    <input
                      id="login-pin"
                      className="entrada"
                      type="password"
                      inputMode="numeric"
                      maxLength={6}
                      value={loginPin}
                      onChange={(e) => setLoginPin(e.target.value)}
                      placeholder="seu PIN"
                      autoComplete="current-password"
                    />
                  </div>
                </div>

                <div className="form-acoes">
                  <button className="btn btn--contorno" type="submit" disabled={entrando}>
                    {entrando ? "Entrando…" : "Entrar"}
                  </button>
                </div>
              </form>
            )}

            <form className="bloco" onSubmit={salvar}>
              <div>
                <h2 className="bloco__titulo">{editando ? "Seus dados" : "Seus dados"}</h2>
                <p className="bloco__apoio">
                  Só o nome é obrigatório. Peso, altura e idade servem para calcular sua meta calórica —
                  sem eles a {marca.assistente} continua ajudando, só não personaliza a porção.
                </p>
              </div>

              <div className="form-grid">
                <div className="campo campo-2">
                  <label className="campo-rotulo" htmlFor="p-nome">Como quer ser chamado *</label>
                  <input id="p-nome" className="entrada" value={nome} onChange={(e) => setNome(e.target.value)} required autoComplete="given-name" />
                </div>
                <div className="campo campo-2">
                  <label className="campo-rotulo" htmlFor="p-unidade">Onde você costuma comer</label>
                  <select id="p-unidade" className="selecao" value={unidadeId} onChange={(e) => setUnidadeId(e.target.value)}>
                    <option value="">Não escolhi ainda</option>
                    {unidades.filter((u) => u.ativo).map((u) => (
                      <option key={u.id} value={u.id}>{u.nome}</option>
                    ))}
                  </select>
                </div>

                <div className="campo">
                  <label className="campo-rotulo" htmlFor="p-peso">Peso (kg)</label>
                  <input id="p-peso" className="entrada" type="number" min={0} step="0.1" inputMode="decimal" value={peso} onChange={(e) => setPeso(e.target.value)} placeholder="70" />
                </div>
                <div className="campo">
                  <label className="campo-rotulo" htmlFor="p-altura">Altura (cm)</label>
                  <input id="p-altura" className="entrada" type="number" min={0} step="1" inputMode="numeric" value={altura} onChange={(e) => setAltura(e.target.value)} placeholder="170" />
                </div>
                <div className="campo">
                  <label className="campo-rotulo" htmlFor="p-idade">Idade</label>
                  <input id="p-idade" className="entrada" type="number" min={0} step="1" inputMode="numeric" value={idade} onChange={(e) => setIdade(e.target.value)} placeholder="30" />
                </div>
                <div className="campo">
                  <label className="campo-rotulo" htmlFor="p-sexo">Sexo</label>
                  <select id="p-sexo" className="selecao" value={sexo} onChange={(e) => setSexo(e.target.value as "" | Sexo)}>
                    <option value="">Prefiro não dizer</option>
                    <option value="M">Masculino</option>
                    <option value="F">Feminino</option>
                    <option value="O">Outro</option>
                  </select>
                </div>

                <div className="campo campo-4">
                  <label className="campo-rotulo" htmlFor="p-nivel">Rotina de atividade física</label>
                  <select id="p-nivel" className="selecao" value={nivel} onChange={(e) => setNivel(e.target.value as "" | NivelAtividade)}>
                    <option value="">Não informar</option>
                    {NIVEIS.map((n) => <option key={n.valor} value={n.valor}>{n.rotulo}</option>)}
                  </select>
                </div>

                <div className="campo-4">
                  <CampoTags
                    rotulo="Restrições alimentares"
                    valores={restricoes}
                    aoMudar={setRestricoes}
                    sugestoes={RESTRICOES_COMUNS}
                    placeholder="digite e aperte Enter"
                    ajuda="Uma por etiqueta. Vale escrever do seu jeito — a Lia entende variações."
                  />
                </div>
                <div className="campo-4">
                  <CampoTags
                    rotulo="Alergias"
                    valores={alergias}
                    aoMudar={setAlergias}
                    sugestoes={ALERGIAS_COMUNS}
                    placeholder="digite e aperte Enter"
                    ajuda="A Lia nunca sugere um prato com algo desta lista."
                  />
                </div>
                <div className="campo-4">
                  <CampoTags
                    rotulo="Preferências"
                    valores={preferencias}
                    aoMudar={setPreferencias}
                    placeholder="o que você gosta de comer"
                    ajuda="O que você gosta — usado para desempatar entre opções parecidas."
                  />
                </div>

                <div className="campo campo-2">
                  <label className="campo-rotulo" htmlFor="p-tel">Telefone com DDD</label>
                  <input id="p-tel" className="entrada" type="tel" inputMode="tel" value={telefone} onChange={(e) => setTelefone(e.target.value)} placeholder="11 91234-5678" autoComplete="tel" />
                </div>
                <div className="campo campo-2">
                  <label className="campo-rotulo" htmlFor="p-pin">{editando ? "Novo PIN" : "PIN de 4 a 6 números"}</label>
                  <input
                    id="p-pin"
                    className="entrada"
                    type="password"
                    inputMode="numeric"
                    maxLength={6}
                    value={pin}
                    onChange={(e) => setPin(e.target.value)}
                    placeholder={editando ? "deixe vazio para manter o atual" : "ex.: 1234"}
                    autoComplete="new-password"
                  />
                </div>
                <span className="campo-ajuda campo-4">
                  Telefone e PIN servem para recuperar seu perfil em outro aparelho.
                </span>
              </div>

              <div className="form-acoes">
                <button className="btn btn--primario" type="submit" disabled={salvando}>
                  {salvando ? "Salvando…" : editando ? "Salvar alterações" : "Criar perfil"}
                </button>
                {editando && (
                  <button className="btn btn--fantasma" type="button" onClick={desconectar}>
                    Sair desta conta
                  </button>
                )}
              </div>
            </form>
          </>
        )}
      </Pagina>
    </AppShell>
  );
}
