import React from "react";
import ReactDOM from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { router } from "./App";
import { marca, aplicarTema } from "./brand";
import { aplicarPreferencia, lerPreferencia } from "./shell/tema";
import "./styles/index.css";

// Tema e marca antes do primeiro render: o index.html já aplicou o tema para
// não piscar branco, mas quem manda a partir daqui é o app.
aplicarPreferencia(lerPreferencia());
aplicarTema(marca.tema);
document.title = `${marca.assistente} · ${marca.produto}`;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
