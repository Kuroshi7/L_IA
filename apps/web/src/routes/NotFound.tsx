import { Link, isRouteErrorResponse, useRouteError } from "react-router-dom";
import { marca } from "../brand";

/** Serve como rota curinga e como `errorElement` do router — por isso não usa
 *  o AppShell: se o que quebrou foi um provider, a moldura quebra junto. */
export default function NotFound() {
  const erro = useRouteError();
  const inesperado = erro !== undefined && !isRouteErrorResponse(erro);

  if (inesperado) console.error("erro não tratado na rota", erro);

  return (
    <div className="partida">
      <span className="marca__selo" aria-hidden="true">{marca.monograma}</span>
      <div>
        <h1 className="cabecalho__titulo">
          {inesperado ? "Algo saiu do lugar" : "Página não encontrada"}
        </h1>
        <p className="cabecalho__apoio" style={{ margin: "8px auto 0" }}>
          {inesperado
            ? "Não conseguimos montar esta tela. Recarregar costuma resolver."
            : "O endereço que você abriu não existe — ou mudou de lugar."}
        </p>
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        {inesperado && (
          <button className="btn btn--contorno" onClick={() => window.location.reload()}>
            Recarregar
          </button>
        )}
        <Link className="btn btn--primario" to="/">Voltar ao início</Link>
      </div>
    </div>
  );
}
