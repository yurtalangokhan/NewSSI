"use client";

import { useCallback, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import { SvgExternalLink, SvgSearch } from "@opal/icons";
import { createFlowStore } from "../stores/flowStore";
import { FlowCanvas } from "../FlowCanvas";
import { FlowEditorShell } from "./FlowEditorShell";
import { useComponentTemplates } from "../hooks/useComponentTemplates";
import { useLoadFlowIntoStore } from "../hooks/useLoadFlowIntoStore";
import { useHandleTypeLookup } from "../hooks/useCanvasWiring";
import { createNodeTypes } from "../nodes/registry";
import EmptyMessage from "@/refresh-components/EmptyMessage";
import Tag from "@/refresh-components/buttons/Tag";
import Button from "@/refresh-components/buttons/Button";
import SimpleLoader from "@/refresh-components/loaders/SimpleLoader";

export interface FlowAgentPreviewProps {
  definitionId: string;
  agentId?: number | string;
  canEdit?: boolean;
  onEdit?: () => void;
}

export function FlowAgentPreview({
  definitionId,
  agentId,
  canEdit,
  onEdit,
}: FlowAgentPreviewProps) {
  const router = useRouter();
  const { t } = useTranslation();
  const store = useMemo(() => createFlowStore(), []);
  const { data: grouped } = useComponentTemplates();
  const lookupHandleTypes = useHandleTypeLookup(store, grouped);
  const nodeTypes = useMemo(() => createNodeTypes(store, true), [store]);

  // `published`, not `draft`: this panel shows the flow that actually runs
  // when someone chats with the agent. Reading the draft made it lie in
  // both directions — it showed in-progress, possibly-invalid edits, and
  // it reported "no flow designed" for every flow whose draft had been
  // consumed by a publish (the server promotes the draft row rather than
  // copying it) or discarded on exit.
  const handleEdit = useCallback(() => {
    if (onEdit) {
      onEdit();
      return;
    }
    router.push(`/app/flows/${definitionId}` as Route);
  }, [definitionId, onEdit, router]);

  const { isLoading, error, nodesCount, edgesCount } = useLoadFlowIntoStore(
    definitionId || null,
    store,
    { source: "published" }
  );

  if (isLoading) {
    return (
      <div className="flex h-56 w-full items-center justify-center rounded-12 border border-border-01 bg-background-tint-01">
        <SimpleLoader />
      </div>
    );
  }

  if (error || nodesCount === 0) {
    return (
      <div className="flex w-full items-center justify-center rounded-12 border border-border-01 bg-background-tint-01 p-4">
        <EmptyMessage
          icon={SvgSearch}
          title={t(
            "agentViewer.noFlowDesigned",
            "No flow designed for this agent yet."
          )}
        />
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Tag
            label={t("agentViewer.flowNodesCount", {
              count: nodesCount,
            })}
          />
          <Tag
            label={t("agentViewer.flowEdgesCount", {
              count: edgesCount,
            })}
          />
        </div>
        {canEdit && (
          <Button
            internal
            rightIcon={SvgExternalLink}
            size="md"
            onClick={handleEdit}
            data-testid="open-flow-editor-button"
          >
            {t("agentViewer.openFlowEditor", "Akış Düzenleyicisini Aç")}
          </Button>
        )}
      </div>

      <FlowEditorShell
        store={store}
        className="langflow-canvas relative h-80 w-full overflow-hidden rounded-12 border border-border-01 shadow-xs"
      >
        <FlowCanvas
          store={store}
          lookupHandleTypes={lookupHandleTypes}
          nodeTypes={nodeTypes}
          readOnly
          compact
        />
      </FlowEditorShell>
    </div>
  );
}
