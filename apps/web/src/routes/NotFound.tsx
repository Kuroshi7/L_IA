import { Link, isRouteErrorResponse, useRouteError } from "react-router-dom";

// Usada tanto como rota catch-all (path "*") quanto como errorElement do router.
export default function NotFound() {
  const error = useRouteError();
  const ehErroInesperado = error !== undefined && !isRouteErrorResponse(error);

  return (
    <div className="app">
      <div className="chat-card selector-card">
        <header className="chat-header">
          <div className="brand">
            <div className="avatar avatar-lia"><span className="avatar-letter">L</span></div>
            <div className="brand-text">
              <h1 className="brand-name">{ehErroInesperado ? "Algo deu errado" : "Página não encontrada"}</h1>
              <span className="status status-off"><span className="status-dot" />{ehErroInesperado ? "erro inesperado" : "404"}</span>
            </div>
          </div>
        </header>
        <main className="messages selector-body">
          <p className="msg-p">
            {ehErroInesperado
              ? "Ocorreu um erro inesperado ao carregar esta página. Tente novamente."
              : "O endereço que você tentou acessar não existe (ou mudou de lugar)."}
          </p>
          <p className="msg-p">
            <Link to="/">← Voltar para o início</Link>
          </p>
        </main>
      </div>
    </div>
  );
}
