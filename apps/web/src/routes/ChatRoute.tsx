import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { enviarMensagem, getGamificacao, getSaudacao, getUsuarioIdSalvo, limparConversa } from "../lib/api";
import type { Gamificacao } from "../types";

interface Msg {
  role: "ai" | "user";
  text: string;
  foraDeEscopo?: boolean;
  naoReconhecidos?: string[];
  aproximados?: string[];
}

const SUGESTOES = [
  { icon: "🥦", text: "Sou vegetariano, o que tem hoje?" },
  { icon: "🚫", text: "Tenho intolerância à lactose, qual é o mais proteico?" },
  { icon: "🌾", text: "Sou celíaco e alérgico a amendoim" },
  { icon: "💪", text: "Quero algo low carb e proteico" },
];

function renderInline(text: string): React.ReactNode[] {
  const parts: React.ReactNode[] = [];
  let i = 0;
  let last = 0;
  while (i < text.length) {
    if (text[i] === "*" && text[i + 1] === "*") {
      const end = text.indexOf("**", i + 2);
      if (end > -1) {
        if (i > last) parts.push(text.slice(last, i));
        parts.push(<strong key={parts.length}>{text.slice(i + 2, end)}</strong>);
        i = end + 2;
        last = i;
        continue;
      }
    }
    i++;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

function MarkdownMessage({ text }: { text: string }) {
  const blocks = useMemo(() => {
    const lines = text.split("\n");
    const out: React.ReactNode[] = [];
    let bullets: string[] = [];
    const flush = () => {
      if (bullets.length) {
        out.push(
          <ul className="msg-list" key={`ul-${out.length}`}>
            {bullets.map((b, idx) => (
              <li key={idx}>{renderInline(b)}</li>
            ))}
          </ul>,
        );
        bullets = [];
      }
    };
    for (const raw of lines) {
      const line = raw.trimEnd();
      if (/^[-•·*]\s+/.test(line)) {
        bullets.push(line.replace(/^[-•·*]\s+/, ""));
      } else if (line === "") {
        flush();
      } else {
        flush();
        out.push(<p className="msg-p" key={`p-${out.length}`}>{renderInline(line)}</p>);
      }
    }
    flush();
    return out;
  }, [text]);
  return <div className="msg-md">{blocks}</div>;
}

/**
 * Nota de incerteza.
 *
 * A Lia nunca inventa número nutricional: ela resolve o que a pessoa escreveu
 * contra a base de medidas caseiras. Isso falha de dois jeitos diferentes, e a
 * pessoa precisa distinguir:
 *
 *   não reconhecido → o item NÃO entrou na conta; o total está incompleto.
 *   aproximado      → o item entrou, mas a base não garante aquele número.
 *
 * Deliberadamente não é um badge de alerta como o "fora de escopo": não houve
 * erro, houve honestidade. Um aviso amarelo puniria visualmente a pessoa por ter
 * escrito "macarronada" em vez de "macarrão". É marginália: filete terracota,
 * texto miúdo, minúscula, colado embaixo da fala.
 */
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

function NotaIncerteza({ fora, aprox }: { fora?: string[]; aprox?: string[] }) {
  const semFora = !fora || fora.length === 0;
  const semAprox = !aprox || aprox.length === 0;
  if (semFora && semAprox) return null;
  return (
    <div className="nota-incerteza">
      {!semFora && (
        <p className="nota-linha">
          não achei <Termos lista={fora!} /> na tabela —{" "}
          {fora!.length > 1 ? "esses itens ficaram" : "esse item ficou"} fora da conta
        </p>
      )}
      {!semAprox && (
        <p className="nota-linha">
          o valor de <Termos lista={aprox!} /> é aproximado
        </p>
      )}
    </div>
  );
}

function AvatarLia() {
  return <div className="avatar avatar-lia" title="Lia"><span className="avatar-letter">L</span></div>;
}

export default function ChatRoute() {
  const { unidadeId: unidadeParam } = useParams();
  const unidadeId = Number(unidadeParam);
  const storageKey = `lia_session_${unidadeId}`;

  const [sessionId, setSessionId] = useState<string>(() => localStorage.getItem(storageKey) || "");
  const [mensagens, setMensagens] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [carregando, setCarregando] = useState(false);
  const [erroConexao, setErroConexao] = useState(false);
  const [usuarioId] = useState<number | null>(() => getUsuarioIdSalvo());
  const [gami, setGami] = useState<Gamificacao | null>(null);
  const [gamiToast, setGamiToast] = useState<{ texto: string; nivelUp: boolean } | null>(null);
  const fimRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const gamiAnteriorRef = useRef<Gamificacao | null>(null);
  const toastTimerRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (toastTimerRef.current !== null) window.clearTimeout(toastTimerRef.current);
    },
    [],
  );

  // Busca a gamificação; com notificar=true, compara com os pontos anteriores e
  // mostra um toast temporário quando o usuário ganhou pontos com a mensagem.
  const atualizarGamificacao = useCallback(
    (notificar = false) => {
      if (!usuarioId) return;
      getGamificacao(usuarioId)
        .then((d) => {
          const anterior = gamiAnteriorRef.current;
          gamiAnteriorRef.current = d.gamificacao;
          setGami(d.gamificacao);

          if (!notificar || !anterior || d.gamificacao.pontos <= anterior.pontos) return;

          const delta = d.gamificacao.pontos - anterior.pontos;
          const nivelUp = d.gamificacao.nivel > anterior.nivel;
          const partes = [`+${delta} pts`];
          const ev = d.eventos?.[0];
          if (ev?.bonus_prato_limpo) partes.push(`prato limpo +${ev.bonus_prato_limpo}`);
          if (ev?.bonus_streak) partes.push(`streak +${ev.bonus_streak}`);
          partes.push(`nível ${d.gamificacao.nivel}`);
          const texto = nivelUp
            ? `Subiu para o nível ${d.gamificacao.nivel}! 🎉 · ${partes.slice(0, -1).join(" · ")}`
            : partes.join(" · ");

          setGamiToast({ texto, nivelUp });
          if (toastTimerRef.current !== null) window.clearTimeout(toastTimerRef.current);
          toastTimerRef.current = window.setTimeout(() => setGamiToast(null), 6000);
        })
        .catch(() => undefined);
    },
    [usuarioId],
  );

  useEffect(() => {
    atualizarGamificacao();
  }, [atualizarGamificacao]);

  useEffect(() => {
    getSaudacao()
      .then((m) => {
        setMensagens([{ role: "ai", text: m }]);
        setErroConexao(false);
      })
      .catch(() => {
        setErroConexao(true);
        setMensagens([{ role: "ai", text: "Olá! Sou a Lia 🍽️\n\n_Backend offline — inicie a API para conversarmos._" }]);
      });
  }, []);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens, carregando]);

  useEffect(() => {
    if (!carregando) inputRef.current?.focus();
  }, [carregando]);

  async function enviar(textoBruto?: string) {
    const texto = (textoBruto ?? input).trim();
    if (!texto || carregando) return;
    setInput("");
    setMensagens((prev) => [...prev, { role: "user", text: texto }]);
    setCarregando(true);
    try {
      const data = await enviarMensagem(unidadeId, sessionId || null, texto, usuarioId);
      if (data.session_id && data.session_id !== sessionId) {
        setSessionId(data.session_id);
        localStorage.setItem(storageKey, data.session_id);
      }
      setMensagens((prev) => [...prev, {
        role: "ai",
        text: data.resposta,
        foraDeEscopo: data.fora_de_escopo,
        naoReconhecidos: data.confianca?.nao_reconhecidos,
        aproximados: data.confianca?.aproximados,
      }]);
      setErroConexao(false);
      // O usuário pode ter registrado consumo pelo chat — pontos podem ter mudado.
      atualizarGamificacao(true);
    } catch {
      setErroConexao(true);
      setMensagens((prev) => [...prev, { role: "ai", text: "⚠️ Não consegui me conectar agora. Verifique se o backend está rodando." }]);
    } finally {
      setCarregando(false);
    }
  }

  async function novaConversa() {
    if (sessionId) await limparConversa(sessionId).catch(() => undefined);
    localStorage.removeItem(storageKey);
    setSessionId("");
    const m = await getSaudacao().catch(() => "Conversa reiniciada! 🍽️");
    setMensagens([{ role: "ai", text: m }]);
  }

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void enviar();
    }
  }

  const mostrandoSugestoes = mensagens.length <= 1 && !carregando;

  return (
    <div className="app">
      <div className="chat-card">
        <header className="chat-header">
          <div className="brand">
            <AvatarLia />
            <div className="brand-text">
              <h1 className="brand-name">Lia</h1>
              <span className={`status ${erroConexao ? "status-off" : "status-on"}`}>
                <span className="status-dot" />
                {erroConexao ? "offline" : "online · pronta para te ajudar"}
              </span>
            </div>
          </div>
          <div className="header-actions">
            {gami && (
              <span className="gami-chip" title={`Streak: ${gami.streak_dias} dia(s)`}>
                ⭐ {gami.pontos} pts · nível {gami.nivel}
              </span>
            )}
            {!usuarioId && (
              <Link className="perfil-link" to="/cadastro">
                Criar perfil para recomendações personalizadas
              </Link>
            )}
            <Link className="btn-ghost" to={`/u/${unidadeId}/ranking`}>🏆 Ranking</Link>
            <Link className="btn-ghost" to="/">Trocar unidade</Link>
            <button className="btn-ghost" onClick={novaConversa} disabled={carregando}>Nova conversa</button>
          </div>
        </header>

        <main className="messages">
          {gamiToast && (
            <div className={`gami-toast${gamiToast.nivelUp ? " gami-toast-nivel" : ""}`} role="status">
              <span className="gami-toast-icon">⭐</span>
              <span>{gamiToast.texto}</span>
            </div>
          )}
          {mensagens.map((msg, i) => (
            <div key={i} className={`row row-${msg.role}`}>
              {msg.role === "ai" && <AvatarLia />}
              <div className={`bubble bubble-${msg.role}${msg.foraDeEscopo ? " bubble-warning" : ""}`}>
                <MarkdownMessage text={msg.text} />
                {msg.foraDeEscopo && <span className="badge">fora de escopo</span>}
                <NotaIncerteza fora={msg.naoReconhecidos} aprox={msg.aproximados} />
              </div>
              {msg.role === "user" && <div className="avatar avatar-user" title="Você">🙂</div>}
            </div>
          ))}
          {carregando && (
            <div className="row row-ai">
              <AvatarLia />
              <div className="bubble bubble-ai bubble-typing">
                <span className="typing-dots"><span /><span /><span /></span>
              </div>
            </div>
          )}
          <div ref={fimRef} />
        </main>

        {mostrandoSugestoes && (
          <div className="suggestions">
            <p className="suggestions-title">Experimente perguntar:</p>
            <div className="chips">
              {SUGESTOES.map((s) => (
                <button key={s.text} className="chip" onClick={() => enviar(s.text)}>
                  <span className="chip-icon">{s.icon}</span>
                  <span>{s.text}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        <footer className="composer">
          <div className="composer-inner">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              placeholder="Conte suas restrições ou peça uma recomendação…"
              rows={1}
              disabled={carregando}
            />
            <button className="btn-send" onClick={() => enviar()} disabled={carregando || !input.trim()} aria-label="Enviar">
              ➤
            </button>
          </div>
          <p className="composer-hint">Enter envia · Shift+Enter nova linha · Lia só responde sobre o cardápio desta unidade</p>
        </footer>
      </div>
    </div>
  );
}
