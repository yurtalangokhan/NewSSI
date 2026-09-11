"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AdminPageTitle } from "@/components/admin/Title";
import CardSection from "@/components/admin/CardSection";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import StepSidebar from "@/sections/sidebar/StepSidebarWrapper";
import { toast } from "@/hooks/useToast";
import { SvgSettings } from "@opal/icons";
import {
  ConnectorSpec,
  DatasourceConflictError,
  StreamInfo,
  fetchConnectorSpec,
  validateConnectorConfig,
  fetchConnectorStreams,
  createDatasource,
} from "@/lib/airbyte";
import SchemaForm from "@/components/admin/airbyte/SchemaForm/index";
import { materializeSchemaDefaults } from "@/components/admin/airbyte/SchemaForm/utils";
import { useTranslation } from "react-i18next";

type Step = 0 | 1 | 2;

interface AirbyteConnectorPageProps {
  connectorName: string;
}

export default function AirbyteConnectorPage({
  connectorName,
}: AirbyteConnectorPageProps) {
  const router = useRouter();
  const { t } = useTranslation();

  const [step, setStep] = useState<Step>(0);
  const [spec, setSpec] = useState<ConnectorSpec | null>(null);
  const [specError, setSpecError] = useState(false);

  const [config, setConfig] = useState<Record<string, unknown>>({});
  const [validating, setValidating] = useState(false);
  const [validationMsg, setValidationMsg] = useState<string | null>(null);

  const [streams, setStreams] = useState<StreamInfo[]>([]);
  const [selectedStreams, setSelectedStreams] = useState<Set<string>>(
    new Set()
  );
  const [loadingStreams, setLoadingStreams] = useState(false);

  const [datasourceName, setDatasourceName] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const displayName =
    spec?.display_name ??
    connectorName
      .replace(/^source-/, "")
      .replace(/-/g, " ")
      .replace(/\b\w/g, (l) => l.toUpperCase());

  useEffect(() => {
    fetchConnectorSpec(connectorName)
      .then((s) => {
        setSpec(s);
        setConfig(
          (materializeSchemaDefaults(s.connection_specification, {}) as Record<
            string,
            unknown
          >) ?? {}
        );
      })
      .catch(() => setSpecError(true));
  }, [connectorName]);

  const handleValidateAndNext = useCallback(async () => {
    setValidating(true);
    setValidationMsg(null);
    try {
      const result = await validateConnectorConfig(connectorName, config);
      if (result.valid) {
        setLoadingStreams(true);
        setStep(1);
        try {
          const s = await fetchConnectorStreams(connectorName, config);
          setStreams(s);
          setSelectedStreams(new Set(s.map((st) => st.name)));
        } catch {
          setStreams([]);
        } finally {
          setLoadingStreams(false);
        }
      } else {
        setValidationMsg(result.message);
      }
    } catch (e: unknown) {
      setValidationMsg(
        e instanceof Error
          ? e.message
          : t("admin.airbyteConnector.validationFailed")
      );
    } finally {
      setValidating(false);
    }
  }, [connectorName, config]);

  const handleCreate = useCallback(async () => {
    if (!datasourceName.trim()) return;
    setNameError(null);
    setCreating(true);
    try {
      await createDatasource({
        name: datasourceName.trim(),
        config: {
          connector_type: connectorName,
          connector_config: config,
          streams:
            selectedStreams.size > 0 ? Array.from(selectedStreams) : undefined,
        },
      });
      toast.success(t("admin.airbyteConnector.datasourceCreated"));
      router.push("/admin/indexing/status");
    } catch (e: unknown) {
      if (e instanceof DatasourceConflictError) {
        setNameError(e.message);
      } else {
        toast.error(
          e instanceof Error ? e.message : "Failed to create data source"
        );
      }
    } finally {
      setCreating(false);
    }
  }, [connectorName, config, datasourceName, selectedStreams, router]);

  return (
    <div className="flex justify-center w-full min-h-full">
      {/* Sidebar */}
      <div className="sticky top-0 self-start flex-shrink-0 h-screen">
        <StepSidebar
          buttonName={t("admin.airbyteConnector.addConnector")}
          buttonIcon={SvgSettings}
          buttonHref="/admin/add-connector"
        >
          <div className="relative mt-4">
            <div className="absolute h-[85%] left-[6px] top-[8px] bottom-0 w-0.5 bg-background-tint-04" />
            {[
              t("admin.airbyteConnector.steps.configure"),
              t("admin.airbyteConnector.steps.selectStreams"),
              t("admin.airbyteConnector.steps.nameAndConfirm"),
            ].map((label, index) => {
              const allowed = index <= step;
              return (
                <div
                  key={index}
                  className={`flex items-center mb-6 relative ${
                    !allowed
                      ? "cursor-not-allowed opacity-50"
                      : "cursor-pointer"
                  }`}
                  onClick={() => {
                    if (allowed) setStep(index as Step);
                  }}
                >
                  <div className="flex-shrink-0 mr-4 z-10">
                    <div
                      className={`h-3.5 w-3.5 rounded-full border-2 ${
                        index === step
                          ? "border-blue-500 bg-blue-500"
                          : index < step
                            ? "border-blue-500 bg-blue-500"
                            : "border-border bg-background-tint-00"
                      }`}
                    />
                  </div>
                  <Text
                    as="span"
                    secondaryBody
                    className={index === step ? "font-semibold" : ""}
                  >
                    {label}
                  </Text>
                </div>
              );
            })}
          </div>
        </StepSidebar>
      </div>

      {/* Main content */}
      <div className="mt-12 w-full max-w-3xl mx-auto">
        <AdminPageTitle
          includeDivider={false}
          icon={
            <span className="h-8 w-8 shrink-0 rounded bg-background-tint-02 flex items-center justify-center text-sm font-bold text-text-02">
              {displayName[0]}
            </span>
          }
          title={displayName}
        />

        {/* Step 0 – Configure */}
        {step === 0 && (
          <CardSection className="mt-4">
            <Text as="p" headingH3 className="pb-4">
              {t("admin.airbyteConnector.configureConnector")}
            </Text>

            {specError ? (
              <Text as="p" secondaryBody className="text-red-500">
                {t("admin.airbyteConnector.loadConfigFailed")}
                {t("admin.airbyteConnector.loadingConfig")}
              </Text>
            ) : !spec ? (
              <Text as="p" secondaryBody textLight05>
                Loading configuration form…
              </Text>
            ) : (
              <SchemaForm
                schema={spec.connection_specification}
                value={config}
                onChange={(v) =>
                  setConfig((v as Record<string, unknown>) ?? {})
                }
              />
            )}

            {validationMsg && (
              <Text as="p" secondaryBody className="text-red-500 text-sm mt-3">
                {validationMsg}
              </Text>
            )}

            <div className="flex justify-end mt-6">
              <Button
                primary
                onClick={handleValidateAndNext}
                disabled={validating || !spec}
              >
                {validating
                  ? t("admin.airbyteConnector.testingConnection")
                  : t("admin.airbyteConnector.testAndContinue")}
              </Button>
            </div>
          </CardSection>
        )}

        {/* Step 1 – Streams */}
        {step === 1 && (
          <CardSection className="mt-4">
            <Text as="p" headingH3 className="pb-4">
              {t("admin.airbyteConnector.steps.selectStreams")}
            </Text>

            {loadingStreams ? (
              <Text as="p" secondaryBody textLight05>
                {t("admin.airbyteConnector.discoveringStreams")}
              </Text>
            ) : streams.length === 0 ? (
              <Text as="p" secondaryBody textLight05>
                {t("admin.airbyteConnector.noStreams")}
              </Text>
            ) : (
              <>
                <div className="flex gap-3 mb-4">
                  <Button
                    size="md"
                    onClick={() =>
                      setSelectedStreams(new Set(streams.map((s) => s.name)))
                    }
                  >
                    {t("admin.airbyteConnector.selectAll")}
                  </Button>
                  <Button
                    size="md"
                    onClick={() => setSelectedStreams(new Set())}
                  >
                    {t("admin.airbyteConnector.deselectAll")}
                  </Button>
                </div>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {streams.map((stream) => (
                    <label
                      key={stream.name}
                      className="flex items-center gap-2 cursor-pointer"
                    >
                      <Checkbox
                        checked={selectedStreams.has(stream.name)}
                        onCheckedChange={(checked) => {
                          setSelectedStreams((prev) => {
                            const next = new Set(prev);
                            if (checked) next.add(stream.name);
                            else next.delete(stream.name);
                            return next;
                          });
                        }}
                      />
                      <Text as="span" secondaryBody>
                        {stream.name}
                      </Text>
                    </label>
                  ))}
                </div>
              </>
            )}

            <div className="flex justify-between mt-6">
              <Button onClick={() => setStep(0)}>
                {t("admin.airbyteConnector.back")}
              </Button>
              <Button primary onClick={() => setStep(2)}>
                {t("admin.airbyteConnector.continue")}
              </Button>
            </div>
          </CardSection>
        )}

        {/* Step 2 – Name & Confirm */}
        {step === 2 && (
          <CardSection className="mt-4">
            <Text as="p" headingH3 className="pb-4">
              {t("admin.airbyteConnector.steps.nameAndConfirm")}
            </Text>

            <div className="space-y-2 mb-6">
              <Text as="p" secondaryBody className="font-medium">
                {t("admin.airbyteConnector.datasourceName")}
              </Text>
              <InputTypeIn
                type="text"
                placeholder={t("admin.airbyteConnector.datasourcePlaceholder")}
                value={datasourceName}
                onChange={(e) => {
                  setDatasourceName(e.target.value);
                  if (nameError) setNameError(null);
                }}
                className={
                  nameError ? "border-red-500 focus:border-red-500" : ""
                }
              />
              {nameError && (
                <Text as="p" secondaryBody className="text-red-500 text-sm">
                  {nameError}
                </Text>
              )}
            </div>

            <div className="rounded-lg border border-border p-4 space-y-2 text-sm mb-6">
              <div className="flex justify-between">
                <Text as="span" secondaryBody textLight05>
                  {t("admin.airbyteConnector.summaryConnector")}
                </Text>
                <Text as="span" secondaryBody>
                  {displayName}
                </Text>
              </div>
              <div className="flex justify-between">
                <Text as="span" secondaryBody textLight05>
                  {t("admin.airbyteConnector.summaryStreams")}
                </Text>
                <Text as="span" secondaryBody>
                  {selectedStreams.size > 0
                    ? t("admin.airbyteConnector.selectedCount", {
                        count: selectedStreams.size,
                      })
                    : t("admin.airbyteConnector.all")}
                </Text>
              </div>
            </div>

            <div className="flex justify-between">
              <Button onClick={() => setStep(1)}>
                {t("admin.airbyteConnector.back")}
              </Button>
              <Button
                primary
                onClick={handleCreate}
                disabled={creating || !datasourceName.trim()}
              >
                {creating
                  ? t("admin.airbyteConnector.creating")
                  : t("admin.airbyteConnector.createDataSource")}
              </Button>
            </div>
          </CardSection>
        )}
      </div>
    </div>
  );
}
