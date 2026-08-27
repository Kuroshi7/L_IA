import { useEffect, useState } from "react";
import { adminListarUnidades, adminListarUsuarios } from "../../lib/api";
import AppShell from "../../shell/AppShell";
import { Aviso, Cabecalho, Pagina, Silhueta, Vazio } from "../../ui/Pagina";
import { mensagemAdmin } from "../../lib/mensagens";
import type { AdminUsuario, Unidade } from "../../types";

const csv = (a: string[] | null | undefined) => {
  const arr = a ?? [];
  return arr.length ? arr.join(", ") : "—";
};

export default function UsuariosAdmin() {
  const [usuarios, setUsuarios] = useState<AdminUsuario[]>([]);
  const [unidades, setUnidades] = useState<Unidade[]>([]);
  const [filtroUnidade, setFiltroUnidade] = useState("");
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState<string | null>(null);

  useEffect(() => {
    adminListarUnidades().then(setUnidades).catch(() => setUnidades([]));
  }, []);

  useEffect(() => {
    setCarregando(true);
    setErro(null);
    adminListarUsuarios(filtroUnidade ? Number(filtroUnidade) : undefined)
      .then(setUsuarios)
      .catch((e: Error) => { console.error("falha ao listar usuários", e); setErro(mensagemAdmin(e)); })
      .finally(() => setCarregando(false));
  }, [filtroUnidade]);

  return (
    <AppShell area="gestor" titulo="Usuários">
      <Pagina>
        <Cabecalho
          titulo="Usuários"
          apoio="Quem criou perfil e como vem usando. Pontos e sequência vêm dos registros de refeição feitos na conversa."
          acoes={
            <div className="campo">
              <label className="campo-rotulo" htmlFor="filtro-unidade">Unidade</label>
              <select
                id="filtro-unidade"
                className="selecao"
                style={{ width: "auto", minWidth: 200 }}
                value={filtroUnidade}
                onChange={(e) => setFiltroUnidade(e.target.value)}
              >
                <option value="">Todas</option>
                {unidades.map((u) => (
                  <option key={u.id} value={u.id}>{u.nome}</option>
                ))}
              </select>
            </div>
          }
        />

        {erro && <Aviso tom="erro" titulo="Não deu certo">{erro}</Aviso>}

        {carregando && <Silhueta linhas={4} altura={44} />}

        {!carregando && !erro && usuarios.length === 0 && (
          <Vazio titulo={`Nenhum usuário${filtroUnidade ? " nesta unidade" : ""}`}>
            Os perfis aparecem aqui assim que as pessoas se cadastram pelo chat.
          </Vazio>
        )}

        {usuarios.length > 0 && (
          <>
            <p className="campo-ajuda">
              {usuarios.length} {usuarios.length === 1 ? "pessoa" : "pessoas"}
            </p>
            <div className="tabela-caixa">
              <table className="tabela">
                <thead>
                  <tr>
                    <th>Nome</th>
                    <th>Restrições</th>
                    <th>Alergias</th>
                    <th className="celula-num">Pontos</th>
                    <th className="celula-num">Nível</th>
                    <th className="celula-num">Sequência</th>
                    <th className="celula-num">Registros</th>
                  </tr>
                </thead>
                <tbody>
                  {usuarios.map((u) => (
                    <tr key={u.id}>
                      <td>{u.nome}</td>
                      <td>{csv(u.restricoes)}</td>
                      <td>{csv(u.alergias)}</td>
                      <td className="celula-num">{u.pontos.toLocaleString("pt-BR")}</td>
                      <td className="celula-num">{u.nivel}</td>
                      <td className="celula-num">{u.streak_dias > 0 ? `${u.streak_dias} d` : "—"}</td>
                      <td className="celula-num">{u.registros_consumo}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </Pagina>
    </AppShell>
  );
}
