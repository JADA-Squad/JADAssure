import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import type { Role } from "../../app/nav";
import { useAuth } from "./AuthContext";

/** Sends unauthenticated visitors to /login, remembering where they were going. */
export function RequireAuth() {
  const { session, restoring } = useAuth();
  const location = useLocation();
  if (restoring) return <div className="auth-wrap muted">Loading…</div>;
  if (!session) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  return <Outlet />;
}

/** Hides an area from roles the permission matrix doesn't allow. The API enforces it too. */
export function RequireRole({ roles, children }: { roles: Role[]; children: ReactNode }) {
  const { session } = useAuth();
  if (!session || !roles.includes(session.me.user.role)) {
    return (
      <div className="placeholder" role="alert">
        Your role doesn't have access to this area.
      </div>
    );
  }
  return <>{children}</>;
}
