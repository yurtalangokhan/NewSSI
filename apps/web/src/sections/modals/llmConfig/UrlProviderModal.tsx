"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { toast } from "@/hooks/useToast";
import { WellKnownLangChainProvider } from "@/interfaces/llm";
import Modal from "@/refresh-components/Modal";
import { Button } from "@opal/components";
import Text from "@/refresh-components/texts/Text";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import { getProviderIcon, URL_PROVIDER_TYPES } from "@/lib/llmConfig/providers";
import { useTranslation } from "react-i18next";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  wellKnownProviders: WellKnownLangChainProvider[];
}

type TestStatus = "idle" | "testing" | "ok" | "error";

export function UrlProviderModal({ open, onOpenChange, wellKnownProviders }: Props) {
  const { t } = useTranslation();
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
  const [defaultModel, setDefaultModel] = useState("");

  const urlProviders = wellKnownProviders.filter((p) =>
    URL_PROVIDER_TYPES.includes(p.provider_type)
  );

  const reset = () => {
    setName("");
    setProviderType("ollama");
    setBaseUrl("");
    setApiKey("");
    setApiVersion("");
    setCustomConfigList([]);
    setDefaultModel("");
    setTestStatus("idle");
    setTestLatency(null);
    setTestError(null);
  };

  const handleTest = async () => {
    if (!baseUrl.trim()) {
      toast({ message: t("admin.llm.baseUrlRequiredToTest"), level: "error" });
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
        setTestError(data.error || t("admin.llm.connectionFailed"));
      }
    } catch (e) {
      setTestStatus("error");
      setTestError(e instanceof Error ? e.message : t("admin.llm.connectionFailed"));
    }
  };

  const handleSubmit = async () => {
    if (!name.trim() || !baseUrl.trim()) {
      toast({ message: t("admin.llm.nameAndBaseUrlRequired"), level: "error" });
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
          default_model: defaultModel.trim() || undefined,
          config: {
            api_version: apiVersion.trim() || null,
            custom_config: customConfig,
          },
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
          title={t("admin.llm.addLocalProviderTitle")}
          onClose={() => onOpenChange(false)}
        />

        <Modal.Body>
          <div className="space-y-4 w-full">
            <div className="space-y-1">
              <Text secondaryBody>{t("admin.llm.providerType")}</Text>
              <InputSelect
                value={providerType}
                onValueChange={(v) => { setProviderType(v); setTestStatus("idle"); }}
              >
                <InputSelect.Trigger placeholder={t("admin.llm.selectProvider")} />
                <InputSelect.Content>
                  {urlProviders.map((p) => {
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
                placeholder={t("admin.llm.localDisplayNamePlaceholder")}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            <div className="space-y-1">
              <Text secondaryBody>{t("admin.llm.baseUrl")}</Text>
              <div className="flex gap-2">
                <input
                  className="flex-1 rounded border border-input bg-background px-3 py-2 text-sm"
                  placeholder={t("admin.llm.baseUrlPlaceholder")}
                  value={baseUrl}
                  onChange={(e) => { setBaseUrl(e.target.value); setTestStatus("idle"); }}
                />
                <Button
                  prominence="secondary"
                  onClick={handleTest}
                  disabled={testStatus === "testing" || !baseUrl.trim()}
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
              <Text secondaryBody>{t("admin.llm.apiKeyOptional")}</Text>
              <input
                type="password"
                className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                placeholder={t("admin.llm.leaveBlankIfNotRequired")}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </div>

            <div className="space-y-1">
              <Text secondaryBody>{t("admin.llm.optionalApiVersion")}</Text>
              <input
                className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                placeholder={t("admin.llm.apiVersionPlaceholder")}
                value={apiVersion}
                onChange={(e) => setApiVersion(e.target.value)}
              />
            </div>

            <div className="rounded border border-border p-3 space-y-2">
              <Text secondaryBody>{t("admin.llm.optionalCustomConfigs")}</Text>
              {customConfigList.map(([key, value], idx) => (
                <div key={`${idx}-${key}`} className="grid grid-cols-12 gap-2">
                  <input
                    className="col-span-5 rounded border border-input bg-background px-3 py-2 text-sm"
                    placeholder={t("admin.llm.key")}
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
                    placeholder={t("admin.llm.value")}
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
                      {t("admin.llm.remove")}
                    </Button>
                  </div>
                </div>
              ))}
              <Button
                prominence="secondary"
                onClick={() => setCustomConfigList((prev) => [...prev, ["", ""]])}
              >
                {t("admin.llm.addConfig")}
              </Button>
            </div>



            <div className="space-y-1">
              <Text secondaryBody>{t("admin.llm.defaultModelOptional")}</Text>
              <input
                className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                placeholder={t("admin.llm.defaultModelExample")}
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
