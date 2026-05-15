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
import { useTranslation } from "react-i18next";

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
  const { t } = useTranslation();
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
  const placeholders = {
    apiKey: t("admin.llm.enterApiKey"),
    baseUrl: t("admin.llm.leaveBlankForProviderDefault"),
    defaultModel: t("admin.llm.defaultModelExample"),
    apiVersion: t("admin.llm.apiVersionPlaceholder"),
  };
  const displayNamePlaceholder = t("admin.llm.displayNamePlaceholder", {
    provider: getProviderDisplayName(providerType),
  });

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
      toast({ message: t("admin.llm.apiKeyRequiredToTest"), level: "error" });
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
        setTestError(data.error || t("admin.llm.connectionFailed"));
      }
    } catch (e) {
      setTestStatus("error");
      setTestError(e instanceof Error ? e.message : t("admin.llm.connectionFailed"));
    }
  };

  const handleSubmit = async () => {
    if (!name.trim() || !apiKey.trim()) {
      toast({ message: t("admin.llm.nameAndApiKeyRequired"), level: "error" });
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
        throw new Error(err.detail || t("admin.llm.failedToAddProvider"));
      }
      toast({ message: t("admin.llm.providerAdded") });
      await mutate("/api/admin/providers");
      reset();
      onOpenChange(false);
    } catch (e: unknown) {
      toast({
        message: e instanceof Error ? e.message : t("admin.llm.failedToAddProvider"),
        level: "error",
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal open={open} onOpenChange={onOpenChange}>
      <Modal.Content width="sm">
        <Modal.Header
          title={t("admin.llm.addCloudProviderTitle")}
          onClose={() => onOpenChange(false)}
        />

        <Modal.Body>
          <div className="space-y-4 w-full">
            <div className="space-y-1">
              <Text secondaryBody>{t("admin.llm.provider")}</Text>
              <InputSelect
                value={providerType}
                onValueChange={(v) => setProviderType(v)}
              >
                <InputSelect.Trigger placeholder={t("admin.llm.selectProvider")} />
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
              <Text secondaryBody>{t("admin.llm.displayName")}</Text>
              <input
                className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                placeholder={displayNamePlaceholder}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            <div className="space-y-1">
              <Text secondaryBody>{t("admin.llm.apiKey")}</Text>
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
                  {testStatus === "testing" ? t("admin.llm.testing") : t("admin.llm.test")}
                </Button>
              </div>
              {testStatus === "ok" && (
                <p className="text-sm text-green-600">
                  {t("admin.llm.connected")}
                  {testLatency !== null ? ` (${testLatency}ms)` : ""}
                </p>
              )}
              {testStatus === "error" && (
                <p className="text-sm text-red-500">
                  {t("admin.llm.connectionFailed")}: {testError || t("admin.llm.connectionFailed")}
                </p>
              )}
            </div>

            <div className="space-y-1">
              <Text secondaryBody>{t("admin.llm.baseUrlOptional")}</Text>
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
                  <Text secondaryBody>{t("admin.llm.apiVersion")}</Text>
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
              <Text secondaryBody>{t("admin.llm.defaultModelOptional")}</Text>
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
            {t("modals.cancel")}
          </Button>
          <Button prominence="primary" onClick={handleSubmit} disabled={submitting}>
            {submitting ? t("admin.llm.adding") : t("admin.llm.addProvider")}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
