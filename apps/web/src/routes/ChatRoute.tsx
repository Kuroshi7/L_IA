import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import { enviarMensagem, getSaudacao, limparConversa, setUnidadeSalva } from "../lib/api";
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
  { icone: "prato", texto: "O que tem para comer hoje?" },
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

export default function ChatRoute() {
  const { unidadeId: param } = useParams();
  const unidadeId = Number(param);
  const unidade = useUnidade(unidadeId);
  const { usuarioId, nome, atualizar, brinde } = usePerfil();

  const chaveSessao = `lia_sessao_${unidadeId}`;

  const [sessionId, setSessionId] = useState<string>(() => localStorage.getItem(chaveSessao) || "");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [entrada, setEntrada] = useState("");
  const [ocupada, setOcupada] = useState(false);
  const [offline, setOffline] = useState(false);
  const [saudacao, setSaudacao] = useState("");
  const [mostrarDescer, setMostrarDescer] = useState(false);

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
      .then((m) => { setSaudacao(m); setOffline(false); })
      .catch(() => setOffline(true));
  }, []);

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

  const enviar = useCallback(
    async (bruto?: string) => {
      const texto = (bruto ?? entrada).trim();
      if (!texto || ocupada) return;

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
    [entrada, ocupada, unidadeId, sessionId, usuarioId, chaveSessao, adicionar, atualizar],
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

  const vazia = msgs.length === 0;
  const primeiroNome = nome.trim().split(/\s+/)[0] ?? "";

  return (
    <AppShell
      area="cliente"
      unidadeId={unidadeId}
      titulo={unidade?.nome ?? marca.assistente}
      variante="conversa"
      aoNovaConversa={novaConversa}
      novaConversaOcupada={ocupada}
      acoes={
        <button className="btn-icone" onClick={novaConversa} disabled={ocupada || vazia} aria-label="Nova conversa">
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
            {vazia ? (
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
                      <span className="digitando" role="status" aria-label={`${marca.assistente} está escrevendo`}>
                        <span /><span /><span />
                      </span>
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
                disabled={ocupada}
                aria-label="Sua mensagem"
                data-testid="compositor"
              />
              <button
                className="compositor__enviar"
                onClick={() => enviar()}
                disabled={ocupada || !entrada.trim()}
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
