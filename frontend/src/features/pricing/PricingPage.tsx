import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { formatDecimal, formatMoney } from "../../components/format";

interface Opportunity {
  agreement_id: string;
  agreement_title: string;
  customer_name: string | null;
  item_code: string;
  currency: string;
  contracted_net_price: string;
  authorized_discount_pct: string;
  unit_cost: string;
  cost_source: string | null;
  margin_pct: string;
  target_margin_pct: string;
  suggested_price: string;
  billed_quantity_12m: string;
  indicative_annual_uplift: string;
  below_cost: boolean;
}

interface PricingResult {
  as_of: string;
  target_margin_pct: string;
  has_cost_data: boolean;
  opportunities: Opportunity[];
  items_without_cost: { item_code: string; currency: string }[];
  note: string;
}

/** Pricing opportunities (FR-33): future decisions from cost and margin data, kept apart from leakage. */
export function PricingPage() {
  const result = useQuery({ queryKey: ["pricing"], queryFn: () => api<PricingResult>("/reports/pricing-opportunities") });
  const r = result.data;

  return (
    <div className="stack">
      <div className="page-header" style={{ marginBottom: 0 }}>
        <h1>Pricing opportunities</h1>
        <p className="muted">
          Where a contract permits a price that earns less than the target margin. These are commercial decisions for the next
          negotiation, not billing errors, and they're never counted as leakage or recovered revenue.
        </p>
      </div>

      {result.isLoading && <p className="muted">Loading…</p>}

      {r && !r.has_cost_data && (
        <div className="placeholder">
          No cost data yet. Import <strong>Cost records</strong> in Data setup (item, unit cost, currency, effective dates) to see
          margin-based opportunities. Without cost data JADAssure doesn't suggest pricing changes.
        </div>
      )}

      {r && r.has_cost_data && (
        <section className="card stack">
          <div className="row spread">
            <h2 style={{ margin: 0 }}>Below the {formatDecimal(r.target_margin_pct)}% target margin</h2>
            <span className="muted">Contract prices in effect on {r.as_of} · target set in Access &amp; settings</span>
          </div>
          {r.opportunities.length === 0 ? (
            <p className="muted" style={{ margin: 0 }}>Every contracted price with cost data meets the target margin.</p>
          ) : (
            <div className="table-wrap">
              <table className="data">
                <thead>
                  <tr>
                    <th>Customer · agreement</th>
                    <th>Item</th>
                    <th className="num">Contract price</th>
                    <th className="num">Unit cost</th>
                    <th className="num">Margin</th>
                    <th className="num">Price at target</th>
                    <th className="num">Billed (12 mo)</th>
                    <th className="num">Indicative annual uplift</th>
                  </tr>
                </thead>
                <tbody>
                  {r.opportunities.map((o) => (
                    <tr key={`${o.agreement_id}-${o.item_code}`}>
                      <td>
                        {o.customer_name}
                        <div className="muted">{o.agreement_title}</div>
                      </td>
                      <td className="mono">{o.item_code}</td>
                      <td className="num">
                        {formatDecimal(o.contracted_net_price)} {o.currency}
                        {Number(o.authorized_discount_pct) > 0 && (
                          <div className="muted">after {formatDecimal(o.authorized_discount_pct)}% authorized discount</div>
                        )}
                      </td>
                      <td className="num">
                        {formatDecimal(o.unit_cost)} {o.currency}
                        {o.cost_source && <div className="muted">{o.cost_source}</div>}
                      </td>
                      <td className="num">
                        {o.margin_pct}%{o.below_cost && <div className="error">below cost</div>}
                      </td>
                      <td className="num">
                        {formatDecimal(o.suggested_price)} {o.currency}
                      </td>
                      <td className="num">{formatDecimal(o.billed_quantity_12m)}</td>
                      <td className="num">
                        <strong>{formatMoney(o.indicative_annual_uplift, o.currency)}</strong>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="muted" style={{ margin: 0, fontSize: 12 }}>
            Indicative uplift = (price at target − contract price) × quantity billed in the last 12 months. It assumes volume
            stays the same and is not revenue owed.
          </p>
        </section>
      )}

      {r && r.items_without_cost.length > 0 && (
        <section className="card">
          <h2>Cost data missing</h2>
          <p className="muted" style={{ marginTop: 0 }}>
            These contracted items have no cost record in effect today, so their margin can't be assessed:
          </p>
          <div className="row">
            {r.items_without_cost.map((i) => (
              <span key={`${i.item_code}-${i.currency}`} className="badge info mono">
                {i.item_code} · {i.currency}
              </span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
