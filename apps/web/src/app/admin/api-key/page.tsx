"use client";

import { notFound } from "next/navigation";
import { ThreeDotsLoader } from "@/components/Loading";
import { errorHandlingFetcher } from "@/lib/fetcher";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import { ErrorCallout } from "@/components/ErrorCallout";
import useSWR, { mutate } from "swr";
import Separator from "@/refresh-components/Separator";
import {
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
  Table,
} from "@/components/ui/table";
import Title from "@/components/ui/title";
import { toast } from "@/hooks/useToast";
import { useState } from "react";
import { DeleteButton } from "@/components/DeleteButton";
import Modal from "@/refresh-components/Modal";
import { Spinner } from "@/components/Spinner";
import { deleteApiKey, regenerateApiKey } from "@/app/admin/api-key/lib";
import OnyxApiKeyForm from "@/app/admin/api-key/OnyxApiKeyForm";
import {
  APIKey,
  DISCORD_SERVICE_API_KEY_NAME,
} from "@/app/admin/api-key/types";
import CreateButton from "@/refresh-components/buttons/CreateButton";
import Button from "@/refresh-components/buttons/Button";
import CopyIconButton from "@/refresh-components/buttons/CopyIconButton";
import Text from "@/refresh-components/texts/Text";
import { SvgEdit, SvgKey, SvgRefreshCw } from "@opal/icons";
import { useCloudSubscription } from "@/hooks/useCloudSubscription";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { useTranslation } from "react-i18next";
import AdminOverviewPanel from "@/components/admin/AdminOverviewPanel";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.API_KEYS]!;

function Main() {
  const { t } = useTranslation();
  const {
    data: apiKeys,
    isLoading,
    error,
  } = useSWR<APIKey[]>("/api/admin/api-key", errorHandlingFetcher);

  const canCreateKeys = useCloudSubscription();

  const [fullApiKey, setFullApiKey] = useState<string | null>(null);
  const [keyIsGenerating, setKeyIsGenerating] = useState(false);
  const [showCreateUpdateForm, setShowCreateUpdateForm] = useState(false);
  const [selectedApiKey, setSelectedApiKey] = useState<APIKey | undefined>();

  const handleEdit = (apiKey: APIKey) => {
    setSelectedApiKey(apiKey);
    setShowCreateUpdateForm(true);
  };

  if (isLoading) {
    return <ThreeDotsLoader />;
  }

  if (!apiKeys || error) {
    return (
      <ErrorCallout
        errorTitle={t("admin.apiKey.fetchError")}
        errorMsg={error?.info?.detail || error.toString()}
      />
    );
  }

  // Filter out the discord service key from the displayed list
  const filteredApiKeys = apiKeys.filter(
    (key) => key.api_key_name !== DISCORD_SERVICE_API_KEY_NAME
  );

  const overviewSection = (
    <AdminOverviewPanel
      icon={route.icon}
      title={t("admin.apiKey.workspaceTitle")}
      description={t("admin.apiKey.workspaceDescription")}
      metrics={[
        {
          label: t("admin.apiKey.activeKeysLabel"),
          value: filteredApiKeys.length.toLocaleString(),
          tone: filteredApiKeys.length > 0 ? "success" : "warning",
        },
        {
          label: t("admin.apiKey.securityLabel"),
          value: t("admin.apiKey.permissionControlled"),
        },
        {
          label: t("admin.apiKey.keyCreationLabel"),
          value: canCreateKeys
            ? t("admin.apiKey.available")
            : t("admin.apiKey.requiresPlan"),
          tone: canCreateKeys ? "success" : "warning",
        },
      ]}
      actions={[
        {
          label: t("admin.navigation.routes.roles.sidebar"),
          href: ADMIN_PATHS.ROLES,
        },
        {
          label: t("admin.navigation.routes.tokenRateLimits.sidebar"),
          href: ADMIN_PATHS.TOKEN_RATE_LIMITS,
          primary: true,
        },
      ]}
    />
  );

  const introSection = (
    <div className="flex flex-col items-start gap-4">
      <Text as="p">
        {t("admin.apiKey.description")}
        {canCreateKeys ? ` ${t("admin.apiKey.descriptionWithButton")}` : ""}
      </Text>
      {canCreateKeys ? (
        <CreateButton onClick={() => setShowCreateUpdateForm(true)}>
          {t("admin.apiKey.createButton")}
        </CreateButton>
      ) : (
        <div className="flex flex-col gap-2 rounded-lg bg-background-tint-02 p-4">
          <Text as="p" text04>
            {t("admin.apiKey.paidSubscriptionRequired")}
          </Text>
          <Button href="/admin/billing">
            {t("admin.apiKey.upgradePlanButton")}
          </Button>
        </div>
      )}
    </div>
  );

  if (filteredApiKeys.length === 0) {
    return (
      <div className="flex flex-col gap-6">
        {overviewSection}
        {introSection}

        {showCreateUpdateForm && (
          <OnyxApiKeyForm
            onCreateApiKey={(apiKey) => {
              setFullApiKey(apiKey.api_key);
            }}
            onClose={() => {
              setShowCreateUpdateForm(false);
              setSelectedApiKey(undefined);
              mutate("/api/admin/api-key");
            }}
            apiKey={selectedApiKey}
          />
        )}
      </div>
    );
  }

  return (
    <>
      <Modal open={!!fullApiKey}>
        <Modal.Content width="sm" height="sm">
          <Modal.Header
            title={t("admin.apiKey.newApiKeyTitle")}
            icon={SvgKey}
            onClose={() => setFullApiKey(null)}
            description={t("admin.apiKey.newApiKeyDescription")}
          />
          <Modal.Body>
            <Text as="p" className="break-all flex-1">
              {fullApiKey}
            </Text>
            <CopyIconButton getCopyText={() => fullApiKey!} />
          </Modal.Body>
        </Modal.Content>
      </Modal>

      {keyIsGenerating && <Spinner />}

      {overviewSection}

      {introSection}

      {canCreateKeys && (
        <>
          <Separator />

          <Title className="mt-6">{t("admin.apiKey.existingKeysTitle")}</Title>
          <Table className="overflow-visible">
            <TableHeader>
              <TableRow>
                <TableHead>{t("admin.apiKey.nameColumn")}</TableHead>
                <TableHead>{t("admin.apiKey.apiKeyColumn")}</TableHead>
                <TableHead>{t("admin.apiKey.regenerateColumn")}</TableHead>
                <TableHead>{t("admin.apiKey.deleteColumn")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredApiKeys.map((apiKey) => (
                <TableRow key={apiKey.api_key_id}>
                  <TableCell>
                    <Button
                      internal
                      onClick={() => handleEdit(apiKey)}
                      leftIcon={SvgEdit}
                    >
                      {apiKey.api_key_name || <i>null</i>}
                    </Button>
                  </TableCell>
                  <TableCell className="max-w-64">
                    {apiKey.api_key_display}
                  </TableCell>
                  <TableCell>
                    <Button
                      internal
                      leftIcon={SvgRefreshCw}
                      onClick={async () => {
                        setKeyIsGenerating(true);
                        const response = await regenerateApiKey(apiKey);
                        setKeyIsGenerating(false);
                        if (!response.ok) {
                          const errorMsg = await response.text();
                          toast.error(
                            t("admin.apiKey.regenerateError", {
                              error: errorMsg,
                            })
                          );
                          return;
                        }
                        const newKey = (await response.json()) as APIKey;
                        setFullApiKey(newKey.api_key);
                        mutate("/api/admin/api-key");
                      }}
                    >
                      {t("admin.apiKey.refreshButton")}
                    </Button>
                  </TableCell>
                  <TableCell>
                    <DeleteButton
                      onClick={async () => {
                        const response = await deleteApiKey(apiKey.api_key_id);
                        if (!response.ok) {
                          const errorMsg = await response.text();
                          toast.error(
                            t("admin.apiKey.deleteError", { error: errorMsg })
                          );
                          return;
                        }
                        mutate("/api/admin/api-key");
                      }}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>

          {showCreateUpdateForm && (
            <OnyxApiKeyForm
              onCreateApiKey={(apiKey) => {
                setFullApiKey(apiKey.api_key);
              }}
              onClose={() => {
                setShowCreateUpdateForm(false);
                setSelectedApiKey(undefined);
                mutate("/api/admin/api-key");
              }}
              apiKey={selectedApiKey}
            />
          )}
        </>
      )}
    </>
  );
}

export default function Page() {
  notFound();

  const { t } = useTranslation();

  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header
        title={t(route.titleKey || "", { defaultValue: route.title })}
        icon={route.icon}
        separator
      />
      <SettingsLayouts.Body>
        <Main />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
