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
}

export interface OrganizationMember {
  id: string;
  user_id: string;
  organization_id: string;
  role_in_org: string;
  is_active?: boolean;
  user?: {
    id: string;
    email?: string;
    first_name?: string;
    last_name?: string;
    username?: string;
  } | null;
}

export type OrganizationMembersByUnit = Record<string, OrganizationMember[]>;

export type CreateOrganization = (
  parentId: string | null,
  name: string
) => Promise<void>;
export type UpdateOrganization = (
  id: string,
  updates: Partial<OrganizationNode>
) => Promise<void>;
export type DeleteOrganization = (id: string) => Promise<void>;
export type MoveOrganization = (
  id: string,
  newParentId: string | null
) => Promise<boolean>;
