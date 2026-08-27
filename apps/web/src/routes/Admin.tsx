import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { esquecerUnidades, getAdminToken, listarUnidadesCache, setAdminToken } from "../lib/api";
import AppShell from "../shell/AppShell";
import { Aviso, Cabecalho, Pagina, Silhueta, Vazio } from "../ui/Pagina";
import Icone from "../ui/Icone";
import type { Unidade } from "../types";

export default function Admin() {
  const [unidades, setUnidades] = useState<Unidade[] | null>(null);
  const [falhou, setFalhou] = useState(false);
  const [token, setToken] = useState(getAdminToken());
  const [salvo, setSalvo] = useState(false);
  const navigate = useNavigate();

  const carregar = useCallback(() => {
    setFalhou(false);
    listarUnidadesCache()
      .then(setUnidades)
      .catch((err) => { console.error("falha ao listar unidades", err); setFalhou(true); });
  }, []);

  useEffect(carregar, [carregar]);

  function salvarToken() {
    setAdminToken(token);
    setSalvo(true);
    window.setTimeout(() => setSalvo(false), 1800);
  }

  return (
    <AppShell area="gestor" titulo="Gestão">
      <Pagina>
        <Cabecalho
          titulo="Gestão"
          apoio="Escolha a unidade para montar o cardápio, cuidar do catálogo de alimentos ou acompanhar o desperdício."
        />

        {/* O gate de admin ainda é um token único compartilhado (SEG-03 em
            docs/tickets-revisao-produto.md). Enquanto for assim, ele mora aqui,
            explicado — esconder não deixa mais seguro, só mais confuso. */}
        <section className="bloco">
          <div>
            <h2 className="bloco__titulo">Chave de acesso</h2>
            <p className="bloco__apoio">
              Fica guardada só neste navegador. Sem ela, as telas de gestão não conseguem ler nem gravar nada.
            </p>
          </div>
          <div className="barra-ferramentas">
            <div className="campo" style={{ flex: 1, minWidth: 240 }}>
              <label className="campo-rotulo" htmlFor="admin-token">Token de gestão</label>
              <input
                id="admin-token"
                className="entrada"
                type="password"
                placeholder="cole a chave recebida"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                autoComplete="off"
              />
            </div>
            <button className="btn btn--primario" onClick={salvarToken}>
              {salvo ? "Guardada" : "Guardar"}
            </button>
          </div>
        </section>

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

        <section className="bloco bloco--plano">
          <span className="secao-rotulo">Unidades</span>

          {!unidades && !falhou && <Silhueta linhas={2} altura={120} />}

          {unidades?.length === 0 && (
            <Vazio
              titulo="Nenhuma unidade cadastrada"
              acao={
                <button className="btn btn--primario" onClick={() => navigate("/admin/unidades")}>
                  Cadastrar a primeira
                </button>
              }
            >
              Uma unidade é um refeitório: tem cardápio, catálogo e clientes próprios.
            </Vazio>
          )}

          {unidades && unidades.length > 0 && (
            <div className="unidade-grid">
              {unidades.map((u) => (
                <div key={u.id} className="unidade-card">
                  <Icone nome="unidade" />
                  <span className="unidade-nome">
                    {u.nome}
                    {!u.ativo && <span className="etiqueta" style={{ marginLeft: 8 }}>inativa</span>}
                  </span>
                  <span className="unidade-slug">{u.slug}</span>
                  <div className="unidade-card__acoes">
                    <button className="btn btn--contorno btn--mini" onClick={() => navigate(`/admin/u/${u.id}/cardapio`)}>
                      Cardápio
                    </button>
                    <button className="btn btn--fantasma btn--mini" onClick={() => navigate(`/admin/u/${u.id}/alimentos`)}>
                      Alimentos
                    </button>
                    <button className="btn btn--fantasma btn--mini" onClick={() => navigate(`/admin/u/${u.id}/desperdicio`)}>
                      Desperdício
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </Pagina>
    </AppShell>
  );
}
