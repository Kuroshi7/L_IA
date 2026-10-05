import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import {
  entrarDemo,
  enviarMensagem,
  getHistorico,
  getSaudacao,
  limparConversa,
  setUnidadeSalva,
} from "../lib/api";
import type { ExperienciaChat, ResumoConsumoExperiencia } from "../types";
import { marca } from "../brand";
import AppShell from "../shell/AppShell";
import { usePerfil } from "../shell/PerfilContexto";
import { useUnidade } from "../shell/useUnidade";
import Icone, { type NomeIcone } from "../ui/Icone";
import Texto from "../ui/Texto";

interface Msg {
  id: number;
  autor: "lia" | "usuario";
  texto: string;
  foraDeEscopo?: boolean;
  naoReconhecidos?: string[];
  aproximados?: string[];
  experiencia?: ExperienciaChat;
}

/**
 * Sugestões da tela inicial.
 *
 * São frases que a pessoa diria, não features do sistema — a primeira coisa que
 * alguém faz num chat é copiar o exemplo, então o exemplo ensina o vocabulário.
 * A quarta ensina a registrar o consumo, que é o passo que alimenta a
 * gamificação e o painel de desperdício e que ninguém descobria sozinho.
 */
const SUGESTOES: { icone: NomeIcone; texto: string }[] = [
  { icone: "prato", texto: "Quero um almoço leve, sem lactose e com bastante proteína" },
  { icone: "folha", texto: "Sou vegetariano — o que dá para montar hoje?" },
  { icone: "veto", texto: "Tenho intolerância à lactose e alergia a amendoim" },
  { icone: "alvo", texto: "Comi 2 conchas de arroz e um filé de frango" },
];

/** Saudação por horário. Não é enfeite: diz que a tela é de agora, o que num
 *  produto de refeitório (café/almoço/janta) é informação. */
function saudacaoDoDia(): string {
  const h = new Date().getHours();
  if (h < 12) return "Bom dia";
  if (h < 18) return "Boa tarde";
  return "Boa noite";
}

function Termos({ lista }: { lista: string[] }) {
  return (
    <>
      {lista.map((t, i) => (
        <span key={t}>
          {i > 0 && (i === lista.length - 1 ? " nem " : ", ")}
          <span className="nota-termo">{t}</span>
        </span>
      ))}
    </>
  );
}

/**
 * Nota de incerteza — mantida do desenho anterior, com o mesmo raciocínio.
 *
 * A Lia não inventa número nutricional: ela resolve o que a pessoa escreveu
 * contra a base de medidas caseiras. Isso falha de dois jeitos, e a pessoa
 * precisa distinguir:
 *
 *   não reconhecido → o item NÃO entrou na conta; o total está incompleto.
 *   aproximado      → o item entrou, mas a base não garante aquele número.
 *
 * Deliberadamente não é um alerta amarelo: não houve erro, houve honestidade.
 * Um aviso puniria visualmente a pessoa por ter escrito "macarronada" em vez de
 * "macarrão".
 */
function NotaIncerteza({ fora, aprox }: { fora?: string[]; aprox?: string[] }) {
  const temFora = !!fora?.length;
  const temAprox = !!aprox?.length;
  if (!temFora && !temAprox) return null;
  return (
    <div className="nota-incerteza">
      {temFora && (
        <p className="nota-linha">
          não achei <Termos lista={fora!} /> na tabela —{" "}
          {fora!.length > 1 ? "esses itens ficaram" : "esse item ficou"} fora da conta
        </p>
      )}
      {temAprox && (
        <p className="nota-linha">
          o valor de <Termos lista={aprox!} /> é aproximado
        </p>
      )}
    </div>
  );
}

function BotaoCopiar({ texto }: { texto: string }) {
  const [copiado, setCopiado] = useState(false);

  async function copiar() {
    try {
      await navigator.clipboard.writeText(texto);
      setCopiado(true);
      window.setTimeout(() => setCopiado(false), 1800);
    } catch {
      // Sem permissão de área de transferência (http sem TLS, por exemplo).
      // Silenciar é melhor que um erro que a pessoa não pode resolver.
    }
  }

  return (
    <button className="msg-acao" onClick={copiar} aria-label="Copiar resposta">
      <Icone nome={copiado ? "confere" : "copiar"} tam={14} />
      {copiado ? "copiado" : "copiar"}
    </button>
  );
}

function numero(valor?: number | null, casas = 0): string {
  if (typeof valor !== "number" || !Number.isFinite(valor)) return "—";
  return valor.toLocaleString("pt-BR", { maximumFractionDigits: casas });
}

function ResumoConsumo({ titulo, resumo }: { titulo: string; resumo?: ResumoConsumoExperiencia }) {
  if (!resumo) return null;
  return (
    <section className="exp-resumo">
      <span className="exp-resumo__titulo">{titulo}</span>
      {!!resumo.itens?.length && (
        <ul className="exp-resumo__itens">
          {resumo.itens.map((item, indice) => {
            const entrada = item.entrada;
            const nome = item.alimento_resolvido || entrada?.alimento || "Item";
            return (
              <li key={`${nome}-${indice}`}>
                <span>{entrada?.quantidade ? `${numero(entrada.quantidade, 1)} ` : ""}{entrada?.medida || "porção"} de {nome}</span>
                <strong>{numero(item.kcal)} kcal</strong>
              </li>
            );
          })}
        </ul>
      )}
      <div className="exp-macros">
        <strong>{numero(resumo.kcal)} kcal</strong>
        <span>{numero(resumo.proteina_g, 1)} g proteína</span>
        <span>{numero(resumo.carboidrato_g, 1)} g carboidratos</span>
      </div>
    </section>
  );
}

function Experiencia({
  dados,
  ocupada,
  aoEnviar,
  aoCorrigir,
}: {
  dados?: ExperienciaChat;
  ocupada: boolean;
  aoEnviar: (texto: string) => void;
  aoCorrigir: (inicio: string) => void;
}) {
  if (!dados) return null;

  if (dados.pratos?.length) {
    return (
      <div className="exp-pratos" aria-label={dados.titulo || "Opções do cardápio"}>
        {dados.pratos.map((prato) => (
          <article className="exp-prato" key={prato.id ?? prato.nome}>
            <div className="exp-prato__topo">
              <span className="exp-prato__categoria">{prato.categoria || "opção"}</span>
              {prato.is_proteina_do_dia && <span className="exp-selo">proteína do dia</span>}
            </div>
            <strong className="exp-prato__nome">{prato.nome}</strong>
            <div className="exp-macros">
              <strong>{numero(prato.calorias)} kcal</strong>
              <span>{numero(prato.proteinas_g, 1)} g proteína</span>
              <span>{numero(prato.carboidratos_g, 1)} g carboidratos</span>
            </div>
            {!!prato.ingredientes?.length && (
              <p className="exp-prato__ingredientes">{prato.ingredientes.join(" · ")}</p>
            )}
          </article>
        ))}
        {dados.fonte && <p className="exp-fonte">Dados verificados · {dados.fonte}</p>}
      </div>
    );
  }

  if (dados.tipo === "pergunta_sobras") {
    return (
      <div className="exp-acoes" aria-label="Informe se houve sobra">
        <button className="exp-btn exp-btn--principal" disabled={ocupada} onClick={() => aoEnviar("Não sobrou nada")}>Não sobrou nada</button>
        <button className="exp-btn" disabled={ocupada} onClick={() => aoCorrigir("Sobrou ")}>Informar sobra</button>
      </div>
    );
  }

  if (dados.tipo === "consumo_previa") {
    return (
      <div className="exp-consumo exp-consumo--previa">
        <div className="exp-cabecalho"><span>Prévia verificável</span><strong>Nada salvo ainda</strong></div>
        <ResumoConsumo titulo="Consumido" resumo={dados.consumido} />
        {dados.resto?.itens?.length ? <ResumoConsumo titulo="Sobras" resumo={dados.resto} /> : <p className="exp-sem-sobra">Sem sobras informadas</p>}
        <div className="exp-acoes">
          <button className="exp-btn exp-btn--principal" disabled={ocupada || dados.pode_confirmar === false} onClick={() => aoEnviar("Confirmar registro")}>Confirmar e pontuar</button>
          <button className="exp-btn" disabled={ocupada} onClick={() => aoCorrigir("Quero corrigir: ")}>Corrigir</button>
        </div>
      </div>
    );
  }

  if (dados.tipo === "consumo_registrado") {
    const pontos = dados.pontuacao?.pontos;
    return (
      <div className="exp-consumo exp-consumo--confirmado" role="status">
        <div className="exp-impacto">
          <span className="exp-impacto__icone">✓</span>
          <div><span>Consumo registrado</span><strong>{typeof pontos === "number" ? `+${pontos} pontos` : "Impacto atualizado"}</strong></div>
        </div>
        <ResumoConsumo titulo="Resumo final" resumo={dados.consumido} />
        <div className="exp-metricas">
          <span><small>desperdício</small><strong>{numero(dados.indice_resto_perc, 1)}%</strong></span>
          {dados.gamificacao && <span><small>nível</small><strong>{numero(dados.gamificacao.nivel)}</strong></span>}
          {dados.gamificacao && <span><small>sequência</small><strong>{numero(dados.gamificacao.streak_dias)} dias</strong></span>}
        </div>
      </div>
    );
  }

  return null;
}

export default function ChatRoute() {
  const { unidadeId: param } = useParams();
  const unidadeId = Number(param);
  const unidade = useUnidade(unidadeId);
  const { usuarioId, nome, atualizar, brinde, entrar } = usePerfil();

  const chaveSessao = `lia_sessao_${unidadeId}`;

  const [sessionId, setSessionId] = useState<string>(() => localStorage.getItem(chaveSessao) || "");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [entrada, setEntrada] = useState("");
  const [ocupada, setOcupada] = useState(false);
  const [offline, setOffline] = useState(false);
  const [saudacao, setSaudacao] = useState("");
  const [mostrarDescer, setMostrarDescer] = useState(false);
  const [carregandoHistorico, setCarregandoHistorico] = useState(Boolean(sessionId));
  const [etapa, setEtapa] = useState("Entendendo seu pedido…");
  const [entrandoDemo, setEntrandoDemo] = useState(false);
  const [erroDemo, setErroDemo] = useState("");
  const [demoDisponivel, setDemoDisponivel] = useState(false);

  const fluxoRef = useRef<HTMLDivElement>(null);
  const fimRef = useRef<HTMLDivElement>(null);
  const campoRef = useRef<HTMLTextAreaElement>(null);
  const proximoId = useRef(0);
  // Guarda se o usuário estava lendo o fim da conversa quando a mensagem chegou.
  const coladoNoFim = useRef(true);

  /** Em tela de toque o Enter do teclado virtual é "nova linha", não "enviar" —
   *  quem digita no celular espera quebrar linha, e mandar sem querer é pior do
   *  que ter que tocar no botão. */
  const toque = useMemo(() => window.matchMedia?.("(pointer: coarse)").matches ?? false, []);

  // Unidade da URL é a fonte da verdade; guardar permite abrir o app direto aqui.
  useEffect(() => {
    if (Number.isFinite(unidadeId) && unidadeId > 0) setUnidadeSalva(unidadeId);
  }, [unidadeId]);

  useEffect(() => {
    getSaudacao()
      .then((dados) => {
        setSaudacao(dados.mensagem);
        setDemoDisponivel(dados.demo_mode);
        setOffline(false);
      })
      .catch(() => setOffline(true));
  }, []);

  // Restaura a conversa da API, não apenas o identificador local. Ao trocar de
  // unidade, cada refeitório continua com sua própria sessão e seu histórico.
  useEffect(() => {
    let vivo = true;
    const salvo = localStorage.getItem(chaveSessao) || "";
    setSessionId(salvo);
    setMsgs([]);
    setCarregandoHistorico(Boolean(salvo));
    if (!salvo) return () => { vivo = false; };

    getHistorico(salvo)
      .then((data) => {
        if (!vivo) return;
        const restauradas: Msg[] = data.mensagens.map((m, indice) => ({
          id: indice,
          autor: m.papel === "user" ? "usuario" : "lia",
          texto: m.conteudo,
        }));
        proximoId.current = restauradas.length;
        setMsgs(restauradas);
      })
      .catch(() => {
        if (!vivo) return;
        localStorage.removeItem(chaveSessao);
        setSessionId("");
      })
      .finally(() => { if (vivo) setCarregandoHistorico(false); });
    return () => { vivo = false; };
  }, [chaveSessao]);

  useEffect(() => {
    if (!ocupada) {
      setEtapa("Entendendo seu pedido…");
      return;
    }
    const consultando = window.setTimeout(() => setEtapa("Consultando cardápio e perfil…"), 900);
    const verificando = window.setTimeout(() => setEtapa("Verificando dados nutricionais…"), 2800);
    return () => {
      window.clearTimeout(consultando);
      window.clearTimeout(verificando);
    };
  }, [ocupada]);
  // Cresce com o texto até um teto — depois rola por dentro. Sem isso, uma
  // mensagem de três linhas fica escondida numa fresta de uma linha.
  useLayoutEffect(() => {
    const el = campoRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [entrada]);

  // Só arrasta a conversa para baixo se a pessoa já estava no fim. Ela pode
  // estar relendo a recomendação anterior — puxar a tela nesse momento é roubar
  // a leitura.
  useEffect(() => {
    if (coladoNoFim.current) fimRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [msgs, ocupada]);

  useEffect(() => { if (!ocupada) campoRef.current?.focus(); }, [ocupada]);

  const aoRolar = useCallback(() => {
    const el = fluxoRef.current;
    if (!el) return;
    const distancia = el.scrollHeight - el.scrollTop - el.clientHeight;
    coladoNoFim.current = distancia < 120;
    setMostrarDescer(distancia > 240);
  }, []);

  const descer = useCallback(() => {
    coladoNoFim.current = true;
    fimRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, []);

  const adicionar = useCallback((m: Omit<Msg, "id">) => {
    setMsgs((prev) => [...prev, { ...m, id: proximoId.current++ }]);
  }, []);

  const corrigir = useCallback((inicio: string) => {
    setEntrada(inicio);
    window.setTimeout(() => campoRef.current?.focus(), 0);
  }, []);

  const ativarDemo = useCallback(async () => {
    if (entrandoDemo) return;
    setEntrandoDemo(true);
    setErroDemo("");
    try {
      const data = await entrarDemo();
      entrar(data.usuario.id);
      setOffline(false);
    } catch {
      setErroDemo("O perfil de demonstração não está habilitado nesta instalação.");
    } finally {
      setEntrandoDemo(false);
    }
  }, [entrandoDemo, entrar]);

  const enviar = useCallback(
    async (bruto?: string) => {
      const texto = (bruto ?? entrada).trim();
      if (!texto || ocupada || carregandoHistorico) return;

      setEntrada("");
      coladoNoFim.current = true; // mandei uma mensagem: quero ver a resposta
      adicionar({ autor: "usuario", texto });
      setOcupada(true);

      try {
        const data = await enviarMensagem(unidadeId, sessionId || null, texto, usuarioId);
        if (data.session_id && data.session_id !== sessionId) {
          setSessionId(data.session_id);
          localStorage.setItem(chaveSessao, data.session_id);
        }
        adicionar({
          autor: "lia",
          texto: data.resposta,
          foraDeEscopo: data.fora_de_escopo,
          naoReconhecidos: data.confianca?.nao_reconhecidos,
          aproximados: data.confianca?.aproximados,
          experiencia: data.experiencia,
        });
        setOffline(false);
        // A pessoa pode ter registrado consumo nesta mensagem — a pontuação muda.
        atualizar(true);
      } catch (err) {
        console.error("falha ao enviar mensagem", err);
        setOffline(true);
        adicionar({
          autor: "lia",
          texto:
            "Não consegui responder agora — a conexão falhou no caminho. Tente de novo em alguns segundos; sua mensagem não se perdeu.",
        });
      } finally {
        setOcupada(false);
      }
    },
    [entrada, ocupada, carregandoHistorico, unidadeId, sessionId, usuarioId, chaveSessao, adicionar, atualizar],
  );

  const novaConversa = useCallback(async () => {
    if (ocupada) return;
    if (sessionId) await limparConversa(sessionId).catch(() => undefined);
    localStorage.removeItem(chaveSessao);
    setSessionId("");
    setMsgs([]);
    setEntrada("");
    campoRef.current?.focus();
  }, [ocupada, sessionId, chaveSessao]);

  function aoTeclar(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey && !toque) {
      e.preventDefault();
      void enviar();
    }
  }

  // URL com unidade inválida: redireciona declarativamente. Chamar navigate()
  // durante o render é efeito colateral no meio da renderização — funciona por
  // acidente e o React reclama.
  if (!Number.isFinite(unidadeId) || unidadeId <= 0) {
    return <Navigate to="/unidades" replace />;
  }

  const vazia = msgs.length === 0 && !carregandoHistorico;
  const primeiroNome = nome.trim().split(/\s+/)[0] ?? "";

  return (
    <AppShell
      area="cliente"
      unidadeId={unidadeId}
      titulo={unidade?.nome ?? marca.assistente}
      variante="conversa"
      aoNovaConversa={novaConversa}
      novaConversaOcupada={ocupada || carregandoHistorico}
      acoes={
        <button className="btn-icone" onClick={novaConversa} disabled={ocupada || carregandoHistorico || vazia} aria-label="Nova conversa">
          <Icone nome="nova" />
        </button>
      }
    >
      <div className={`chat${vazia ? " chat--vazio" : ""}`}>
        {brinde && (
          <div className={`brinde${brinde.nivelUp ? " brinde--nivel" : ""}`} role="status">
            <Icone nome="pontos" tam={16} />
            {brinde.texto}
          </div>
        )}

        <div className="chat__fluxo" ref={fluxoRef} onScroll={aoRolar}>
          <div className="coluna">
            {carregandoHistorico ? (
              <div className="chat-carregando" role="status">Retomando sua conversa…</div>
            ) : vazia ? (
              <div className="abertura">
                {/* Cumprimenta pelo nome quando sabe quem é. A apresentação da
                    Lia não vem daqui: vem da saudação do servidor, logo abaixo —
                    dizer "sou a Lia" nas duas linhas soava a formulário. */}
                <h2 className="abertura__saudacao">
                  {saudacaoDoDia()}
                  {primeiroNome && <>, <em>{primeiroNome}</em></>}.
                </h2>
                <p className="abertura__convite">
                  {offline
                    ? "Ainda não consegui falar com o servidor. Confira sua conexão e tente enviar uma mensagem — se voltar, respondo na hora."
                    : saudacao ||
                      "Me conte suas restrições ou peça uma recomendação do cardápio de hoje."}
                </p>
                {!usuarioId && !offline && demoDisponivel && (
                  <div className="demo-entrada">
                    <button className="exp-btn exp-btn--principal" onClick={ativarDemo} disabled={entrandoDemo}>
                      {entrandoDemo ? "Preparando perfil…" : "Usar perfil de demonstração"}
                    </button>
                    <span>restrições, meta e pontos prontos para a apresentação</span>
                  </div>
                )}
                {erroDemo && <p className="demo-entrada__erro" role="alert">{erroDemo}</p>}
              </div>
            ) : (
              <div className="msgs" role="log" aria-live="polite" aria-label="Conversa">
                {msgs.map((m, i) => {
                  if (m.autor === "usuario") {
                    return (
                      <article className="msg msg--usuario" key={m.id} data-testid="msg-usuario">
                        <div className="msg__corpo">{m.texto}</div>
                      </article>
                    );
                  }
                  const continua = i > 0 && msgs[i - 1].autor === "lia";
                  return (
                    <article
                      className={`msg msg--lia${continua ? " msg--continua" : ""}${m.foraDeEscopo ? " msg--fora" : ""}`}
                      key={m.id}
                      data-testid="msg-lia"
                    >
                      <span className="msg__selo" aria-hidden="true">{marca.monograma}</span>
                      <div className="msg__corpo">
                        <span className="vis-oculto">{marca.assistente} respondeu:</span>
                        <Texto conteudo={m.texto} />
                        {m.foraDeEscopo && (
                          <span className="msg__fora-nota">fora do cardápio</span>
                        )}
                        <NotaIncerteza fora={m.naoReconhecidos} aprox={m.aproximados} />
                        <Experiencia
                          dados={m.experiencia}
                          ocupada={ocupada}
                          aoEnviar={(texto) => { void enviar(texto); }}
                          aoCorrigir={corrigir}
                        />
                        <div className="msg__acoes">
                          <BotaoCopiar texto={m.texto} />
                        </div>
                      </div>
                    </article>
                  );
                })}

                {ocupada && (
                  <article className="msg msg--lia" data-testid="msg-digitando">
                    <span className="msg__selo" aria-hidden="true">{marca.monograma}</span>
                    <div className="msg__corpo">
                      <div className="progresso-ia" role="status">
                        <span className="digitando" aria-hidden="true"><span /><span /><span /></span>
                        <span>{etapa}</span>
                      </div>
                    </div>
                  </article>
                )}
                <div ref={fimRef} />
              </div>
            )}
          </div>
        </div>

        {mostrarDescer && !vazia && (
          <button className="btn-descer" onClick={descer} aria-label="Ir para a última mensagem">
            <Icone nome="baixo" tam={18} />
          </button>
        )}

        <div className="chat__doca">
          <div className="coluna">
            <div className="compositor">
              <textarea
                ref={campoRef}
                value={entrada}
                onChange={(e) => setEntrada(e.target.value)}
                onKeyDown={aoTeclar}
                placeholder={`Fale com a ${marca.assistente}…`}
                rows={1}
                disabled={ocupada || carregandoHistorico}
                aria-label="Sua mensagem"
                data-testid="compositor"
              />
              <button
                className="compositor__enviar"
                onClick={() => enviar()}
                disabled={ocupada || carregandoHistorico || !entrada.trim()}
                aria-label="Enviar mensagem"
                data-testid="enviar"
              >
                <Icone nome="enviar" tam={18} />
              </button>
            </div>

            {vazia && (
              <div className="sugestoes">
                {SUGESTOES.map((s) => (
                  <button key={s.texto} className="sugestao" onClick={() => enviar(s.texto)}>
                    <Icone nome={s.icone} tam={18} className="sugestao__icone" />
                    <span>{s.texto}</span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {!vazia && (
            <p className="compositor-dica">
              {toque
                ? `A ${marca.assistente} responde sobre o cardápio desta unidade.`
                : `Enter envia · Shift+Enter quebra linha · a ${marca.assistente} responde sobre o cardápio desta unidade`}
            </p>
          )}
        </div>
      </div>
    </AppShell>
  );
}
