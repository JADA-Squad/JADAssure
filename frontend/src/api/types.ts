import type { Role } from "../app/nav";

export interface Organization {
  id: string;
  name: string;
  short_code: string;
  business_type: string;
  is_demo: boolean;
}

export interface User {
  id: string;
  email: string;
  name: string;
  role: Role;
  active: boolean;
  created_at: string;
}

export interface Me {
  user: User;
  organization: Organization;
  capabilities: string[];
}

export interface TokenResponse {
  access_token: string;
  token_type: "bearer";
  expires_at: string;
  me: Me;
}
