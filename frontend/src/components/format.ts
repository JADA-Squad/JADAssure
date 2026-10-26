// Display formatting. Money arrives from the API as decimal strings and is never converted to a JS
// float (GR-09). Rounding to 2 dp for display uses BigInt.

export function formatMoney(value: string | null | undefined, currency?: string): string {
  if (value === null || value === undefined || value === "") return "—";
  const negative = value.startsWith("-");
  const [intPart, fracPart = ""] = value.replace("-", "").split(".");
  const digits = (fracPart + "000").slice(0, 3);
  let cents = BigInt(intPart || "0") * 100n + BigInt(digits.slice(0, 2));
  if (Number(digits[2]) >= 5) cents += 1n; // half-up for display only
  const whole = (cents / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const frac = (cents % 100n).toString().padStart(2, "0");
  const text = `${negative && cents !== 0n ? "-" : ""}${whole}.${frac}`;
  return currency ? `${text} ${currency}` : text;
}

/** Trims trailing zeros from decimal strings ("45.000000" → "45"). Display only. */
export function formatDecimal(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

/** Unit prices: at least 2 dp, extra precision kept ("12.5000" → "12.50", "16.8750" → "16.875"). */
export function formatPrice(value: string | null | undefined): string {
  const trimmed = formatDecimal(value);
  if (trimmed === "—") return trimmed;
  const [intPart, frac = ""] = trimmed.split(".");
  return `${intPart}.${frac.padEnd(2, "0")}`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return value.slice(0, 10);
}

export function formatDateTime(value: string | null | undefined): string {
  return value ? new Date(value).toLocaleString() : "—";
}

export const CHECK_LABELS: Record<string, string> = {
  delivered_not_billed: "Delivered not billed",
  incorrect_rate: "Incorrect contracted rate",
  expired_discount: "Expired or unauthorized discount",
  missed_increase: "Missed contractual increase",
  credit_outside_policy: "Credit outside policy",
};

export const FINDING_STATUS_LABELS: Record<string, string> = {
  open: "Open",
  in_review: "In review",
  proposed: "Proposed",
  approved: "Approved",
  billed: "Billed",
  recovered: "Recovered",
  rejected: "Rejected",
  closed_no_recovery: "Closed, no recovery",
};

export const ROOT_CAUSE_LABELS: Record<string, string> = {
  price_not_updated: "Price not updated in billing system",
  discount_not_ended: "Discount not ended on time",
  delivery_not_billed: "Delivery not passed to billing",
  credit_process: "Credit issued outside process",
  contract_not_loaded: "Contract terms not loaded",
  data_quality: "Data quality issue",
  other: "Other",
};

export const CORRECTION_STATUS_LABELS: Record<string, string> = {
  prepared: "Prepared",
  billed: "Billed",
  partially_paid: "Partially paid",
  paid: "Paid",
};
