import { FederatedConnectorConfig } from "@/lib/types";
export interface DocumentSetCreationRequest {
  name: string;
  description: string;
  cc_pair_ids: number[];
  is_public: boolean;
  users: string[];
  groups: number[];
  federated_connectors: FederatedConnectorConfig[];
}

export interface DocumentSetUpdateRequest {
  id: number;
  description: string;
  cc_pair_ids: number[];
  is_public: boolean;
  users: string[];
  groups: number[];
  federated_connectors: FederatedConnectorConfig[];
}
