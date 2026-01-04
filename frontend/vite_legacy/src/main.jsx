// frontend/src/main.jsx
import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App.jsx";

const el = document.getElementById("root");
if (!el) throw new Error('Missing mount element: <div id="root"></div>');

ReactDOM.createRoot(el).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
