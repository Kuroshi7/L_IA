import { Outlet, createBrowserRouter } from "react-router-dom";
import UnidadeSelector from "./routes/UnidadeSelector";
import ChatRoute from "./routes/ChatRoute";
import Cadastro from "./routes/Cadastro";
import Ranking from "./routes/Ranking";
import NotFound from "./routes/NotFound";
import Admin from "./routes/Admin";
import CardapioEditor from "./routes/admin/CardapioEditor";
import AlimentosCatalogo from "./routes/admin/AlimentosCatalogo";
import UnidadesAdmin from "./routes/admin/UnidadesAdmin";
import UsuariosAdmin from "./routes/admin/UsuariosAdmin";
import DesperdicioDashboard from "./routes/admin/DesperdicioDashboard";

export const router = createBrowserRouter([
  {
    element: <Outlet />,
    errorElement: <NotFound />,
    children: [
      { path: "/", element: <UnidadeSelector /> },
      { path: "/u/:unidadeId/chat", element: <ChatRoute /> },
      { path: "/u/:unidadeId/ranking", element: <Ranking /> },
      { path: "/cadastro", element: <Cadastro /> },
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
