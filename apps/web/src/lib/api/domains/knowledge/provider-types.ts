export type ProviderTestPayload = {
  provider_type: string;
  api_key: string | null;
  use_stored_key: boolean;
  config: Record<string, string>;
};

export type ProviderUpsertPayload = {
  id: number | null;
  name: string;
  provider_type: string;
  api_key: string | null;
  api_key_changed: boolean;
  config: Record<string, string>;
  activate: boolean;
};
