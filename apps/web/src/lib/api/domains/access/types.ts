// Access Domain API types
// Merged from tenancy module

export interface Tenant {
  id: string;
  name: string;
  slug?: string;
}

export interface TenantBillingInfo {
  billing_email?: string;
  subscription_status?: string;
  plan?: string;
}

export interface Invitation {
  id: string;
  email: string;
  role: string;
  status: "pending" | "approved" | "denied";
  created_at: string;
}

export interface PendingUsersResponse {
  users: Invitation[];
}

export type ScopedPermissionTarget = "organization" | "user";
export type ScopedPermissionResource = "agent" | "rag_collection";
export type PermissionLevel = "read" | "execute" | "write" | "admin" | "owner";

export interface DirectResourcePermission {
  resource_id: string;
  resource_name: string;
  permission_level: PermissionLevel;
}

export interface AssignableResource {
  id: string;
  name: string;
  description?: string;
}

export interface ScopedPermissionsResponse {
  resources: AssignableResource[];
  permissions: DirectResourcePermission[];
  count: number;
}

export type SavedScopedPermissionsResponse = Omit<
  ScopedPermissionsResponse,
  "resources"
>;

export interface DirectoryRole {
  id: string;
  name: string;
  description: string | null;
  is_builtin: boolean;
}

export interface OrganizationNode {
  id: string;
  name: string;
  path: string;
  parent_id: string | null;
  description?: string;
  metadata?: Record<string, unknown>;
  children?: OrganizationNode[];
  user_count?: number;
  permission_count?: number;
  has_children?: boolean;
  children_count?: number;
  order_index?: number | null;
}

export interface OrganizationLayoutPosition {
  organization_id: string;
  x: number;
  y: number;
}
