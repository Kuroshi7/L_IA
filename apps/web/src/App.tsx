import { Navigate, Outlet, createBrowserRouter } from "react-router-dom";
import { PerfilProvider } from "./shell/PerfilContexto";
import Entrada from "./routes/Entrada";
import UnidadeSelector from "./routes/UnidadeSelector";
import ChatRoute from "./routes/ChatRoute";
import Perfil from "./routes/Perfil";
import Ranking from "./routes/Ranking";
import NotFound from "./routes/NotFound";
import Admin from "./routes/Admin";
import CardapioEditor from "./routes/admin/CardapioEditor";
import AlimentosCatalogo from "./routes/admin/AlimentosCatalogo";
import UnidadesAdmin from "./routes/admin/UnidadesAdmin";
import UsuariosAdmin from "./routes/admin/UsuariosAdmin";
import DesperdicioDashboard from "./routes/admin/DesperdicioDashboard";

/** Provedores que valem para o app inteiro. Ficam numa rota-mãe para que tanto
 *  o shell quanto as telas leiam o mesmo estado — sem duas buscas do mesmo dado. */
function Raiz() {
  return (
    <PerfilProvider>
      <Outlet />
    </PerfilProvider>
  );
}

export const router = createBrowserRouter([
  {
    element: <Raiz />,
    errorElement: <NotFound />,
    children: [
      // A raiz não é mais um seletor: manda direto para a conversa quando dá.
      { path: "/", element: <Entrada /> },
      { path: "/unidades", element: <UnidadeSelector /> },

      { path: "/u/:unidadeId/chat", element: <ChatRoute /> },
      { path: "/u/:unidadeId/ranking", element: <Ranking /> },

      { path: "/perfil", element: <Perfil /> },
      // Endereço antigo da mesma tela — links já compartilhados continuam válidos.
      { path: "/cadastro", element: <Navigate to="/perfil" replace /> },

      { path: "/admin", element: <Admin /> },
      { path: "/admin/unidades", element: <UnidadesAdmin /> },
      { path: "/admin/usuarios", element: <UsuariosAdmin /> },
      { path: "/admin/u/:unidadeId/cardapio", element: <CardapioEditor /> },
      { path: "/admin/u/:unidadeId/alimentos", element: <AlimentosCatalogo /> },
      { path: "/admin/u/:unidadeId/desperdicio", element: <DesperdicioDashboard /> },

      { path: "*", element: <NotFound /> },
    ],
  },
]);
