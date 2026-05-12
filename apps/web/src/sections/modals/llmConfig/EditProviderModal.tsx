"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { toast } from "@/hooks/useToast";
import { UrlBasedProvider, ApiKeyProvider } from "@/interfaces/llm";
import Modal from "@/refresh-components/Modal";
import { Button } from "@opal/components";
import Text from "@/refresh-components/texts/Text";
import InputSelect from "@/refresh-components/inputs/InputSelect";
import { SvgTrash, SvgCheckCircle, SvgAlertCircle } from "@opal/icons";
import { useTranslation } from "react-i18next";
import { getProviderDisplayName, getProviderIcon, URL_PROVIDER_TYPES } from "@/lib/llmConfig/providers";
import { useWellKnownLangChainProviders } from "@/hooks/useProviders";

type Provider = UrlBasedProvider | ApiKeyProvider;

interface Props {
  provider: Provider;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type TestStatus = "idle" | "testing" | "ok" | "error";

export function EditProviderModal({ provider, open, onOpenChange }: Props) {
  const { t } = useTranslation();
  const { mutate } = useSWRConfig();

  const { data: wellKnownProviders = [] } = useWellKnownLangChainProviders();

  const isUrlProvider = provider.provider_kind === "url";
  const urlProvider = isUrlProvider ? (provider as UrlBasedProvider) : null;
  const apiKeyProvider = !isUrlProvider ? (provider as ApiKeyProvider) : null;

  const [providerType, setProviderType] = useState(provider.provider_type);
  const isAzure = providerType === "azure_openai";
  const ProviderIcon = getProviderIcon(providerType);

  const availableProviders = isUrlProvider
    ? wellKnownProviders.filter((p) => URL_PROVIDER_TYPES.includes(p.provider_type))
    : wellKnownProviders.filter((p) => p.category === "api_key");

  // Common fields
  const [name, setName] = useState(provider.name);
  const [defaultModel, setDefaultModel] = useState(provider.user_config.default_model ?? "");

  // URL provider fields
  const [baseUrl, setBaseUrl] = useState(urlProvider?.base_url ?? "");
  const [apiVersion, setApiVersion] = useState(
    urlProvider?.config.api_version ?? apiKeyProvider?.user_config.api_version ?? ""
  );
  const [customConfigList, setCustomConfigList] = useState<Array<[string, string]>>(
    Object.entries(urlProvider?.config.custom_config ?? {})
  );

  // Cloud provider fields
  const [apiBase, setApiBase] = useState(apiKeyProvider?.user_config.api_base ?? "");

  // API key — always shown empty (encrypted in DB)
  const [newApiKey, setNewApiKey] = useState("");
  const [deleteApiKey, setDeleteApiKey] = useState(false);
  const hasExistingApiKey = urlProvider?.has_api_key ?? true;

  // Test connection
  const [testStatus, setTestStatus] = useState<TestStatus>("idle");
  const [testLatency, setTestLatency] = useState<number | null>(null);
  const [testError, setTestError] = useState<string | null>(null);

  const [submitting, setSubmitting] = useState(false);

  const handleTest = async () => {
    const effectiveBaseUrl = isUrlProvider ? baseUrl.trim() : apiBase.trim();
    const effectiveApiKey = newApiKey.trim() || undefined;

    if (isUrlProvider && !effectiveBaseUrl) {
      toast({ message: t("admin.llm.baseUrlRequiredToTest"), level: "error" });
      return;
    }
    if (!isUrlProvider && !effectiveApiKey) {
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
          base_url: effectiveBaseUrl || undefined,
          api_key: effectiveApiKey,
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
    if (!name.trim()) {
      toast({ message: t("admin.llm.nameRequired"), level: "error" });
      return;
    }
    if (isUrlProvider && !baseUrl.trim()) {
      toast({ message: t("admin.llm.nameAndBaseUrlRequired"), level: "error" });
      return;
    }

    setSubmitting(true);
    try {
      let res: Response;

      if (isUrlProvider) {
        const customConfig = customConfigList.reduce<Record<string, string>>((acc, [k, v]) => {
          if (k.trim()) acc[k.trim()] = v;
          return acc;
        }, {});

        const body: Record<string, unknown> = {
          name: name.trim(),
          provider_type: providerType,
          base_url: baseUrl.trim(),
          default_model: defaultModel.trim() || null,
          config: {
            api_version: apiVersion.trim() || null,
            custom_config: customConfig,
          },
        };
        if (deleteApiKey) {
          body.clear_api_key = true;
        } else if (newApiKey.trim()) {
          body.api_key = newApiKey.trim();
        }

        res = await fetch(`/api/admin/providers/${provider.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      } else {
        const body: Record<string, string | null> = {
          name: name.trim(),
          api_base: apiBase.trim() || null,
          api_version: apiVersion.trim() || null,
          default_model: defaultModel.trim() || null,
        };
        if (newApiKey.trim()) body.api_key = newApiKey.trim();

        res = await fetch(`/api/admin/user-providers/${provider.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
      }

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || t("admin.llm.failedToUpdateProvider"));
      }

      toast({ message: t("admin.llm.providerUpdated") });
      await mutate("/api/admin/providers");
      onOpenChange(false);
    } catch (e: unknown) {
      toast({
        message: e instanceof Error ? e.message : t("admin.llm.failedToUpdateProvider"),
        level: "error",
      });
    } finally {
      setSubmitting(false);
    }
  };

  const testResultRow = (
    <>
      {testStatus === "ok" && (
        <p className="text-sm text-green-600 flex items-center gap-1">
          <SvgCheckCircle className="h-4 w-4" />
          {t("admin.llm.connected")}{testLatency !== null ? ` (${testLatency}ms)` : ""}
        </p>
      )}
      {testStatus === "error" && (
        <p className="text-sm text-red-500 flex items-center gap-1">
          <SvgAlertCircle className="h-4 w-4" />
          {testError || t("admin.llm.connectionFailed")}
        </p>
      )}
    </>
  );

  return (
    <Modal open={open} onOpenChange={onOpenChange}>
      <Modal.Content width="sm">
        <Modal.Header
          title={isUrlProvider ? t("admin.llm.editLocalProviderTitle") : t("admin.llm.editCloudProviderTitle")}
          onClose={() => onOpenChange(false)}
        />

        <Modal.Body>
          <div className="space-y-4 w-full">

            {/* Provider type — selectable like add modal */}
            <div className="space-y-1">
              <Text secondaryBody>{t("admin.llm.providerType")}</Text>
              <InputSelect value={providerType} onValueChange={(v) => setProviderType(v)}>
                <InputSelect.Trigger placeholder={t("admin.llm.selectProvider")}>
                  <span className="inline-flex items-center gap-2 text-text-04">
                    <ProviderIcon className="h-4 w-4" />
                    <span>{getProviderDisplayName(providerType)}</span>
                  </span>
                </InputSelect.Trigger>
                <InputSelect.Content>
                  {availableProviders.map((p) => {
                    const Icon = getProviderIcon(p.provider_type);
                    return (
                      <InputSelect.Item
                        key={p.provider_type}
                        value={p.provider_type}
                        icon={Icon}
                      >
                        {p.name}
                      </InputSelect.Item>
                    );
                  })}
                </InputSelect.Content>
              </InputSelect>
            </div>

            {/* Display name */}
            <div className="space-y-1">
              <Text secondaryBody>{t("admin.llm.displayName")}</Text>
              <input
                className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            {/* URL provider: base URL + test */}
            {isUrlProvider && (
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
                {testResultRow}
              </div>
            )}

            {/* API key */}
            <div className="space-y-1">
              <Text secondaryBody>
                {isUrlProvider ? t("admin.llm.apiKeyOptional") : t("admin.llm.apiKey")}
              </Text>

              {deleteApiKey ? (
                <div className="flex gap-2 items-center">
                  <p className="flex-1 text-sm text-amber-600 dark:text-amber-400">
                    {t("admin.llm.apiKeyWillBeDeleted")}
                  </p>
                  <Button prominence="tertiary" onClick={() => setDeleteApiKey(false)}>
                    {t("admin.llm.undoDeleteApiKey")}
                  </Button>
                </div>
              ) : (
                <>
                  <div className="flex gap-2 items-center">
                    <input
                      type="password"
                      className="flex-1 rounded border border-input bg-background px-3 py-2 text-sm"
                      placeholder={
                        hasExistingApiKey
                          ? t("admin.llm.apiKeyKeepCurrent")
                          : isUrlProvider
                          ? t("admin.llm.leaveBlankIfNotRequired")
                          : t("admin.llm.enterApiKey")
                      }
                      value={newApiKey}
                      onChange={(e) => { setNewApiKey(e.target.value); setTestStatus("idle"); }}
                    />
                    {isUrlProvider && hasExistingApiKey && (
                      <Button
                        icon={SvgTrash}
                        prominence="tertiary"
                        aria-label={t("admin.llm.deleteApiKey")}
                        onClick={() => { setDeleteApiKey(true); setNewApiKey(""); }}
                      />
                    )}
                  </div>
                  {hasExistingApiKey && (
                    <p className="text-xs text-muted-foreground">
                      {t("admin.llm.apiKeyHiddenHint")}
                    </p>
                  )}
                </>
              )}
            </div>

            {/* Cloud provider: test with new api key */}
            {!isUrlProvider && newApiKey.trim() && (
              <div className="space-y-1">
                <div className="flex justify-end">
                  <Button
                    prominence="secondary"
                    onClick={handleTest}
                    disabled={testStatus === "testing"}
                  >
                    {testStatus === "testing" ? t("admin.llm.testing") : t("admin.llm.test")}
                  </Button>
                </div>
                {testResultRow}
              </div>
            )}

            {/* Cloud provider: optional base URL */}
            {!isUrlProvider && (
              <div className="space-y-1">
                <Text secondaryBody>{t("admin.llm.baseUrlOptional")}</Text>
                <input
                  className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                  placeholder={t("admin.llm.leaveBlankForProviderDefault")}
                  value={apiBase}
                  onChange={(e) => setApiBase(e.target.value)}
                />
              </div>
            )}

            {/* API version — URL providers always, cloud only Azure */}
            {(isUrlProvider || isAzure) && (
              <div className="space-y-1">
                <Text secondaryBody>{t("admin.llm.optionalApiVersion")}</Text>
                <input
                  className="w-full rounded border border-input bg-background px-3 py-2 text-sm"
                  placeholder={t("admin.llm.apiVersionPlaceholder")}
                  value={apiVersion}
                  onChange={(e) => setApiVersion(e.target.value)}
                />
              </div>
            )}

            {/* URL provider: custom config */}
            {isUrlProvider && (
              <div className="rounded border border-border p-3 space-y-2">
                <Text secondaryBody>{t("admin.llm.optionalCustomConfigs")}</Text>
                {customConfigList.map(([key, value], idx) => (
                  <div key={idx} className="grid grid-cols-12 gap-2">
                    <input
                      className="col-span-5 rounded border border-input bg-background px-3 py-2 text-sm"
                      placeholder={t("admin.llm.key")}
                      value={key}
                      onChange={(e) =>
                        setCustomConfigList((prev) =>
                          prev.map((entry, i) => (i === idx ? [e.target.value, entry[1]] : entry))
                        )
                      }
                    />
                    <input
                      className="col-span-5 rounded border border-input bg-background px-3 py-2 text-sm"
                      placeholder={t("admin.llm.value")}
                      value={value}
                      onChange={(e) =>
                        setCustomConfigList((prev) =>
                          prev.map((entry, i) => (i === idx ? [entry[0], e.target.value] : entry))
                        )
                      }
                    />
                    <div className="col-span-2">
                      <Button
                        prominence="tertiary"
                        onClick={() =>
                          setCustomConfigList((prev) => prev.filter((_, i) => i !== idx))
                        }
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
            )}

            {/* Default model */}
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
            {submitting ? t("admin.llm.saving") : t("admin.llm.saveChanges")}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
