import { NavLink, Outlet } from "react-router-dom";

import { useAuth } from "../features/auth/AuthContext";
import { NAV_AREAS, ROLE_LABELS } from "./nav";

export function Layout() {
  const { session, logout } = useAuth();
  if (!session) return null;
  const { user, organization } = session.me;
  const areas = NAV_AREAS.filter((area) => area.roles.includes(user.role));

  return (
    <div className="shell">
      <nav className="sidebar" aria-label="Main">
        <div className="brand">
          JAD<span>Assure</span>
        </div>
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
            <button className="btn" onClick={logout}>
              Sign out
            </button>
          </div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
