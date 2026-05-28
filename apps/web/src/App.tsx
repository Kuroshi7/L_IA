import { createBrowserRouter } from "react-router-dom";
import UnidadeSelector from "./routes/UnidadeSelector";
import ChatRoute from "./routes/ChatRoute";
import Cadastro from "./routes/Cadastro";
import Admin from "./routes/Admin";

export const router = createBrowserRouter([
  { path: "/", element: <UnidadeSelector /> },
  { path: "/u/:unidadeId/chat", element: <ChatRoute /> },
  { path: "/cadastro", element: <Cadastro /> },
  { path: "/admin", element: <Admin /> },
]);
