import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { useAuth } from "../features/auth/AuthContext";
import { NAV_AREAS, ROLE_LABELS } from "./nav";
import { Brand } from "../components/Brand";
import { AssistantPanel } from "../features/assistant/AssistantPanel";

export function Layout() {
  const { session, logout } = useAuth();
  const navigate = useNavigate();
  if (!session) return null;
  const { user, organization } = session.me;
  const areas = NAV_AREAS.filter((area) => area.roles.includes(user.role));

  return (
    <div className="shell">
      <nav className="sidebar" aria-label="Main">
        <Brand />
        {areas.map((area) => (
          <NavLink key={area.path} to={area.path} className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
            {area.label}
          </NavLink>
        ))}
      </nav>
      <div className="main">
        <header className="topbar">
          <div className="org">
            {organization.name}
            {organization.is_demo && <span className="badge demo" title="Synthetic demonstration data">DEMO</span>}
          </div>
          <div className="user">
            <span>
              {user.name} · {ROLE_LABELS[user.role]}
            </span>
            <button
              className="btn"
              onClick={() => {
                // Explicit sign-out: the next person starts on their own Overview, not this page.
                logout();
                navigate("/login", { replace: true });
              }}
            >
              Sign out
            </button>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
      <AssistantPanel role={user.role} />
    </div>
  );
}
