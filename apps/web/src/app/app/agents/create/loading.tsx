"use client";

import * as AppLayouts from "@/layouts/app-layouts";
import AgentEditorSkeleton from "@/refresh-components/skeletons/AgentEditorSkeleton";

export default function Loading() {
  return (
    <AppLayouts.Root>
      <AgentEditorSkeleton isEditing={false} />
    </AppLayouts.Root>
  );
}
