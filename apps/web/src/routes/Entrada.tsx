import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getUnidadeSalva, listarUnidadesCache, esquecerUnidades } from "../lib/api";
import { marca } from "../brand";
import { Aviso } from "../ui/Pagina";

/**
 * Porta de entrada.
 *
 * Antes, a raiz do app era um seletor de unidade — uma pergunta antes do
 * produto, todo santo dia, para quem almoça no mesmo lugar há dois anos. Um app
 * de conversa abre na conversa.
 *
 * A ordem é: unidade que a pessoa já usou → se a rede só tem uma, essa → senão,
 * escolher. A URL `/u/:id/chat` continua sendo a fonte da verdade; isto aqui só
 * decide para onde mandar quem chegou sem uma.
 */
export default function Entrada() {
  const navigate = useNavigate();
  const [falhou, setFalhou] = useState(false);

  const decidir = useCallback(() => {
    setFalhou(false);

    const salva = getUnidadeSalva();
    if (salva) {
      navigate(`/u/${salva}/chat`, { replace: true });
      return;
    }

    listarUnidadesCache()
      .then((us) => {
        const ativas = us.filter((u) => u.ativo);
        if (ativas.length === 1) navigate(`/u/${ativas[0].id}/chat`, { replace: true });
        else navigate("/unidades", { replace: true });
      })
      .catch((err) => {
        console.error("falha ao listar unidades", err);
        setFalhou(true);
      });
  }, [navigate]);

  useEffect(decidir, [decidir]);

  return (
    <div className="partida">
      <span className="marca__selo" aria-hidden="true">{marca.monograma}</span>
      {falhou ? (
        <Aviso
          tom="erro"
          titulo="Não consegui carregar as unidades"
          acao={
            <button
              className="btn btn--contorno btn--mini"
              onClick={() => { esquecerUnidades(); decidir(); }}
            >
              Tentar de novo
            </button>
          }
        >
          Verifique sua conexão. Se o problema continuar, avise o responsável pelo refeitório.
        </Aviso>
      ) : (
        <p className="partida__texto">Abrindo…</p>
      )}
    </div>
  );
}
