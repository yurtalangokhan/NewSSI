import { IconProps } from "@/components/icons/icons";
import { FunctionComponent } from "react";

export interface LLMOption {
  name: string;
  provider: string;
  providerId?: string;
  providerDisplayName: string;
  modelName: string;
  displayName: string;
  description?: string;
  vendor: string | null;
  maxInputTokens?: number | null;
  region?: string | null;
  version?: string | null;
  supportsReasoning?: boolean;
  supportsImageInput?: boolean;
  isRemote?: boolean;
}

export interface LLMOptionGroup {
  key: string;
  displayName: string;
  options: LLMOption[];
  Icon: FunctionComponent<IconProps>;
}
