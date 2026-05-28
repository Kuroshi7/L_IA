import { Link } from "react-router-dom";

// Scaffold — o CRUD completo de cadastro de usuário (restrições, peso, altura,
// idade → IMC e meta calórica) entra nas próximas fases. O schema já existe no backend.
export default function Cadastro() {
  return (
    <div className="app">
      <div className="chat-card selector-card">
        <header className="chat-header">
          <div className="brand">
            <div className="avatar avatar-lia"><span className="avatar-letter">L</span></div>
            <div className="brand-text">
              <h1 className="brand-name">Cadastro</h1>
              <span className="status status-on"><span className="status-dot" />em breve</span>
            </div>
          </div>
          <div className="header-actions">
            <Link className="btn-ghost" to="/">Início</Link>
          </div>
        </header>
        <main className="messages selector-body">
          <p className="msg-p">
            Aqui o usuário cadastrará <strong>nome, restrições, preferências, peso, altura e idade</strong> —
            usados para calcular IMC e a meta calórica (Mifflin-St Jeor) que personaliza as recomendações.
          </p>
          <p className="msg-p">Funcionalidade planejada para a próxima fase; a fundação (schema e perfil) já existe no backend.</p>
        </main>
      </div>
    </div>
  );
}
