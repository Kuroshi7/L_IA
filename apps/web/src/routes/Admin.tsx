import { Link } from "react-router-dom";

// Scaffold — a área de admin (cadastrar alimentos, montar o cardápio semanal por
// unidade, definir a proteína do dia, ver desperdício) entra nas próximas fases.
export default function Admin() {
  return (
    <div className="app">
      <div className="chat-card selector-card">
        <header className="chat-header">
          <div className="brand">
            <div className="avatar avatar-lia"><span className="avatar-letter">L</span></div>
            <div className="brand-text">
              <h1 className="brand-name">Admin</h1>
              <span className="status status-on"><span className="status-dot" />em breve</span>
            </div>
          </div>
          <div className="header-actions">
            <Link className="btn-ghost" to="/">Início</Link>
          </div>
        </header>
        <main className="messages selector-body">
          <p className="msg-p">
            Aqui o admin vai <strong>configurar o cardápio por unidade</strong>: cadastrar alimentos, montar o
            cardápio da semana (adicionar/remover por dia), definir a <strong>proteína do dia</strong> e
            acompanhar o <strong>controle de desperdício</strong>.
          </p>
          <p className="msg-p">Funcionalidade planejada para a próxima fase; o schema (unidades, alimentos, cardápios) já existe no backend.</p>
        </main>
      </div>
    </div>
  );
}
