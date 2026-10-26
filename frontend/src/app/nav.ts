// The eight screen areas (requirements FR-34..FR-38, design §5).

export type Role = "admin" | "analyst" | "approver" | "commercial" | "executive";

export const ALL_ROLES: Role[] = ["admin", "analyst", "approver", "commercial", "executive"];

export interface NavArea {
  path: string;
  label: string;
  /** Roles that may open this area; mirrors the permission matrix in design §3.7. */
  roles: Role[];
}

export const NAV_AREAS: NavArea[] = [
  { path: "/overview", label: "Overview", roles: ALL_ROLES },
  { path: "/data-setup", label: "Data setup", roles: ["admin"] },
  { path: "/agreements", label: "Rules & agreements", roles: ["admin", "analyst", "approver", "commercial"] },
  { path: "/findings", label: "Findings", roles: ["analyst", "approver", "commercial"] },
  { path: "/recovery", label: "Recovery tracker", roles: ["analyst", "approver", "executive"] },
  { path: "/pricing", label: "Pricing opportunities", roles: ALL_ROLES },
  { path: "/settings", label: "Access & settings", roles: ["admin", "approver"] },
];

export const ROLE_LABELS: Record<Role, string> = {
  admin: "Administrator",
  analyst: "Finance analyst",
  approver: "Finance approver",
  commercial: "Commercial manager",
  executive: "Executive viewer",
};
