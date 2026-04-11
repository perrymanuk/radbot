import ChatPage from "./pages/ChatPage";
import AdminPage from "./pages/AdminPage";
import TerminalPage from "./pages/TerminalPage";
import NotificationsPage from "./pages/NotificationsPage";
import ErrorBoundary from "./components/ErrorBoundary";

export default function App() {
  const path = window.location.pathname;
  const isAdmin = path.startsWith("/admin");
  const isTerminal = path.startsWith("/terminal");
  const isNotifications = path.startsWith("/notifications");

  return (
    <ErrorBoundary>
      {isAdmin ? (
        <AdminPage />
      ) : isTerminal ? (
        <TerminalPage />
      ) : isNotifications ? (
        <NotificationsPage />
      ) : (
        <ChatPage />
      )}
    </ErrorBoundary>
  );
}
