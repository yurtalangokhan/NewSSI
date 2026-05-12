"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { toast } from "@/hooks/useToast";
import { WellKnownLangChainProvider } from "@/interfaces/llm";
import Modal from "@/refresh-components/Modal";
import { Button } from "@opal/components";
import Text from "@/refresh-components/texts/Text";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import { getProviderDisplayName, getProviderIcon } from "@/lib/llmConfig/providers";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  wellKnownProviders: WellKnownLangChainProvider[];
  preselectedType?: string;
}

const PROVIDER_PLACEHOLDERS: Record<
  string,
  { apiKey: string; baseUrl: string; defaultModel: string; apiVersion: string }
> = {
  openai:          { apiKey: "sk-...",                       baseUrl: "https://api.openai.com/v1",                          defaultModel: "e.g. gpt-4o",                                                      apiVersion: "" },
  anthropic:       { apiKey: "sk-ant-...",                   baseUrl: "https://api.anthropic.com",                          defaultModel: "e.g. claude-3-7-sonnet-latest",                                    apiVersion: "" },
  google_genai:    { apiKey: "AIza...",                      baseUrl: "https://generativelanguage.googleapis.com (optional)", defaultModel: "e.g. gemini-1.5-pro",                                             apiVersion: "" },
  azure_openai:    { apiKey: "Azure API key",                baseUrl: "https://<resource>.openai.azure.com",                defaultModel: "e.g. gpt-4o",                                                      apiVersion: "2024-02-01" },
  openrouter:      { apiKey: "sk-or-...",                    baseUrl: "https://openrouter.ai/api (optional)",               defaultModel: "e.g. openai/gpt-4o-mini",                                         apiVersion: "" },
  google_vertexai: { apiKey: "Google service key / token",   baseUrl: "Use Google default endpoint (optional)",             defaultModel: "e.g. gemini-1.5-pro",                                             apiVersion: "" },
  azure_ai:        { apiKey: "Azure API key",                baseUrl: "https://<resource>.services.ai.azure.com",           defaultModel: "e.g. gpt-4o-mini",                                                apiVersion: "" },
  aws_bedrock:     { apiKey: "AWS credentials / token",      baseUrl: "Use provider default endpoint",                      defaultModel: "e.g. anthropic.claude-3-5-sonnet",                                apiVersion: "" },
  groq:            { apiKey: "gsk_...",                      baseUrl: "https://api.groq.com/openai (optional)",             defaultModel: "e.g. llama-3.3-70b-versatile",                                    apiVersion: "" },
  mistral:         { apiKey: "Mistral API key",              baseUrl: "https://api.mistral.ai (optional)",                  defaultModel: "e.g. mistral-large-latest",                                       apiVersion: "" },
  cohere:          { apiKey: "Cohere API key",               baseUrl: "Use provider default endpoint",                      defaultModel: "e.g. command-r-plus",                                             apiVersion: "" },
  deepseek:        { apiKey: "DeepSeek API key",             baseUrl: "https://api.deepseek.com (optional)",                defaultModel: "e.g. deepseek-chat",                                              apiVersion: "" },
  xai:             { apiKey: "xAI API key",                  baseUrl: "https://api.x.ai (optional)",                        defaultModel: "e.g. grok-2-latest",                                             apiVersion: "" },
  perplexity:      { apiKey: "Perplexity API key",           baseUrl: "https://api.perplexity.ai (optional)",               defaultModel: "e.g. sonar-pro",                                                  apiVersion: "" },
  together:        { apiKey: "Together API key",             baseUrl: "https://api.together.xyz (optional)",                defaultModel: "e.g. meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo",              apiVersion: "" },
  fireworks:       { apiKey: "Fireworks API key",            baseUrl: "https://api.fireworks.ai/inference (optional)",      defaultModel: "e.g. accounts/fireworks/models/llama-v3p1-70b-instruct",         apiVersion: "" },
  cerebras:        { apiKey: "Cerebras API key",             baseUrl: "https://api.cerebras.ai (optional)",                 defaultModel: "e.g. llama3.1-70b",                                               apiVersion: "" },
  huggingface:     { apiKey: "hf_...",                       baseUrl: "https://router.huggingface.co (optional)",           defaultModel: "e.g. meta-llama/Llama-3.1-70B-Instruct",                         apiVersion: "" },
  nvidia:          { apiKey: "NVIDIA API key",               baseUrl: "https://integrate.api.nvidia.com (optional)",        defaultModel: "e.g. meta/llama-3.1-70b-instruct",                               apiVersion: "" },
  ibm_watsonx:     { apiKey: "IBM API key",                  baseUrl: "Use provider default endpoint",                      defaultModel: "e.g. ibm/granite-3-8b-instruct",                                 apiVersion: "" },
  sambanova:       { apiKey: "SambaNova API key",            baseUrl: "https://api.sambanova.ai (optional)",                defaultModel: "e.g. Meta-Llama-3.1-70B-Instruct",                               apiVersion: "" },
};

const FALLBACK_PLACEHOLDERS = {
  apiKey: "Enter API key",
  baseUrl: "Leave blank to use provider default",
  defaultModel: "e.g. model-name",
  apiVersion: "",
};

export function ApiKeyProviderModal({
  open,
  onOpenChange,
  wellKnownProviders,
  preselectedType,
}: Props) {
  const { mutate } = useSWRConfig();
  const apiKeyProviders = wellKnownProviders.filter(
    (p) => p.category === "api_key"
  );

  const [name, setName] = useState("");
  const [providerType, setProviderType] = useState(
    preselectedType ?? apiKeyProviders[0]?.provider_type ?? "openai"
  );
  const [apiKey, setApiKey] = useState("");
  const [apiBase, setApiBase] = useState("");
  const [apiVersion, setApiVersion] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [testStatus, setTestStatus] = useState<"idle" | "testing" | "ok" | "error">("idle");
  const [testLatency, setTestLatency] = useState<number | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [defaultModel, setDefaultModel] = useState("");

  const isAzure = providerType === "azure_openai";
  const placeholders = PROVIDER_PLACEHOLDERS[providerType] ?? FALLBACK_PLACEHOLDERS;
  const displayNamePlaceholder = `e.g. My ${getProviderDisplayName(providerType)} Key`;

  const reset = () => {
    setName("");
    setApiKey("");
    setApiBase("");
    setApiVersion("");
    setDefaultModel("");
    setTestStatus("idle");
    setTestLatency(null);
    setTestError(null);
  };

  const handleTest = async () => {
    if (!apiKey.trim()) {
      toast({ message: "API Key is required to test connection", level: "error" });
      return;
    }
    setTestStatus("testing");
    setTestError(null);
    try {
      const res = await fetch("/api/admin/providers/test-connection", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          provider_type: providerType,
          api_key: apiKey.trim(),
          base_url: apiBase.trim() || undefined,
        }),
      });
      const data = await res.json();
      setTestLatency(data.latency_ms ?? null);
      if (data.success) {
        setTestStatus("ok");
      } else {
        setTestStatus("error");
        setTestError(data.error || "Connection failed");
      }
    } catch (e) {
      setTestStatus("error");
      setTestError(e instanceof Error ? e.message : "Connection failed");
    }
  };

  const handleSubmit = async () => {
    if (!name.trim() || !apiKey.trim()) {
      toast({ message: "Name and API Key are required", level: "error" });
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch("/api/admin/user-providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          provider_type: providerType,
          api_key: apiKey.trim(),
          api_base: apiBase.trim() || undefined,
          api_version: apiVersion.trim() || undefined,
          default_model: defaultModel.trim() || undefined,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to add provider");
      }
      toast({ message: "Provider added" });
      await mutate("/api/admin/providers");
      reset();
      onOpenChange(false);
    } catch (e: unknown) {
      toast({
        message: e instanceof Error ? e.message : "Failed to add provider",
        level: "error",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onOpenChange={onOpenChange}>
      <Modal.Content width="sm">
        <Modal.Header title="Add Cloud Provider" onClose={() => onOpenChange(false)} />

        <Modal.Body>
          <div className="space-y-4 w-full">
            <div className="space-y-1">
              <Text secondaryBody>Provider</Text>
              <InputSelect
                value={providerType}
                onValueChange={(v) => setProviderType(v)}
              >
                <InputSelect.Trigger placeholder="Select provider" />
                <InputSelect.Content>
                  {apiKeyProviders.map((p) => {
                    const ProviderIcon = getProviderIcon(p.provider_type);
                    return (
                      <InputSelect.Item
                        key={p.provider_type}
                        value={p.provider_type}
                        icon={ProviderIcon}
                      >
                        {p.name}
                      </InputSelect.Item>
                    );
                  })}
                </InputSelect.Content>
              </InputSelect>
            </div>

            <div className="space-y-1">
              <Text secondaryBody>Display Name</Text>
              <input
                className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                placeholder={displayNamePlaceholder}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            <div className="space-y-1">
              <Text secondaryBody>API Key</Text>
              <div className="flex gap-2">
                <input
                  type="password"
                  className="flex-1 rounded border border-input bg-background px-3 py-2 text-sm"
                  placeholder={placeholders.apiKey}
                  value={apiKey}
                  onChange={(e) => { setApiKey(e.target.value); setTestStatus("idle"); }}
                />
                <Button
                  prominence="secondary"
                  onClick={handleTest}
                  disabled={testStatus === "testing" || !apiKey.trim()}
                >
                  {testStatus === "testing" ? "Testing…" : "Test"}
                </Button>
              </div>
              {testStatus === "ok" && (
                <p className="text-sm text-green-600">
                  ✓ Connected{testLatency !== null ? ` (${testLatency}ms)` : ""}
                </p>
              )}
              {testStatus === "error" && (
                <p className="text-sm text-red-500">✗ {testError || "Connection failed"}</p>
              )}
            </div>

            <div className="space-y-1">
              <Text secondaryBody>Base URL (optional)</Text>
              <input
                className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                placeholder={placeholders.baseUrl}
                value={apiBase}
                onChange={(e) => setApiBase(e.target.value)}
              />
            </div>

            {isAzure && (
              <>
                <div className="space-y-1">
                  <Text secondaryBody>API Version</Text>
                  <input
                    className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                    placeholder={placeholders.apiVersion}
                    value={apiVersion}
                    onChange={(e) => setApiVersion(e.target.value)}
                  />
                </div>

              </>
            )}

            <div className="space-y-1">
              <Text secondaryBody>Default Model (optional)</Text>
              <input
                className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                placeholder={placeholders.defaultModel}
                value={defaultModel}
                onChange={(e) => setDefaultModel(e.target.value)}
              />
            </div>
          </div>
        </Modal.Body>

        <Modal.Footer>
          <Button prominence="secondary" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button prominence="primary" onClick={handleSubmit} disabled={submitting}>
            {submitting ? "Adding…" : "Add Provider"}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
