"use client";

import { useAppMode } from "@/providers/AppModeProvider";
import KnowledgeSearchView from "@/sections/knowledge-search/KnowledgeSearchView";

/** The search mode of a new session; a new session starts a fresh search view. */
export default function KnowledgeSearchMode() {
  const { searchSessionKey } = useAppMode();

  // The incoming screen fades in: switching between search and chat (and
  // starting a new search session, via `searchSessionKey`) reads as a
  // transition instead of a hard cut. Fades only, no slide: this root fills the
  // app's `overflow-auto` content area, where a transient offset would make the
  // scrollbar flash.
  return (
    <div className="h-full w-full overflow-y-auto animate-in fade-in duration-200 motion-reduce:animate-none">
      <KnowledgeSearchView key={searchSessionKey} />
    </div>
  );
}
