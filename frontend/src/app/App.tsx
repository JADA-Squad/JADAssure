import { Navigate, Route, Routes } from "react-router-dom";

import { AuthProvider } from "../features/auth/AuthContext";
import { RequireAuth, RequireRole } from "../features/auth/guards";
import { LoginPage } from "../features/auth/LoginPage";
import { SignupPage } from "../features/auth/SignupPage";
import { Layout } from "./Layout";
import { NAV_AREAS } from "./nav";
import { PAGES } from "./routes";

export function App() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/signup" element={<SignupPage />} />
        <Route element={<RequireAuth />}>
          <Route element={<Layout />}>
            {NAV_AREAS.map((area) => (
              <Route
                key={area.path}
                path={area.path}
                element={<RequireRole roles={area.roles}>{PAGES[area.path]}</RequireRole>}
              />
            ))}
            <Route path="*" element={<Navigate to="/overview" replace />} />
          </Route>
        </Route>
      </Routes>
    </AuthProvider>
  );
}
