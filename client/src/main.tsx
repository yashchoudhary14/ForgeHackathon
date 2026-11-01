import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Provider } from "./context";
import { ErrorBoundary } from "./components";
import AppRoutes from "./Shell";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <ErrorBoundary>
      <BrowserRouter>
        <Provider>
          <AppRoutes />
        </Provider>
      </BrowserRouter>
    </ErrorBoundary>
  </StrictMode>,
);