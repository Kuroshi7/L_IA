import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  adminCopiarSemana,
  adminGetCardapioSemana,
  adminListarAlimentos,
  adminListarUnidades,
  adminSetCardapioItens,
} from "../../lib/api";
import { addDaysISO, fmtISO, mondayISO, parseISO, rotuloCurto } from "../../lib/datas";
import AppShell from "../../shell/AppShell";
import { Aviso, Cabecalho, Pagina, Silhueta } from "../../ui/Pagina";
import { mensagemAdmin } from "../../lib/mensagens";
import Icone from "../../ui/Icone";
import type { Alimento, CardapioDia, CardapioItemInput, CardapioSemana, Unidade } from "../../types";

function itensDe(dia: CardapioDia): CardapioItemInput[] {
  return dia.pratos.map((p) => ({ alimento_id: p.id, is_proteina_do_dia: p.is_proteina_do_dia }));
}

export default function CardapioEditor() {
  const unidadeId = Number(useParams().unidadeId);
  const navigate = useNavigate();
  const [inicio, setInicio] = useState(() => mondayISO(new Date()));
  const [semana, setSemana] = useState<CardapioSemana | null>(null);
  const [catalogo, setCatalogo] = useState<Alimento[]>([]);
  const [unidades, setUnidades] = useState<Unidade[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [copiaDestino, setCopiaDestino] = useState("");

  useEffect(() => {
    adminListarUnidades().then(setUnidades).catch(() => setUnidades([]));
  }, []);

  const carregar = useCallback(() => {
    setCarregando(true);
    setErro(null);
    Promise.all([adminGetCardapioSemana(unidadeId, inicio), adminListarAlimentos(unidadeId)])
      .then(([sem, cat]) => {
        setSemana(sem);
        setCatalogo(cat);
      })
      .catch((e: Error) => { console.error("falha ao carregar semana", e); setErro(mensagemAdmin(e)); })
      .finally(() => setCarregando(false));
  }, [unidadeId, inicio]);

  useEffect(() => {
    carregar();
  }, [carregar]);

  function salvarDia(diaIdx: number, itens: CardapioItemInput[]) {
    if (!semana) return;
    const dia = semana.dias[diaIdx];
    setSalvando(true);
    setErro(null);
    adminSetCardapioItens(unidadeId, dia.data, itens)
      .then((atualizado) => {
        setSemana((prev) => {
          if (!prev) return prev;
          const dias = [...prev.dias];
          dias[diaIdx] = atualizado;
          return { ...prev, dias };
        });
      })
      .catch((e: Error) => { console.error("falha ao salvar", e); setErro(mensagemAdmin(e)); })
      .finally(() => setSalvando(false));
  }

  function adicionar(diaIdx: number, alimentoId: number) {
    if (!alimentoId || !semana) return;
    const dia = semana.dias[diaIdx];
    salvarDia(diaIdx, [...itensDe(dia), { alimento_id: alimentoId, is_proteina_do_dia: false }]);
  }

  function remover(diaIdx: number, alimentoId: number) {
    if (!semana) return;
    const dia = semana.dias[diaIdx];
    salvarDia(diaIdx, itensDe(dia).filter((i) => i.alimento_id !== alimentoId));
  }

  function alternarProteina(diaIdx: number, alimentoId: number) {
    if (!semana) return;
    const dia = semana.dias[diaIdx];
    const atual = dia.pratos.find((p) => p.id === alimentoId)?.is_proteina_do_dia ?? false;
    salvarDia(
      diaIdx,
      dia.pratos.map((p) => ({ alimento_id: p.id, is_proteina_do_dia: p.id === alimentoId ? !atual : false })),
    );
  }

  // Copia a semana atual para a semana (segunda-feira) de destino, com confirmação.
  function copiarPara(destino: string) {
    if (destino === inicio) {
      setErro("A semana de destino é a mesma que está sendo editada.");
      return;
    }
    const ok = window.confirm(
      `Copiar a semana de ${rotuloCurto(inicio)} para a semana de ${rotuloCurto(destino)}?\n\n` +
        "Isso SUBSTITUI os itens já cadastrados nos dias da semana de destino.",
    );
    if (!ok) return;
    setSalvando(true);
    setErro(null);
    adminCopiarSemana(unidadeId, inicio, destino)
      .then(() => setInicio(destino))
      .catch((e: Error) => { console.error("falha ao salvar", e); setErro(mensagemAdmin(e)); })
      .finally(() => setSalvando(false));
  }

  function copiarProximaSemana() {
    copiarPara(addDaysISO(inicio, 7));
  }

  function copiarParaDestino() {
    if (!copiaDestino) return;
    copiarPara(mondayISO(parseISO(copiaDestino)));
  }

  function irParaData(iso: string) {
    if (!iso) return;
    setInicio(mondayISO(parseISO(iso)));
  }

  function trocarUnidade(id: number) {
    if (id && id !== unidadeId) navigate(`/admin/u/${id}/cardapio`);
  }

  const hoje = fmtISO(new Date());

  return (
    <AppShell
      area="gestor"
      unidadeId={unidadeId}
      titulo="Cardápio da semana"
      acoes={
        unidades.length > 1 ? (
          <select
            className="selecao"
            style={{ width: "auto", maxWidth: 200 }}
            value={unidadeId}
            onChange={(e) => trocarUnidade(Number(e.target.value))}
            aria-label="Trocar de unidade"
          >
            {unidades.map((u) => (
              <option key={u.id} value={u.id}>{u.nome}{u.ativo ? "" : " (inativa)"}</option>
            ))}
          </select>
        ) : undefined
      }
    >
      <Pagina>
        <Cabecalho
          titulo={`Semana de ${rotuloCurto(inicio)}`}
          apoio="O que estiver aqui é o que a Lia oferece ao cliente naquele dia. A estrela marca a proteína do dia — uma por dia."
          acoes={
            <>
              <button className="btn btn--fantasma btn--mini" onClick={() => setInicio(addDaysISO(inicio, -7))}>
                <Icone nome="esquerda" tam={16} /> Anterior
              </button>
              <button className="btn btn--contorno btn--mini" onClick={() => setInicio(mondayISO(new Date()))}>
                Esta semana
              </button>
              <button className="btn btn--fantasma btn--mini" onClick={() => setInicio(addDaysISO(inicio, 7))}>
                Próxima <Icone nome="direita" tam={16} />
              </button>
            </>
          }
        />

        <section className="bloco">
          <div className="barra-ferramentas">
            <div className="campo">
              <label className="campo-rotulo" htmlFor="ir-para-data">Ir para a semana de</label>
              <input
                id="ir-para-data"
                className="entrada"
                style={{ width: "auto" }}
                type="date"
                value={inicio}
                onChange={(e) => irParaData(e.target.value)}
              />
            </div>

            <div className="campo">
              <label className="campo-rotulo" htmlFor="copia-destino">Copiar esta semana para</label>
              <input
                id="copia-destino"
                className="entrada"
                style={{ width: "auto" }}
                type="date"
                value={copiaDestino}
                onChange={(e) => setCopiaDestino(e.target.value)}
              />
            </div>
            <button className="btn btn--contorno" disabled={salvando || !copiaDestino} onClick={copiarParaDestino}>
              Copiar
            </button>

            <span className="barra-ferramentas__espaco" />

            <button className="btn btn--primario" disabled={salvando} onClick={copiarProximaSemana}>
              Repetir na próxima semana
            </button>
          </div>

          {copiaDestino && (
            <p className="campo-ajuda">
              Destino: semana de {rotuloCurto(mondayISO(parseISO(copiaDestino)))} — os itens já cadastrados nesses dias
              serão substituídos.
            </p>
          )}
        </section>

        {erro && <Aviso tom="erro" titulo="Não deu certo">{erro}</Aviso>}

        {carregando && <Silhueta linhas={2} altura={140} />}

        {semana && catalogo.length === 0 && (
          <Aviso
            tom="atencao"
            titulo="O catálogo desta unidade está vazio"
            acao={
              <Link className="btn btn--contorno btn--mini" to={`/admin/u/${unidadeId}/alimentos`}>
                Cadastrar alimentos
              </Link>
            }
          >
            Sem alimentos cadastrados não há o que colocar no cardápio.
          </Aviso>
        )}

        {semana && (
          <div className="semana">
            {semana.dias.map((dia, idx) => {
              const presentes = new Set(dia.pratos.map((p) => p.id));
              const disponiveis = catalogo.filter((a) => a.ativo && !presentes.has(a.id));
              return (
                <section className={`dia${dia.data === hoje ? " dia--hoje" : ""}`} key={dia.data}>
                  <header className="dia__cabecalho">
                    <span className="dia__nome">{dia.dia_semana}</span>
                    <span className="dia__data">
                      {rotuloCurto(dia.data)}{dia.data === hoje ? " · hoje" : ""}
                    </span>
                  </header>

                  <div className="dia__itens">
                    {dia.pratos.length === 0 && <p className="dia__vazio">Nada servido</p>}
                    {dia.pratos.map((p) => (
                      <div className={`item${p.ativo ? "" : " item--inativo"}`} key={p.id}>
                        <button
                          className={`estrela${p.is_proteina_do_dia ? " estrela--ligada" : ""}`}
                          title="Proteína do dia — uma por dia"
                          aria-label={`${p.is_proteina_do_dia ? "Desmarcar" : "Marcar"} ${p.nome} como proteína do dia`}
                          aria-pressed={p.is_proteina_do_dia}
                          disabled={salvando}
                          onClick={() => alternarProteina(idx, p.id)}
                        >
                          <Icone nome="estrela" tam={15} />
                        </button>
                        <span className="item__nome">
                          {p.nome}
                          {!p.ativo && <em className="item__tag"> inativo</em>}
                        </span>
                        <button
                          className="remove"
                          aria-label={`Tirar ${p.nome} do cardápio`}
                          disabled={salvando}
                          onClick={() => remover(idx, p.id)}
                        >
                          <Icone nome="remover" tam={14} />
                        </button>
                      </div>
                    ))}
                  </div>

                  <select
                    className="selecao"
                    value=""
                    aria-label={`Adicionar alimento em ${dia.dia_semana}`}
                    disabled={salvando || disponiveis.length === 0}
                    onChange={(e) => adicionar(idx, Number(e.target.value))}
                  >
                    <option value="">
                      {disponiveis.length === 0 ? "nada disponível" : "adicionar alimento…"}
                    </option>
                    {disponiveis.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.categoria ? `${a.categoria} · ` : ""}{a.nome}
                      </option>
                    ))}
                  </select>
                </section>
              );
            })}
          </div>
        )}
      </Pagina>
    </AppShell>
  );
}
