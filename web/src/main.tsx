import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { useEffect, useState } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useParams } from "react-router-dom";
import Admin from "./pages/Admin";
import Home from "./pages/Home";
import Participant from "./pages/Participant";
import { checkAdminEntry } from "./api";
import "./styles.css";

function AdminEntry() {
  const { adminEntry = "" } = useParams<{ adminEntry: string }>();
  const [allowed, setAllowed] = useState<boolean | null>(null);

  useEffect(() => {
    checkAdminEntry(adminEntry).then(() => setAllowed(true)).catch(() => setAllowed(false));
  }, [adminEntry]);

  if (allowed === null) return <p className="loading">正在验证入口……</p>;
  if (!allowed) return <Navigate to="/" replace />;
  return <Admin adminEntry={adminEntry} />;
}

function App() {
  return (
    <BrowserRouter>
      <main className="app-shell">
        <header className="topbar">
          <Link to="/" className="brand-lockup">
            <span className="brand-mark">C</span>
            <span>cutestar</span>
          </Link>
        </header>
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/e/:code" element={<Participant />} />
          <Route path={`/admin`} element={<Navigate to="/" replace />} />
          <Route path="/:adminEntry" element={<AdminEntry />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
    </BrowserRouter>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
