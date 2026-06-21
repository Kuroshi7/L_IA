import { createBrowserRouter } from "react-router-dom";
import UnidadeSelector from "./routes/UnidadeSelector";
import ChatRoute from "./routes/ChatRoute";
import Cadastro from "./routes/Cadastro";
import Admin from "./routes/Admin";
import CardapioEditor from "./routes/admin/CardapioEditor";
import AlimentosCatalogo from "./routes/admin/AlimentosCatalogo";

export const router = createBrowserRouter([
  { path: "/", element: <UnidadeSelector /> },
  { path: "/u/:unidadeId/chat", element: <ChatRoute /> },
  { path: "/cadastro", element: <Cadastro /> },
  { path: "/admin", element: <Admin /> },
  { path: "/admin/u/:unidadeId/cardapio", element: <CardapioEditor /> },
  { path: "/admin/u/:unidadeId/alimentos", element: <AlimentosCatalogo /> },
]);
