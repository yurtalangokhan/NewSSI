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

export interface OrganizationRevealRequest {
  id: number;
  result: OrganizationNode;
  ancestorIds: string[];
}

export interface OrganizationSearchProps {
  searchResults: OrganizationNode[];
  searchLoading: boolean;
  searchError: string | null;
  resultsLimited: boolean;
  revealLoading: boolean;
  onSearch: (query: string) => void;
  onRevealResult: (result: OrganizationNode) => void;
  revealRequest?: OrganizationRevealRequest | null;
  onRevealReady?: (organization: OrganizationNode) => void;
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
