import { Navigate, Route, Routes } from "react-router-dom";

import { Layout } from "./Layout";
import { NAV_AREAS } from "./nav";
import { PAGES } from "./routes";

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        {NAV_AREAS.map((area) => (
          <Route key={area.path} path={area.path} element={PAGES[area.path]} />
        ))}
        <Route path="*" element={<Navigate to="/overview" replace />} />
      </Route>
    </Routes>
  );
}
