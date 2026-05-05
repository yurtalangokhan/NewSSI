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

export function UrlProviderModal({ open, onOpenChange, wellKnownProviders }: Props) {
  const { mutate } = useSWRConfig();
  const [name, setName] = useState("");
  const [providerType, setProviderType] = useState("ollama");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const urlProviders = wellKnownProviders.filter((p) =>
    URL_TYPES.includes(p.provider_type)
  );

  const reset = () => {
    setName("");
    setProviderType("ollama");
    setBaseUrl("");
    setApiKey("");
  };

  const handleSubmit = async () => {
    if (!name.trim() || !baseUrl.trim()) {
      toast({ title: "Name and Base URL are required", variant: "destructive" });
      return;
    }
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
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || "Failed to add provider");
      }
      toast({ title: "Provider added" });
      await mutate("/api/admin/providers");
      reset();
      onOpenChange(false);
    } catch (e: unknown) {
      toast({
        title: e instanceof Error ? e.message : "Failed to add provider",
        variant: "destructive",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onOpenChange={onOpenChange}>
      <Modal.Content className="max-w-lg">
        <Modal.Header>
          <Modal.Title>Add Local / Self-Hosted Provider</Modal.Title>
        </Modal.Header>

        <div className="space-y-4 py-2">
          <div className="space-y-1">
            <Text size="sm" weight="medium">Provider Type</Text>
            <InputSelect
              value={providerType}
              onChange={(v) => setProviderType(v as string)}
              options={urlProviders.map((p) => ({
                label: p.name,
                value: p.provider_type,
              }))}
            />
          </div>

          <div className="space-y-1">
            <Text size="sm" weight="medium">Display Name</Text>
            <input
              className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
              placeholder="e.g. Local Ollama"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div className="space-y-1">
            <Text size="sm" weight="medium">Base URL</Text>
            <input
              className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
              placeholder="http://localhost:11434"
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </div>

          <div className="space-y-1">
            <Text size="sm" weight="medium">API Key (optional)</Text>
            <input
              type="password"
              className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
              placeholder="Leave blank if not required"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>
        </div>

        <Modal.Footer>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={submitting}>
            {submitting ? "Adding…" : "Add Provider"}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
