import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { ROLE_LABELS, type Role } from "../../app/nav";

interface DemoAccount {
  organization: string;
  name: string;
  email: string;
  role: Role;
  password: string;
}

/** Seeded DEMO logins (DATA-001). The API returns nothing unless SHOW_DEMO_ACCOUNTS is enabled. */
export function DemoAccounts({ onPick }: { onPick: (email: string, password: string) => void }) {
  const { data } = useQuery({
    queryKey: ["demo-accounts"],
    queryFn: () => api<DemoAccount[]>("/auth/demo-accounts"),
    staleTime: Infinity,
    retry: false,
  });
  if (!data || data.length === 0) return null;

  const orgs = [...new Set(data.map((a) => a.organization))];
  return (
    <section className="card demo-panel" aria-label="Demo accounts">
      <div className="row spread">
        <h2 style={{ margin: 0 }}>
          Demo accounts <span className="badge demo">DEMO</span>
        </h2>
        <span className="muted">Synthetic data · shared password shown for local demos only</span>
      </div>
      <div className="table-wrap">
      <table className="data">
        <thead>
          <tr>
            <th>Role</th>
            {orgs.map((o) => (
              <th key={o}>{o.replace(" (demo)", "")}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(Object.keys(ROLE_LABELS) as Role[]).map((role) => (
            <tr key={role}>
              <td>{ROLE_LABELS[role]}</td>
              {orgs.map((o) => {
                const acct = data.find((a) => a.organization === o && a.role === role);
                return (
                  <td key={o}>
                    {acct && (
                      <button className="btn link" type="button" onClick={() => onPick(acct.email, acct.password)}>
                        {acct.email}
                      </button>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </section>
  );
}
