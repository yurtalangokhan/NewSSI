import {
  MemoizedLink,
  MemoizedParagraph,
} from "@/app/app/message/MemoizedTextComponents";
import React, { useMemo, CSSProperties } from "react";
import ReactMarkdown, {
  type Components,
  type UrlTransform,
} from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { MarkdownCode } from "@/components/chat/MarkdownCode";
import type { MermaidDiagnostic } from "@/components/mermaid/mermaidDiagnostics";
import { MarkdownSourceProvider } from "@/components/chat/MarkdownSourceContext";
import { cn, transformLinkUri } from "@/lib/utils";

type MinimalMarkdownComponentOverrides = Partial<Components>;

interface MinimalMarkdownProps {
  content: string;
  className?: string;
  style?: CSSProperties;
  /**
   * Override specific markdown renderers.
   * Any renderer not provided will fall back to this component's defaults.
   */
  components?: MinimalMarkdownComponentOverrides;
  /**
   * True while `content` is still streaming in. Open Mermaid fences then stay
   * pending instead of rendering half a diagram.
   */
  isStreaming?: boolean;
  /** "Ask the agent to fix" on a broken diagram; the button is hidden when absent. */
  onRequestMermaidFix?: (source: string, diagnostic: MermaidDiagnostic) => void;
  /** Overrides how link and image URLs are vetted; defaults to the shared link rules. */
  urlTransform?: UrlTransform;
  /**
   * Keep the light typography palette. Required on a forced-light surface (the
   * document panel's white page): `dark:prose-invert` is class-based, so it
   * would still paint light text on the white sheet.
   */
  lightProse?: boolean;
}

export default function MinimalMarkdown({
  content,
  className = "",
  style,
  components,
  isStreaming = false,
  onRequestMermaidFix,
  urlTransform = transformLinkUri,
  lightProse = false,
}: MinimalMarkdownProps) {
  const markdownComponents = useMemo(() => {
    const defaults: Components = {
      a: MemoizedLink,
      p: MemoizedParagraph,
      pre: ({ node, className, children }: any) => {
        // Don't render the pre wrapper - CodeBlock handles its own wrapper
        return <>{children}</>;
      },
      // Stable across content changes: MarkdownCode reads the source from
      // MarkdownSourceProvider, so code blocks are not remounted per chunk.
      code: (props: any) => (
        <MarkdownCode
          {...props}
          mermaidVariant="document"
          onRequestFix={onRequestMermaidFix}
        />
      ),
    };

    return {
      ...defaults,
      ...(components ?? {}),
    } satisfies Components;
  }, [components, onRequestMermaidFix]);

  const sourceValue = useMemo(
    () => ({ markdown: content, isStreaming }),
    [content, isStreaming]
  );

  return (
    <MarkdownSourceProvider value={sourceValue}>
      <div style={style || {}} className={`${className}`}>
        <ReactMarkdown
          className={cn(
            "prose max-w-full text-sm break-words",
            !lightProse && "dark:prose-invert"
          )}
          components={markdownComponents}
          rehypePlugins={[rehypeHighlight, rehypeKatex]}
          remarkPlugins={[
            remarkGfm,
            [remarkMath, { singleDollarTextMath: false }],
          ]}
          urlTransform={urlTransform}
        >
          {content}
        </ReactMarkdown>
      </div>
    </MarkdownSourceProvider>
  );
}
