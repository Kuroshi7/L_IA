import { useEffect, useMemo, useRef, useState } from "react";
import { enviarMensagem, gerarSessionId, getOuCriarSessionId, getSaudacao, limparConversa } from "./api.js";

const SUGESTOES = [
  { icon: "🥦", text: "Sou vegetariano, o que tem hoje?" },
  { icon: "🚫", text: "Tenho intolerância à lactose, qual é o mais proteico?" },
  { icon: "🌾", text: "Sou celíaco e alérgico a amendoim" },
  { icon: "💪", text: "Quero algo low carb e proteico" },
];

function renderMarkdownInline(text) {
  const parts = [];
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

function MarkdownMessage({ text }) {
  const blocks = useMemo(() => {
    const lines = text.split("\n");
    const out = [];
    let bullets = [];
    const flush = () => {
      if (bullets.length) {
        out.push(
          <ul className="msg-list" key={`ul-${out.length}`}>
            {bullets.map((b, idx) => (
              <li key={idx}>{renderMarkdownInline(b)}</li>
            ))}
          </ul>
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
        out.push(
          <p className="msg-p" key={`p-${out.length}`}>
            {renderMarkdownInline(line)}
          </p>
        );
      }
    }
    flush();
    return out;
  }, [text]);
  return <div className="msg-md">{blocks}</div>;
}

function TypingDots() {
  return (
    <span className="typing-dots" aria-label="Lia está digitando">
      <span /><span /><span />
    </span>
  );
}

function AvatarLia() {
  return (
    <div className="avatar avatar-lia" title="Lia">
      <span className="avatar-letter">L</span>
    </div>
  );
}

function AvatarUser() {
  return <div className="avatar avatar-user" title="Você">🙂</div>;
}

export default function Chat() {
  const [sessionId, setSessionId] = useState(getOuCriarSessionId);
  const [mensagens, setMensagens] = useState([]);
  const [input, setInput] = useState("");
  const [carregando, setCarregando] = useState(false);
  const [erroConexao, setErroConexao] = useState(false);
  const fimRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    getSaudacao()
      .then((m) => {
        setMensagens([{ role: "ai", text: m }]);
        setErroConexao(false);
      })
      .catch(() => {
        setErroConexao(true);
        setMensagens([
          { role: "ai", text: "Olá! Sou a Lia 🍽️\n\n_Backend offline — inicie o servidor FastAPI para conversarmos._" },
        ]);
      });
  }, []);

  useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens, carregando]);

  useEffect(() => {
    if (!carregando) inputRef.current?.focus();
  }, [carregando]);

  async function enviar(textoBruto) {
    const texto = (textoBruto ?? input).trim();
    if (!texto || carregando) return;
    setInput("");
    setMensagens((prev) => [...prev, { role: "user", text: texto }]);
    setCarregando(true);
    try {
      const data = await enviarMensagem(sessionId, texto);
      setMensagens((prev) => [
        ...prev,
        { role: "ai", text: data.resposta, foraDeEscopo: data.fora_de_escopo },
      ]);
      setErroConexao(false);
    } catch {
      setErroConexao(true);
      setMensagens((prev) => [
        ...prev,
        {
          role: "ai",
          text: "⚠️ Não consegui me conectar agora. Verifique se o backend e o Ollama estão rodando.",
        },
      ]);
    } finally {
      setCarregando(false);
    }
  }

  async function novaConversa() {
    // Tenta apagar a sessão no backend; logamos se falhar pra não cair em
    // silêncio (caso de antes onde "Nova Conversa" parecia funcionar mas o
    // histórico continuava acumulando).
    await limparConversa(sessionId).catch((err) => {
      console.warn("[novaConversa] DELETE /chat falhou — gerando novo session_id mesmo assim:", err);
    });
    // Gera novo session_id e persiste. Garante conversa limpa mesmo se o DELETE
    // acima falhou — o backend cria histórico fresh para um id desconhecido.
    const novoId = gerarSessionId();
    localStorage.setItem("lia_session_id", novoId);
    setSessionId(novoId);

    const m = await getSaudacao().catch(() => "Conversa reiniciada! 🍽️");
    setMensagens([{ role: "ai", text: m }]);
  }

  function onKey(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      enviar();
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
            <a
              className="btn-ghost"
              href="/mapa-conceitual.html"
              target="_blank"
              rel="noopener noreferrer"
              title="Mapa conceitual do projeto"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              </svg>
              Sobre o projeto
            </a>
            <button className="btn-ghost" onClick={novaConversa} disabled={carregando}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M3 12a9 9 0 1 0 9-9" /><path d="M3 4v5h5" />
              </svg>
              Nova conversa
            </button>
          </div>
        </header>

        <main className="messages">
          {mensagens.map((msg, i) => (
            <div key={i} className={`row row-${msg.role}`}>
              {msg.role === "ai" && <AvatarLia />}
              <div className={`bubble bubble-${msg.role}${msg.foraDeEscopo ? " bubble-warning" : ""}`}>
                <MarkdownMessage text={msg.text} />
                {msg.foraDeEscopo && <span className="badge">fora de escopo</span>}
              </div>
              {msg.role === "user" && <AvatarUser />}
            </div>
          ))}

          {carregando && (
            <div className="row row-ai">
              <AvatarLia />
              <div className="bubble bubble-ai bubble-typing">
                <TypingDots />
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
            <button
              className="btn-send"
              onClick={() => enviar()}
              disabled={carregando || !input.trim()}
              aria-label="Enviar"
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                <path d="M22 2L11 13" /><path d="M22 2l-7 20-4-9-9-4 20-7z" />
              </svg>
            </button>
          </div>
          <p className="composer-hint">
            Enter para enviar · Shift+Enter para nova linha · Lia só responde sobre o cardápio
          </p>
        </footer>
      </div>
    </div>
  );
}
