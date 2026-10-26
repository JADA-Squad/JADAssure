import { NavLink, Outlet } from "react-router-dom";

import { NAV_AREAS } from "./nav";

export function Layout() {
  return (
    <div className="shell">
      <nav className="sidebar" aria-label="Main">
        <div className="brand">
          JAD<span>Assure</span>
        </div>
        {NAV_AREAS.map((area) => (
          <NavLink key={area.path} to={area.path} className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}>
            {area.label}
          </NavLink>
        ))}
      </nav>
      <div className="main">
        <header className="topbar">
          <div className="org">JADAssure</div>
        </header>
        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
