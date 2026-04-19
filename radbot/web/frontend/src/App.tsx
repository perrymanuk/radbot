import { BrowserRouter, Route, Routes } from "react-router-dom";
import ChatPage from "./pages/ChatPage";
import AdminPage from "./pages/AdminPage";
import TerminalPage from "./pages/TerminalPage";
import NotificationsPage from "./pages/NotificationsPage";
import ProjectsPage from "./pages/ProjectsPage";
import ErrorBoundary from "./components/ErrorBoundary";

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/admin/*" element={<AdminPage />} />
          <Route path="/terminal/*" element={<TerminalPage />} />
          <Route path="/notifications" element={<NotificationsPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/:refCode" element={<ProjectsPage />} />
          <Route path="*" element={<ChatPage />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
