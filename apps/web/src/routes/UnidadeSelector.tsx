import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { esquecerUnidades, listarUnidadesCache, setUnidadeSalva } from "../lib/api";
import { marca } from "../brand";
import AppShell from "../shell/AppShell";
import { Aviso, Cabecalho, Pagina, Silhueta, Vazio } from "../ui/Pagina";
import Icone from "../ui/Icone";
import type { Unidade } from "../types";

export default function UnidadeSelector() {
  const [unidades, setUnidades] = useState<Unidade[] | null>(null);
  const [falhou, setFalhou] = useState(false);
  const navigate = useNavigate();

  const carregar = useCallback(() => {
    setFalhou(false);
    listarUnidadesCache()
      .then(setUnidades)
      .catch((err) => { console.error("falha ao listar unidades", err); setFalhou(true); });
  }, []);

  useEffect(carregar, [carregar]);

  function escolher(u: Unidade) {
    // Guardar aqui é o que faz a próxima visita abrir direto na conversa.
    setUnidadeSalva(u.id);
    navigate(`/u/${u.id}/chat`);
  }

  const ativas = unidades?.filter((u) => u.ativo) ?? [];

  return (
    <AppShell titulo="Escolher unidade">
      <Pagina>
        <Cabecalho
          titulo="Onde você vai comer?"
          apoio={`A ${marca.assistente} responde sobre o cardápio da unidade escolhida. Dá para trocar depois, pelo menu.`}
        />

        {falhou && (
          <Aviso
            tom="erro"
            titulo="Não consegui carregar as unidades"
            acao={
              <button className="btn btn--contorno btn--mini" onClick={() => { esquecerUnidades(); carregar(); }}>
                Tentar de novo
              </button>
            }
          >
            Verifique sua conexão e tente de novo.
          </Aviso>
        )}

        {!unidades && !falhou && <Silhueta linhas={3} altura={78} />}

        {unidades && ativas.length === 0 && (
          <Vazio titulo="Nenhuma unidade disponível">
            Nenhum refeitório foi liberado ainda. Fale com o responsável pela sua unidade.
          </Vazio>
        )}

        {ativas.length > 0 && (
          <div className="unidade-grid">
            {ativas.map((u) => (
              <button key={u.id} className="unidade-card" onClick={() => escolher(u)}>
                <Icone nome="unidade" />
                <span className="unidade-nome">{u.nome}</span>
                <span className="unidade-slug">{u.slug}</span>
              </button>
            ))}
          </div>
        )}
      </Pagina>
    </AppShell>
  );
}
