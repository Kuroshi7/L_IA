import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { adminGetDesperdicio } from "../../lib/api";
import { addDaysISO, fmtISO, rotuloCurto } from "../../lib/datas";
import AppShell from "../../shell/AppShell";
import { Aviso, Cabecalho, Pagina, Silhueta, Vazio } from "../../ui/Pagina";
import { mensagemAdmin } from "../../lib/mensagens";
import type { ClassificacaoDesperdicio, DesperdicioRelatorio } from "../../types";

const PERIODOS = [7, 14, 30] as const;

const CLASSIFICACAO_LABEL: Record<ClassificacaoDesperdicio, string> = {
  otimo: "Ótimo",
  bom: "Bom",
  atencao: "Atenção",
  critico: "Crítico",
};

const num = (v: number, casas = 0) =>
  v.toLocaleString("pt-BR", { minimumFractionDigits: casas, maximumFractionDigits: casas });

export default function DesperdicioDashboard() {
  const unidadeId = Number(useParams().unidadeId);
  const [periodo, setPeriodo] = useState<(typeof PERIODOS)[number]>(14);
  const [rel, setRel] = useState<DesperdicioRelatorio | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    const hoje = fmtISO(new Date());
    const de = addDaysISO(hoje, -(periodo - 1));
    setCarregando(true);
    setErro(null);
    adminGetDesperdicio(unidadeId, de, hoje)
      .then(setRel)
      .catch((e: Error) => { console.error("falha ao carregar desperdício", e); setErro(mensagemAdmin(e)); })
      .finally(() => setCarregando(false));
  }, [unidadeId, periodo]);

  const dias = rel?.dias ?? [];
  const top = rel?.top_desperdicados ?? [];
  const maxResto = Math.max(...dias.map((d) => d.resto_g), 0);
  const semRegistros = !carregando && !erro && rel !== null && rel.refeicoes === 0;
  // Com muitos dias, rotular todos os eixos vira ruído — mostra 1 a cada N.
  const labelStep = Math.max(1, Math.ceil(dias.length / 10));

  return (
    <AppShell area="gestor" unidadeId={unidadeId} titulo="Desperdício">
      <Pagina>
        <Cabecalho
          titulo="Desperdício"
          apoio={
            rel
              ? `Resto-ingesta de ${rotuloCurto(rel.de)} a ${rotuloCurto(rel.ate)}.`
              : "Quanto do que foi servido volta no prato."
          }
          acoes={
            <div className="barra-ferramentas" role="group" aria-label="Período do relatório">
              {PERIODOS.map((p) => (
                <button
                  key={p}
                  className={`pilula${periodo === p ? " pilula--ativa" : ""}`}
                  aria-pressed={periodo === p}
                  onClick={() => setPeriodo(p)}
                >
                  {p} dias
                </button>
              ))}
            </div>
          }
        />

        {erro && <Aviso tom="erro" titulo="Não deu certo">{erro}</Aviso>}

        {carregando && <Silhueta linhas={2} altura={110} />}

        {semRegistros && (
          <Vazio
            titulo="Nenhum registro no período"
            acao={
              <Link className="btn btn--contorno" to={`/admin/u/${unidadeId}/cardapio`}>
                Conferir o cardápio
              </Link>
            }
          >
            O número só existe quando as pessoas contam à Lia o que comeram e o que sobrou no prato.
            Sem registro não há resto-ingesta para medir.
          </Vazio>
        )}

        {!carregando && rel && !semRegistros && (
          <>
            <section className="mosaico">
              <div className={`numero numero--${rel.classificacao}`}>
                <span className="numero__rotulo">Índice resto-ingesta</span>
                <span className="numero__valor">{num(rel.indice_resto_perc, 1)}%</span>
                <span className="numero__apoio">{CLASSIFICACAO_LABEL[rel.classificacao]}</span>
              </div>
              <div className="numero">
                <span className="numero__rotulo">Refeições registradas</span>
                <span className="numero__valor">{num(rel.refeicoes)}</span>
                <span className="numero__apoio">no período</span>
              </div>
              <div className="numero">
                <span className="numero__rotulo">Resto por refeição</span>
                <span className="numero__valor">{num(rel.resto_per_capita_g)} g</span>
                <span className="numero__apoio">média por prato</span>
              </div>
              <div className="numero">
                <span className="numero__rotulo">Resto total</span>
                <span className="numero__valor">{num(rel.resto_kcal)} kcal</span>
                <span className="numero__apoio">{num(rel.resto_g)} g descartados</span>
              </div>
            </section>

            {dias.length > 0 && maxResto > 0 && (
              <section className="bloco">
                <div>
                  <h2 className="bloco__titulo">Resto por dia</h2>
                  <p className="bloco__apoio">Em gramas. Passe o cursor para ver o dia e o número de refeições.</p>
                </div>
                <div className="barras">
                  {dias.map((d, i) => (
                    <div
                      className="barras__col"
                      key={d.data}
                      title={`${rotuloCurto(d.data)} · ${num(d.resto_g)} g de resto · ${d.refeicoes} ${d.refeicoes === 1 ? "refeição" : "refeições"}`}
                    >
                      <div className="barras__trilho">
                        {/* Rótulo só no pico: um número em cada barra vira ruído. */}
                        {d.resto_g === maxResto && <span className="barras__valor">{num(d.resto_g)}</span>}
                        <div
                          className="barras__barra"
                          style={{ height: `${Math.max((d.resto_g / maxResto) * 85, d.resto_g > 0 ? 2 : 0)}%` }}
                        />
                      </div>
                      <span className="barras__rotulo">{i % labelStep === 0 ? rotuloCurto(d.data) : "\u00a0"}</span>
                    </div>
                  ))}
                </div>
              </section>
            )}

            {top.length > 0 && (
              <section className="bloco bloco--plano">
                <div>
                  <h2 className="bloco__titulo">O que mais volta no prato</h2>
                  <p className="bloco__apoio">
                    Item que aparece muito aqui costuma ser questão de porcionamento ou de aceitação da receita.
                  </p>
                </div>
                <div className="tabela-caixa">
                  <table className="tabela">
                    <thead>
                      <tr>
                        <th>Alimento</th>
                        <th className="celula-num">Ocorrências</th>
                        <th className="celula-num">Resto (g)</th>
                        <th className="celula-num">Resto (kcal)</th>
                      </tr>
                    </thead>
                    <tbody>
                      {top.map((t) => (
                        <tr key={t.alimento}>
                          <td>{t.alimento}</td>
                          <td className="celula-num">{num(t.ocorrencias)}</td>
                          <td className="celula-num">{num(t.resto_g)}</td>
                          <td className="celula-num">{num(t.resto_kcal)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}
          </>
        )}

        {!carregando && rel && (
          <p className="campo-ajuda">
            Índice de resto-ingesta = resto ÷ total servido. Referência para UANs: até 10% é bom; acima disso,
            vale revisar porcionamento ou aceitação do cardápio.
          </p>
        )}
      </Pagina>
    </AppShell>
  );
}
