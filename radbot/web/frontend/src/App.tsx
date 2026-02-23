import ChatPage from "./pages/ChatPage";
import AdminPage from "./pages/AdminPage";
import TerminalPage from "./pages/TerminalPage";
import ErrorBoundary from "./components/ErrorBoundary";

export default function App() {
  const path = window.location.pathname;
  const isAdmin = path.startsWith("/admin");
  const isTerminal = path.startsWith("/terminal");

  return (
    <ErrorBoundary>
      {isAdmin ? <AdminPage /> : isTerminal ? <TerminalPage /> : <ChatPage />}
    </ErrorBoundary>
  );
}
