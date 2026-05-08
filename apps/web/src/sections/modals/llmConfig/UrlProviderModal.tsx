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
}

const URL_TYPES = ["ollama", "vllm", "openai_compatible", "litellm"];

type TestStatus = "idle" | "testing" | "ok" | "error";

export function UrlProviderModal({ open, onOpenChange, wellKnownProviders }: Props) {
  const { mutate } = useSWRConfig();
  const [name, setName] = useState("");
  const [providerType, setProviderType] = useState("ollama");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [apiVersion, setApiVersion] = useState("");
  const [customConfigList, setCustomConfigList] = useState<Array<[string, string]>>([]);

  const [submitting, setSubmitting] = useState(false);
  const [testStatus, setTestStatus] = useState<TestStatus>("idle");
  const [testLatency, setTestLatency] = useState<number | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  const urlProviders = wellKnownProviders.filter((p) =>
    URL_TYPES.includes(p.provider_type)
  );

  const reset = () => {
    setName("");
    setProviderType("ollama");
    setBaseUrl("");
    setApiKey("");
    setApiVersion("");
    setCustomConfigList([]);
    setTestStatus("idle");
    setTestLatency(null);
    setTestError(null);
  };

  const handleTest = async () => {
    if (!baseUrl.trim()) {
      toast({ message: "Base URL is required to test connection", level: "error" });
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
          base_url: baseUrl.trim(),
          api_key: apiKey.trim() || undefined,
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
    if (!name.trim() || !baseUrl.trim()) {
      toast({ message: "Name and Base URL are required", level: "error" });
      return;
    }

    const customConfig = customConfigList.reduce<Record<string, string>>((acc, [key, value]) => {
      const cleanedKey = key.trim();
      if (cleanedKey) {
        acc[cleanedKey] = value;
      }
      return acc;
    }, {});

    setSubmitting(true);
    try {
      const res = await fetch("/api/admin/providers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          provider_type: providerType,
          base_url: baseUrl.trim(),
          api_key: apiKey.trim() || undefined,
          config: {
            api_version: apiVersion.trim() || null,
            custom_config: customConfig,
          },
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
        <Modal.Header title="Add Local / Self-Hosted Provider" onClose={() => onOpenChange(false)} />

        <Modal.Body>
          <div className="space-y-4 w-full">
            <div className="space-y-1">
              <Text secondaryBody>Provider Type</Text>
              <InputSelect
                value={providerType}
                onValueChange={(v) => { setProviderType(v); setTestStatus("idle"); }}
              >
                <InputSelect.Trigger placeholder="Select provider" />
                <InputSelect.Content>
                  {urlProviders.map((p) => (
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
                placeholder="e.g. Local Ollama"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            <div className="space-y-1">
              <Text secondaryBody>Base URL</Text>
              <div className="flex gap-2">
                <input
                  className="flex-1 rounded border border-input bg-background px-3 py-2 text-sm"
                  placeholder="http://localhost:11434"
                  value={baseUrl}
                  onChange={(e) => { setBaseUrl(e.target.value); setTestStatus("idle"); }}
                />
                <Button
                  prominence="secondary"
                  onClick={handleTest}
                  disabled={testStatus === "testing" || !baseUrl.trim()}
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
              <Text secondaryBody>API Key (optional)</Text>
              <input
                type="password"
                className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                placeholder="Leave blank if not required"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </div>

            <div className="space-y-1">
              <Text secondaryBody>[Optional] API Version</Text>
              <input
                className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                placeholder="e.g. 2024-02-15-preview"
                value={apiVersion}
                onChange={(e) => setApiVersion(e.target.value)}
              />
            </div>

            <div className="rounded border border-border p-3 space-y-2">
              <Text secondaryBody>[Optional] Custom Configs</Text>
              {customConfigList.map(([key, value], idx) => (
                <div key={`${idx}-${key}`} className="grid grid-cols-12 gap-2">
                  <input
                    className="col-span-5 rounded border border-input bg-background px-3 py-2 text-sm"
                    placeholder="Key"
                    value={key}
                    onChange={(e) => {
                      setCustomConfigList((prev) =>
                        prev.map((entry, i) =>
                          i === idx ? [e.target.value, entry[1]] : entry
                        )
                      );
                    }}
                  />
                  <input
                    className="col-span-5 rounded border border-input bg-background px-3 py-2 text-sm"
                    placeholder="Value"
                    value={value}
                    onChange={(e) => {
                      setCustomConfigList((prev) =>
                        prev.map((entry, i) =>
                          i === idx ? [entry[0], e.target.value] : entry
                        )
                      );
                    }}
                  />
                  <div className="col-span-2">
                    <Button
                      prominence="tertiary"
                      onClick={() => {
                        setCustomConfigList((prev) => prev.filter((_, i) => i !== idx));
                      }}
                    >
                      Remove
                    </Button>
                  </div>
                </div>
              ))}
              <Button
                prominence="secondary"
                onClick={() => setCustomConfigList((prev) => [...prev, ["", ""]])}
              >
                + Add Config
              </Button>
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
