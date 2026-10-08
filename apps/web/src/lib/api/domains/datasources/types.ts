export enum ConnectorCredentialPairStatus {
  SCHEDULED = "SCHEDULED",
  INITIAL_INDEXING = "INITIAL_INDEXING",
  ACTIVE = "ACTIVE",
  PAUSED = "PAUSED",
  DELETING = "DELETING",
  INVALID = "INVALID",
}
export interface ConnectorFileInfo {
  file_id: string;
  file_name: string;
  file_size?: number;
  upload_date?: string;
}
export const CONNECTOR_OPERATIONS = ["list_resources", "read"] as const;
export type ConnectorOperation = (typeof CONNECTOR_OPERATIONS)[number];
export interface ConnectorToolOption {
  id: string;
  name: string;
  connector_type: string;
  operations: string[];
  unavailable_reason: string | null;
}
