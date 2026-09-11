"use client";

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import * as InputLayouts from "@/layouts/input-layouts";
import Switch from "@/refresh-components/inputs/Switch";
import Message from "@/refresh-components/messages/Message";

export interface AgentVisibilityFieldsProps {
  isPublic: boolean;
  featured: boolean;
  canFeature: boolean;
  onChange: (next: { isPublic: boolean; featured: boolean }) => void;
  /** The editor passes its "share with people" button here; the creation
   * modal passes nothing — sharing needs an agent id that does not exist
   * yet at that point. */
  footer?: ReactNode;
  /** i18n key prefix for the four labels. Flows say "this flow", agents
   * say "this agent" — same controls, the noun follows the caller. */
  labelNamespace?: "agentEditor" | "flowSettings";
}

/**
 * Public/featured switches, lifted out of AgentEditorPage's advanced
 * options card so the flow creation modal can offer the same two toggles
 * without a Formik context.
 */
export default function AgentVisibilityFields({
  isPublic,
  featured,
  canFeature,
  onChange,
  footer,
  labelNamespace = "agentEditor",
}: AgentVisibilityFieldsProps) {
  const { t } = useTranslation();
  const label = (key: string) => t(`${labelNamespace}.${key}`);

  return (
    <>
      {footer && (
        <InputLayouts.Horizontal
          title={label("shareThisAgentLabel")}
          description={label("shareThisAgentDescription")}
          center
        >
          {footer}
        </InputLayouts.Horizontal>
      )}
      {!footer && (
        <InputLayouts.Horizontal
          title={label("shareThisAgentLabel")}
          description={label("shareThisAgentDescription")}
          center
        >
          <Switch
            data-testid="agent-visibility-public"
            checked={isPublic}
            onCheckedChange={(checked) =>
              onChange({ isPublic: checked, featured })
            }
          />
        </InputLayouts.Horizontal>
      )}
      {canFeature && (
        <>
          <InputLayouts.Horizontal
            title={label("featureThisAgentLabel")}
            description={label("featureThisAgentDescription")}
          >
            <Switch
              data-testid="agent-visibility-featured"
              checked={featured}
              onCheckedChange={(checked) =>
                onChange({ isPublic, featured: checked })
              }
            />
          </InputLayouts.Horizontal>
          {featured && !isPublic && (
            <Message
              static
              close={false}
              className="w-full"
              text={label("agentPrivateWarning")}
            />
          )}
        </>
      )}
    </>
  );
}
