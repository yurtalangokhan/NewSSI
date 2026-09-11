/**
 * CompositionValidator Component
 * Displays validation results for agent composition in real-time.
 */

"use client";

import { useEffect } from "react";
import { Card } from "@/refresh-components/cards";
import Text from "@/refresh-components/texts/Text";
import * as GeneralLayouts from "@/layouts/general-layouts";
import { SvgAlertTriangle, SvgCheckCircle, SvgInfo } from "@opal/icons";
import SimpleLoader from "@/refresh-components/loaders/SimpleLoader";
import { useCompositionValidation } from "@/hooks/useCompositionValidation";
import { useTranslation } from "react-i18next";

interface CompositionValidatorProps {
  agentId?: string | null;
  graphSchema: string;
  subAgentIds: string[];
  enabled?: boolean;
  onValidationChange?: (isValid: boolean, depth: number) => void;
}

export default function CompositionValidator({
  agentId,
  graphSchema,
  subAgentIds,
  enabled = true,
  onValidationChange,
}: CompositionValidatorProps) {
  const { t } = useTranslation();
  const { validate, isValidating, errors, warnings, depth, isValid } =
    useCompositionValidation({
      enabled,
    });

  // Trigger validation when dependencies change
  useEffect(() => {
    validate(agentId ?? null, graphSchema, subAgentIds);
  }, [agentId, graphSchema, subAgentIds, validate]);

  // Notify parent of validation changes
  useEffect(() => {
    onValidationChange?.(isValid, depth);
  }, [isValid, depth, onValidationChange]);

  if (subAgentIds.length === 0) {
    return null; // Don't show if no agents selected
  }

  return (
    <GeneralLayouts.Section gap={1} width="full">
      {/* Validation Status */}
      {isValidating ? (
        <Card className="p-4 border border-neutral-200 dark:border-neutral-700">
          <GeneralLayouts.Section
            flexDirection="row"
            alignItems="center"
            gap={1}
          >
            <SimpleLoader />
            <Text mainUiMuted text03>
              {t("agentEditor.validatingComposition")}
            </Text>
          </GeneralLayouts.Section>
        </Card>
      ) : isValid ? (
        <Card className="bg-green-50 dark:bg-green-950 border border-green-300 dark:border-green-700 p-4">
          <GeneralLayouts.Section
            flexDirection="row"
            alignItems="center"
            gap={1}
          >
            <SvgCheckCircle className="w-5 h-5 text-green-600 dark:text-green-400" />
            <GeneralLayouts.Section gap={0.25}>
              <Text mainUiAction text03>
                {t("agentEditor.compositionValid")}
              </Text>
              {depth > 0 && (
                <Text mainUiMuted text04>
                  {t("agentEditor.compositionDepth", { depth })}
                </Text>
              )}
            </GeneralLayouts.Section>
          </GeneralLayouts.Section>
        </Card>
      ) : (
        <Card className="bg-red-50 dark:bg-red-950 border border-red-300 dark:border-red-700 p-4">
          <GeneralLayouts.Section
            flexDirection="row"
            alignItems="start"
            gap={1}
          >
            <SvgAlertTriangle className="w-5 h-5 text-red-600 dark:text-red-400 flex-shrink-0" />
            <GeneralLayouts.Section gap={0.5}>
              <Text
                mainUiAction
                text03
                className="text-red-700 dark:text-red-300"
              >
                {t("agentEditor.compositionInvalid")}
              </Text>
              {errors.length > 0 && (
                <GeneralLayouts.Section gap={0.25}>
                  {errors.map((error, idx) => (
                    <Text
                      key={idx}
                      mainUiMuted
                      text04
                      className="text-red-700 dark:text-red-300"
                    >
                      • {error}
                    </Text>
                  ))}
                </GeneralLayouts.Section>
              )}
            </GeneralLayouts.Section>
          </GeneralLayouts.Section>
        </Card>
      )}

      {/* Warnings */}
      {warnings.length > 0 && (
        <Card className="bg-amber-50 dark:bg-amber-950 border border-amber-300 dark:border-amber-700 p-4">
          <GeneralLayouts.Section
            flexDirection="row"
            alignItems="start"
            gap={1}
          >
            <SvgInfo className="w-5 h-5 text-amber-600 dark:text-amber-400 flex-shrink-0" />
            <GeneralLayouts.Section gap={0.5}>
              <Text
                mainUiAction
                text03
                className="text-amber-700 dark:text-amber-300"
              >
                {t("agentEditor.warningsFound")}
              </Text>
              <GeneralLayouts.Section gap={0.25}>
                {warnings.map((warning, idx) => (
                  <Text
                    key={idx}
                    mainUiMuted
                    text04
                    className="text-amber-700 dark:text-amber-300"
                  >
                    ⚠ {warning}
                  </Text>
                ))}
              </GeneralLayouts.Section>
            </GeneralLayouts.Section>
          </GeneralLayouts.Section>
        </Card>
      )}

      {/* Depth Info Card */}
      {depth > 0 && (
        <Card className="p-3 border border-neutral-200 dark:border-neutral-700">
          <GeneralLayouts.Section
            flexDirection="row"
            alignItems="center"
            gap={1}
          >
            <SvgInfo className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            <Text mainUiMuted text04>
              {t("agentEditor.hierarchyDepth", { depth })}
            </Text>
          </GeneralLayouts.Section>
        </Card>
      )}
    </GeneralLayouts.Section>
  );
}
