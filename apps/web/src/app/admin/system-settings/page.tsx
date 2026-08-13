"use client";

import type { ReactNode } from "react";
import { useMemo, useState } from "react";
import useSWR from "swr";
import useSWRMutation from "swr/mutation";
import Button from "@/refresh-components/buttons/Button";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Text from "@/refresh-components/texts/Text";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ADMIN_PATHS, ADMIN_ROUTE_CONFIG } from "@/lib/admin-routes";
import { authenticatedFetch, errorHandlingFetcher } from "@/lib/fetcher";
import { toast } from "@/hooks/useToast";
import { cn } from "@/lib/utils";
import {
  SvgCheck,
  SvgKey,
  SvgRefreshCw,
  SvgServer,
  SvgShield,
  SvgX,
} from "@opal/icons";
import type { IconFunctionComponent } from "@opal/types";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";
import { useTranslation } from "react-i18next";
import i18n from "@/i18n/config";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.SYSTEM_SETTINGS]!;

interface IdentityProviderStatus {
  enabled: boolean;
  alias: string;
  exists: boolean;
  reachable: boolean;
  provider: {
    alias?: string;
    displayName?: string;
    providerId?: string;
    enabled?: boolean;
    trustEmail?: boolean;
    firstBrokerLoginFlowAlias?: string;
  } | null;
  mapper: {
    exists: boolean;
    name: string;
    role?: string;
  } | null;
  error?: string;
}

interface SystemKeycloakSettings {
  keycloak: {
    enabled: boolean;
    source: string;
    realm: string | null;
    base_url: string | null;
    issuer_url: string | null;
    admin: string | null;
    admin_password_configured: boolean;
    client_id: string | null;
    login_client_id: string | null;
    client_secret_configured: boolean;
    admin_access_configured: boolean;
    realm_session: {
      reachable: boolean;
      access_token_lifespan?: number | null;
      sso_session_idle_timeout?: number | null;
      sso_session_max_lifespan?: number | null;
      error?: string;
    };
  };
  external_keycloak: {
    enabled: boolean;
    source: string;
    alias: string;
    display_name: string | null;
    issuer_url: string | null;
    base_url: string | null;
    realm: string | null;
    client_id: string | null;
    client_secret_configured: boolean;
    identity_provider: IdentityProviderStatus;
  };
}

function configFormFromSettings(data: SystemKeycloakSettings) {
  return {
    keycloak_enabled: data.keycloak.enabled,
    keycloak_base_url: data.keycloak.base_url ?? "",
    keycloak_issuer_url: data.keycloak.issuer_url ?? "",
    keycloak_realm: data.keycloak.realm ?? "",
    keycloak_admin: data.keycloak.admin ?? "",
    keycloak_admin_password: "",
    keycloak_client_id: data.keycloak.client_id ?? "",
    keycloak_login_client_id: data.keycloak.login_client_id ?? "",
    keycloak_client_secret: "",
    external_keycloak: data.external_keycloak.enabled,
    external_keycloak_alias: data.external_keycloak.alias ?? "",
    external_keycloak_display_name: data.external_keycloak.display_name ?? "",
    external_keycloak_base_url: data.external_keycloak.base_url ?? "",
    external_keycloak_issuer_url: data.external_keycloak.issuer_url ?? "",
    external_keycloak_realm: data.external_keycloak.realm ?? "",
    external_keycloak_client_id: data.external_keycloak.client_id ?? "",
    external_keycloak_client_secret: "",
  };
}

function sessionFormFromSettings(data: SystemKeycloakSettings) {
  return {
    access_token_lifespan: String(
      data.keycloak.realm_session.access_token_lifespan ?? ""
    ),
    sso_session_idle_timeout: String(
      data.keycloak.realm_session.sso_session_idle_timeout ?? ""
    ),
    sso_session_max_lifespan: String(
      data.keycloak.realm_session.sso_session_max_lifespan ?? ""
    ),
  };
}

async function postSyncExternalIdp(url: string) {
  const res = await authenticatedFetch(url, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: i18n.t("admin.systemSettings.syncFailedGeneric") }));
    throw new Error(err.detail || i18n.t("admin.systemSettings.syncFailedGeneric"));
  }
  return res.json();
}

async function patchJson(
  url: string,
  { arg }: { arg: Record<string, unknown> }
) {
  const res = await authenticatedFetch(url, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(arg),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: i18n.t("admin.systemSettings.saveFailedGeneric") }));
    throw new Error(err.detail || i18n.t("admin.systemSettings.saveFailedGeneric"));
  }
  return res.json();
}

function StatusPill({ active, label }: { active: boolean; label: string }) {
  const Icon = active ? SvgCheck : SvgX;
  return (
    <div
      className={cn(
        "inline-flex items-center gap-1.5 rounded-08 border px-2 py-1",
        active
          ? "border-status-success-02 bg-status-success-00"
          : "border-border-01 bg-background-neutral-01"
      )}
    >
      <Icon
        className={cn(
          "h-3 w-3",
          active ? "stroke-status-success-05" : "stroke-text-03"
        )}
      />
      <Text
        as="span"
        figureSmallLabel
        className={active ? "text-status-success-05" : "text-text-03"}
      >
        {label}
      </Text>
    </div>
  );
}

function SettingRow({
  label,
  value,
}: {
  label: string;
  value: string | boolean | null | undefined;
}) {
  const displayValue =
    typeof value === "boolean"
      ? value
        ? i18n.t("admin.systemSettings.enabled")
        : i18n.t("admin.systemSettings.disabled")
      : value || i18n.t("admin.systemSettings.notConfiguredValue");

  return (
    <div className="grid grid-cols-1 gap-1 border-b border-border-01 py-3 last:border-b-0 md:grid-cols-[180px_1fr]">
      <Text as="span" secondaryBody text03>
        {label}
      </Text>
      <Text as="span" mainUiBody text01 className="break-all">
        {displayValue}
      </Text>
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <Text as="span" secondaryBody text03>
        {label}
      </Text>
      {children}
    </label>
  );
}

function ToggleRow({
  checked,
  label,
  onCheckedChange,
}: {
  checked: boolean;
  label: string;
  onCheckedChange: (checked: boolean) => void;
}) {
  return (
    <button
      type="button"
      className="flex items-center gap-2 rounded-08 border border-border-01 bg-background-neutral-01 px-3 py-2 text-left"
      onClick={() => onCheckedChange(!checked)}
    >
      <Checkbox checked={checked} onCheckedChange={onCheckedChange} />
      <Text as="span" mainUiBody text01>
        {label}
      </Text>
    </button>
  );
}

function Panel({
  icon: Icon,
  title,
  children,
}: {
  icon: IconFunctionComponent;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="rounded-08 border border-border-01 bg-background-neutral-00">
      <div className="flex items-center gap-2 border-b border-border-01 px-4 py-3">
        <Icon className="h-4 w-4 stroke-text-02" />
        <Text as="span" headingH3 text01>
          {title}
        </Text>
      </div>
      <div className="px-4">{children}</div>
    </section>
  );
}

export default function SystemSettingsPage() {
  const { t } = useTranslation();
  const [configForm, setConfigForm] = useState({
    keycloak_enabled: false,
    keycloak_base_url: "",
    keycloak_issuer_url: "",
    keycloak_realm: "",
    keycloak_admin: "",
    keycloak_admin_password: "",
    keycloak_client_id: "",
    keycloak_login_client_id: "",
    keycloak_client_secret: "",
    external_keycloak: false,
    external_keycloak_alias: "",
    external_keycloak_display_name: "",
    external_keycloak_base_url: "",
    external_keycloak_issuer_url: "",
    external_keycloak_realm: "",
    external_keycloak_client_id: "",
    external_keycloak_client_secret: "",
  });
  const [sessionForm, setSessionForm] = useState({
    access_token_lifespan: "",
    sso_session_idle_timeout: "",
    sso_session_max_lifespan: "",
  });

  const { data, error, isLoading, mutate } = useSWR<SystemKeycloakSettings>(
    "/api/user-service/system-settings/keycloak",
    errorHandlingFetcher,
    {
      onSuccess: (nextData) => {
        setConfigForm(configFormFromSettings(nextData));
        setSessionForm(sessionFormFromSettings(nextData));
      },
    }
  );

  const { trigger, isMutating } = useSWRMutation(
    "/api/user-service/system-settings/keycloak/external-idp/sync",
    postSyncExternalIdp
  );
  const { trigger: saveConfig, isMutating: isSavingConfig } = useSWRMutation(
    "/api/user-service/system-settings/keycloak",
    patchJson
  );
  const { trigger: saveSession, isMutating: isSavingSession } = useSWRMutation(
    "/api/user-service/system-settings/keycloak/realm-session",
    patchJson
  );

  const idp = data?.external_keycloak.identity_provider;
  const headline = useMemo(() => {
    if (isLoading) return t("admin.systemSettings.checkingConfig");
    if (error) return t("admin.systemSettings.settingsUnavailable");
    if (!data?.keycloak.enabled) return t("admin.systemSettings.keycloakDisabled");
    if (!data.external_keycloak.enabled)
      return t("admin.systemSettings.externalKeycloakDisabled");
    if (idp?.exists && idp.mapper?.exists)
      return t("admin.systemSettings.externalIdpReady");
    return t("admin.systemSettings.externalIdpNeedsSync");
  }, [data, error, idp, isLoading, t]);

  const syncExternalIdp = async () => {
    try {
      const response = await trigger();
      await mutate(response.settings, false);
      toast.success(t("admin.systemSettings.externalIdpApplied"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  };

  const onSaveConfig = async () => {
    try {
      const payload = Object.fromEntries(
        Object.entries(configForm).filter(([, value]) => value !== "")
      );
      const response = await saveConfig(payload);
      await mutate(response, false);
      toast.success(t("admin.systemSettings.settingsSaved"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  };

  const onSaveSession = async () => {
    try {
      const payload = Object.fromEntries(
        Object.entries(sessionForm)
          .filter(([, value]) => value !== "")
          .map(([key, value]) => [key, Number(value)])
      );
      const response = await saveSession(payload);
      await mutate(
        data
          ? {
              ...data,
              keycloak: {
                ...data.keycloak,
                realm_session: response,
              },
            }
          : undefined,
        false
      );
      toast.success(t("admin.systemSettings.sessionSettingsSaved"));
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err));
    }
  };

  return (
    <SettingsLayouts.Root width="full">
      <SettingsLayouts.Header icon={route.icon} title={route.title} separator />
      <SettingsLayouts.Body>
        <div className="flex flex-col gap-4">
          <AdminOverviewPanel
            icon={route.icon}
            title={t("admin.systemSettings.workspaceTitle")}
            description={t("admin.systemSettings.workspaceDescription")}
            metrics={[
              {
                label: t("admin.systemSettings.keycloakLabel"),
                value: data?.keycloak.enabled
                  ? t("admin.systemSettings.enabled")
                  : t("admin.systemSettings.disabled"),
                tone: data?.keycloak.enabled ? "success" : "warning",
              },
              {
                label: t("admin.systemSettings.externalIdpLabel"),
                value: data?.external_keycloak.enabled
                  ? t("admin.systemSettings.enabled")
                  : t("admin.systemSettings.disabled"),
                tone: data?.external_keycloak.enabled ? "success" : "neutral",
              },
              {
                label: t("admin.systemSettings.realmSessionLabel"),
                value: data?.keycloak.realm_session.reachable
                  ? t("admin.systemSettings.reachable")
                  : t("admin.systemSettings.needsReview"),
                tone: data?.keycloak.realm_session.reachable
                  ? "success"
                  : "warning",
              },
            ]}
            actions={[
              {
                label: t("admin.navigation.routes.roles.sidebar"),
                href: ADMIN_PATHS.ROLES,
              },
              {
                label: t("admin.navigation.routes.users.sidebar"),
                href: ADMIN_PATHS.USERS,
                primary: true,
              },
            ]}
          />
          <section className="rounded-08 border border-border-01 bg-background-neutral-00 px-4 py-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex flex-col gap-1">
                <Text as="span" headingH2 text01>
                  {headline}
                </Text>
                <Text as="span" secondaryBody text03>
                  {t("admin.systemSettings.externalIdpEnvNote")}
                </Text>
              </div>
              <div className="flex flex-wrap gap-2">
                <StatusPill
                  active={Boolean(data?.keycloak.enabled)}
                  label={t("admin.systemSettings.keycloakLabel")}
                />
                <StatusPill
                  active={Boolean(data?.external_keycloak.enabled)}
                  label={t("admin.systemSettings.externalIdpLabel")}
                />
                <StatusPill
                  active={Boolean(idp?.exists)}
                  label={t("admin.systemSettings.providerExistsLabel")}
                />
                <StatusPill
                  active={Boolean(idp?.mapper?.exists)}
                  label={t("admin.systemSettings.roleMapperLabel")}
                />
              </div>
            </div>
          </section>

          {error ? (
            <section className="rounded-08 border border-status-error-02 bg-background-neutral-00 px-4 py-4">
              <Text as="span" mainUiBody className="text-status-error-05">
                {t("admin.systemSettings.failedToLoad")}
              </Text>
            </section>
          ) : null}

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_1fr_360px]">
            <Panel icon={SvgServer} title={t("admin.systemSettings.internalKeycloakTitle")}>
              <div className="flex flex-col gap-3 border-b border-border-01 py-4">
                <ToggleRow
                  checked={configForm.keycloak_enabled}
                  label={t("admin.systemSettings.enableInternalKeycloak")}
                  onCheckedChange={(checked) =>
                    setConfigForm((current) => ({
                      ...current,
                      keycloak_enabled: checked,
                    }))
                  }
                />
                <Field label={t("admin.systemSettings.baseUrlLabel")}>
                  <InputTypeIn
                    value={configForm.keycloak_base_url}
                    onChange={(event) =>
                      setConfigForm((current) => ({
                        ...current,
                        keycloak_base_url: event.target.value,
                      }))
                    }
                    placeholder="http://keycloak:8080"
                  />
                </Field>
                <Field label={t("admin.systemSettings.issuerUrlLabel")}>
                  <InputTypeIn
                    value={configForm.keycloak_issuer_url}
                    onChange={(event) =>
                      setConfigForm((current) => ({
                        ...current,
                        keycloak_issuer_url: event.target.value,
                      }))
                    }
                    placeholder="http://keycloak:8080/realms/agenticai"
                  />
                </Field>
                <Field label={t("admin.systemSettings.realmLabel")}>
                  <InputTypeIn
                    value={configForm.keycloak_realm}
                    onChange={(event) =>
                      setConfigForm((current) => ({
                        ...current,
                        keycloak_realm: event.target.value,
                      }))
                    }
                    placeholder="agenticai"
                  />
                </Field>
                <Field label={t("admin.systemSettings.adminUsernameLabel")}>
                  <InputTypeIn
                    value={configForm.keycloak_admin}
                    onChange={(event) =>
                      setConfigForm((current) => ({
                        ...current,
                        keycloak_admin: event.target.value,
                      }))
                    }
                    placeholder="admin"
                  />
                </Field>
                <Field label={t("admin.systemSettings.adminPasswordLabel")}>
                  <InputTypeIn
                    type="password"
                    value={configForm.keycloak_admin_password}
                    onChange={(event) =>
                      setConfigForm((current) => ({
                        ...current,
                        keycloak_admin_password: event.target.value,
                      }))
                    }
                    placeholder={
                      data?.keycloak.admin_password_configured
                        ? t("admin.systemSettings.configuredLeaveBlank")
                        : t("admin.systemSettings.notConfiguredValue")
                    }
                  />
                </Field>
                <Field label={t("admin.systemSettings.clientIdLabel")}>
                  <InputTypeIn
                    value={configForm.keycloak_client_id}
                    onChange={(event) =>
                      setConfigForm((current) => ({
                        ...current,
                        keycloak_client_id: event.target.value,
                      }))
                    }
                    placeholder="agenticai-web"
                  />
                </Field>
                <Field label={t("admin.systemSettings.clientSecretLabel")}>
                  <InputTypeIn
                    type="password"
                    value={configForm.keycloak_client_secret}
                    onChange={(event) =>
                      setConfigForm((current) => ({
                        ...current,
                        keycloak_client_secret: event.target.value,
                      }))
                    }
                    placeholder={
                      data?.keycloak.client_secret_configured
                        ? t("admin.systemSettings.configuredLeaveBlank")
                        : t("admin.systemSettings.optionalValue")
                    }
                  />
                </Field>
              </div>
              <SettingRow label={t("admin.systemSettings.enabled")} value={data?.keycloak.enabled} />
              <SettingRow label={t("admin.systemSettings.sourceLabel")} value={data?.keycloak.source} />
              <SettingRow label={t("admin.systemSettings.realmLabel")} value={data?.keycloak.realm} />
              <SettingRow label={t("admin.systemSettings.baseUrlLabel")} value={data?.keycloak.base_url} />
              <SettingRow
                label={t("admin.systemSettings.adminApiAccessLabel")}
                value={data?.keycloak.admin_access_configured}
              />
            </Panel>

            <Panel icon={SvgKey} title={t("admin.systemSettings.externalKeycloakIdpTitle")}>
              <div className="flex flex-col gap-3 border-b border-border-01 py-4">
                <ToggleRow
                  checked={configForm.external_keycloak}
                  label={t("admin.systemSettings.enableExternalKeycloak")}
                  onCheckedChange={(checked) =>
                    setConfigForm((current) => ({
                      ...current,
                      external_keycloak: checked,
                    }))
                  }
                />
                <Field label={t("admin.systemSettings.aliasLabel")}>
                  <InputTypeIn
                    value={configForm.external_keycloak_alias}
                    onChange={(event) =>
                      setConfigForm((current) => ({
                        ...current,
                        external_keycloak_alias: event.target.value,
                      }))
                    }
                    placeholder="external-keycloak"
                  />
                </Field>
                <Field label={t("admin.systemSettings.displayNameLabel")}>
                  <InputTypeIn
                    value={configForm.external_keycloak_display_name}
                    onChange={(event) =>
                      setConfigForm((current) => ({
                        ...current,
                        external_keycloak_display_name: event.target.value,
                      }))
                    }
                    placeholder="External Keycloak"
                  />
                </Field>
                <Field label={t("admin.systemSettings.issuerUrlLabel")}>
                  <InputTypeIn
                    value={configForm.external_keycloak_issuer_url}
                    onChange={(event) =>
                      setConfigForm((current) => ({
                        ...current,
                        external_keycloak_issuer_url: event.target.value,
                      }))
                    }
                    placeholder="https://sso.example.com/realms/external"
                  />
                </Field>
                <Field label={t("admin.systemSettings.baseUrlLabel")}>
                  <InputTypeIn
                    value={configForm.external_keycloak_base_url}
                    onChange={(event) =>
                      setConfigForm((current) => ({
                        ...current,
                        external_keycloak_base_url: event.target.value,
                      }))
                    }
                    placeholder="https://sso.example.com"
                  />
                </Field>
                <Field label={t("admin.systemSettings.realmLabel")}>
                  <InputTypeIn
                    value={configForm.external_keycloak_realm}
                    onChange={(event) =>
                      setConfigForm((current) => ({
                        ...current,
                        external_keycloak_realm: event.target.value,
                      }))
                    }
                    placeholder="ldap-realm"
                  />
                </Field>
                <Field label={t("admin.systemSettings.clientIdLabel")}>
                  <InputTypeIn
                    value={configForm.external_keycloak_client_id}
                    onChange={(event) =>
                      setConfigForm((current) => ({
                        ...current,
                        external_keycloak_client_id: event.target.value,
                      }))
                    }
                    placeholder="ldap-client"
                  />
                </Field>
                <Field label={t("admin.systemSettings.clientSecretLabel")}>
                  <InputTypeIn
                    type="password"
                    value={configForm.external_keycloak_client_secret}
                    onChange={(event) =>
                      setConfigForm((current) => ({
                        ...current,
                        external_keycloak_client_secret: event.target.value,
                      }))
                    }
                    placeholder={
                      data?.external_keycloak.client_secret_configured
                        ? t("admin.systemSettings.configuredLeaveBlank")
                        : t("admin.systemSettings.requiredValue")
                    }
                  />
                </Field>
              </div>
              <SettingRow
                label={t("admin.systemSettings.sourceLabel")}
                value={data?.external_keycloak.source}
              />
              <SettingRow
                label={t("admin.systemSettings.aliasLabel")}
                value={data?.external_keycloak.alias}
              />
              <SettingRow
                label={t("admin.systemSettings.displayNameLabel")}
                value={data?.external_keycloak.display_name}
              />
              <SettingRow
                label={t("admin.systemSettings.issuerUrlLabel")}
                value={data?.external_keycloak.issuer_url}
              />
              <SettingRow
                label={t("admin.systemSettings.clientIdLabel")}
                value={data?.external_keycloak.client_id}
              />
              <SettingRow
                label={t("admin.systemSettings.clientSecretLabel")}
                value={
                  data?.external_keycloak.client_secret_configured
                    ? t("admin.systemSettings.configuredValue")
                    : null
                }
              />
            </Panel>

            <Panel icon={SvgShield} title={t("admin.systemSettings.operationsTitle")}>
              <div className="flex flex-col gap-3 py-4">
                <Button
                  main
                  primary
                  leftIcon={SvgCheck}
                  disabled={isLoading || isSavingConfig}
                  onClick={onSaveConfig}
                  className="w-full"
                >
                  {isSavingConfig ? t("admin.systemSettings.savingButton") : t("admin.systemSettings.saveKeycloakSettingsButton")}
                </Button>
                <Button
                  main
                  secondary
                  leftIcon={SvgRefreshCw}
                  disabled={
                    isLoading || isMutating || !data?.external_keycloak.enabled
                  }
                  onClick={syncExternalIdp}
                  className="w-full"
                >
                  {isMutating ? t("admin.systemSettings.applyingButton") : t("admin.systemSettings.applyExternalIdpButton")}
                </Button>
                <div className="flex flex-col gap-3 rounded-08 border border-border-01 bg-background-neutral-01 px-3 py-3">
                  <Text as="span" secondaryBody text03>
                    {t("admin.systemSettings.realmSessionDurations")}
                  </Text>
                  <Field label={t("admin.systemSettings.accessTokenLifespanLabel")}>
                    <InputTypeIn
                      type="number"
                      value={sessionForm.access_token_lifespan}
                      onChange={(event) =>
                        setSessionForm((current) => ({
                          ...current,
                          access_token_lifespan: event.target.value,
                        }))
                      }
                    />
                  </Field>
                  <Field label={t("admin.systemSettings.ssoIdleTimeoutLabel")}>
                    <InputTypeIn
                      type="number"
                      value={sessionForm.sso_session_idle_timeout}
                      onChange={(event) =>
                        setSessionForm((current) => ({
                          ...current,
                          sso_session_idle_timeout: event.target.value,
                        }))
                      }
                    />
                  </Field>
                  <Field label={t("admin.systemSettings.ssoMaxLifespanLabel")}>
                    <InputTypeIn
                      type="number"
                      value={sessionForm.sso_session_max_lifespan}
                      onChange={(event) =>
                        setSessionForm((current) => ({
                          ...current,
                          sso_session_max_lifespan: event.target.value,
                        }))
                      }
                    />
                  </Field>
                  <Button
                    main
                    secondary
                    leftIcon={SvgCheck}
                    disabled={isLoading || isSavingSession}
                    onClick={onSaveSession}
                    className="w-full"
                  >
                    {isSavingSession ? t("admin.systemSettings.savingButton") : t("admin.systemSettings.saveSessionSettingsButton")}
                  </Button>
                </div>
                <Button
                  main
                  secondary
                  leftIcon={SvgRefreshCw}
                  disabled={isLoading || isMutating}
                  onClick={() => mutate()}
                  className="w-full"
                >
                  {t("admin.systemSettings.refreshStatusButton")}
                </Button>
                <div className="rounded-08 border border-border-01 bg-background-neutral-01 px-3 py-3">
                  <Text as="span" secondaryBody text03 className="block">
                    {t("admin.systemSettings.startupBehaviorTitle")}
                  </Text>
                  <Text as="span" mainUiBody text01 className="block pt-1">
                    {t("admin.systemSettings.startupBehaviorDescription")}
                  </Text>
                </div>
                {idp?.error ? (
                  <div className="rounded-08 border border-status-error-02 bg-background-neutral-01 px-3 py-3">
                    <Text
                      as="span"
                      secondaryBody
                      className="block text-status-error-05"
                    >
                      {idp.error}
                    </Text>
                  </div>
                ) : null}
              </div>
            </Panel>
          </div>
        </div>
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
