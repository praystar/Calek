import { useState, useEffect } from "react";
import { BrowserRouter as Router, Routes, Route, NavLink } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { Moon, Sun, PenTool } from "lucide-react";
import CorpusPage from "./pages/CorpusPage";
import VoicePage from "./pages/VoicePage";
import ChatPage from "./pages/ChatPage";
import "./styles/global.css";

export default function App() {
  const [dark, setDark] = useState(() => localStorage.getItem("theme") === "dark");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", dark ? "dark" : "light");
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  return (
    <Router>
      <div className="app">
        <nav className="navbar">
          <div className="nav-brand">
            <PenTool size={22} strokeWidth={1.5} />
            <span>HandScribe</span>
          </div>
          <div className="nav-links">
            <NavLink to="/" end className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
              Corpus
            </NavLink>
            <NavLink to="/voice" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
              Voice
            </NavLink>
            <NavLink to="/chat" className={({ isActive }) => isActive ? "nav-link active" : "nav-link"}>
              AI Chat
            </NavLink>
          </div>
          <button className="theme-btn" onClick={() => setDark(d => !d)} aria-label="Toggle theme">
            {dark ? <Sun size={18} /> : <Moon size={18} />}
          </button>
        </nav>

        <main className="main-content">
          <Routes>
            <Route path="/" element={<CorpusPage />} />
            <Route path="/voice" element={<VoicePage />} />
            <Route path="/chat" element={<ChatPage />} />
          </Routes>
        </main>

        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              background: "var(--surface)",
              color: "var(--text-primary)",
              border: "1px solid var(--border)",
              borderRadius: "10px",
              fontSize: "14px",
            },
          }}
        />
      </div>
    </Router>
  );
}
