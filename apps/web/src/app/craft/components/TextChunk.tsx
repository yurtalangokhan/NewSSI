"use client";

import MinimalMarkdown from "@/components/chat/MinimalMarkdown";

interface TextChunkProps {
  content: string;
  /** True while this chunk's text is still arriving; keeps open Mermaid fences pending. */
  isStreaming?: boolean;
}

/**
 * TextChunk - Renders markdown text content
 *
 * Uses MinimalMarkdown for consistent rendering with the main chat.
 */
export default function TextChunk({
  content,
  isStreaming = false,
}: TextChunkProps) {
  if (!content) return null;

  return (
    <div className="py-1">
      <MinimalMarkdown
        content={content}
        className="text-text-05"
        isStreaming={isStreaming}
      />
    </div>
  );
}
