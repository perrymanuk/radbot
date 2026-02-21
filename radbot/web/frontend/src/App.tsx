import ChatPage from "./pages/ChatPage";
import AdminPage from "./pages/AdminPage";
import ErrorBoundary from "./components/ErrorBoundary";

export default function App() {
  const isAdmin = window.location.pathname.startsWith("/admin");

  return (
    <ErrorBoundary>
      {isAdmin ? <AdminPage /> : <ChatPage />}
    </ErrorBoundary>
  );
}
