"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { toast } from "@/hooks/useToast";
import { WellKnownLangChainProvider } from "@/interfaces/llm";
import Modal from "@/refresh-components/Modal";
import { Button } from "@opal/components";
import Text from "@/refresh-components/texts/Text";
import InputSelect from "@/refresh-components/inputs/InputSelect";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  wellKnownProviders: WellKnownLangChainProvider[];
  preselectedType?: string;
}

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
  const [deploymentName, setDeploymentName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [testStatus, setTestStatus] = useState<"idle" | "testing" | "ok" | "error">("idle");
  const [testLatency, setTestLatency] = useState<number | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  const isAzure = providerType === "azure_openai";

  const reset = () => {
    setName("");
    setApiKey("");
    setApiBase("");
    setApiVersion("");
    setDeploymentName("");
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
          deployment_name: deploymentName.trim() || undefined,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to add provider");
      }
      toast({ message: "Provider added" });
      await mutate("/api/admin/user-providers");
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
                  {apiKeyProviders.map((p) => (
                    <InputSelect.Item key={p.provider_type} value={p.provider_type}>
                      {p.name}
                    </InputSelect.Item>
                  ))}
                </InputSelect.Content>
              </InputSelect>
            </div>

            <div className="space-y-1">
              <Text secondaryBody>Display Name</Text>
              <input
                className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                placeholder="e.g. My OpenAI Key"
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
                  placeholder="sk-..."
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
                placeholder="Leave blank to use default"
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
                    placeholder="2024-02-01"
                    value={apiVersion}
                    onChange={(e) => setApiVersion(e.target.value)}
                  />
                </div>

                <div className="space-y-1">
                  <Text secondaryBody>Deployment Name</Text>
                  <input
                    className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                    placeholder="gpt-4o"
                    value={deploymentName}
                    onChange={(e) => setDeploymentName(e.target.value)}
                  />
                </div>
              </>
            )}
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
