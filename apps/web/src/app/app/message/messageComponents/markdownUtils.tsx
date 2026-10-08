import React, {
  useCallback,
  useMemo,
  useRef,
  JSX,
  type CSSProperties,
} from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeHighlight from "rehype-highlight";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import "@/app/app/message/custom-code-styles.css";
import { FullChatState } from "@/app/app/message/messageComponents/interfaces";
import {
  MemoizedAnchor,
  MemoizedParagraph,
} from "@/app/app/message/MemoizedTextComponents";
import { preprocessLaTeX } from "@/app/app/message/codeUtils";
import { MarkdownCode } from "@/components/chat/MarkdownCode";
import {
  buildMermaidFixRequest,
  type MermaidDiagnostic,
} from "@/components/mermaid/mermaidDiagnostics";
import { useTranslation } from "react-i18next";
import { MarkdownSourceProvider } from "@/components/chat/MarkdownSourceContext";
import { transformLinkUri, cn } from "@/lib/utils";
import { InMessageImage } from "@/app/app/components/files/images/InMessageImage";
import { extractChatImageFileId } from "@/app/app/components/files/images/utils";

export interface MarkdownRenderOptions {
  /** True while the text is still streaming; open Mermaid fences stay pending. */
  isStreaming?: boolean;
}

/**
 * Processes content for markdown rendering by handling code blocks and LaTeX
 */
export const processContent = (content: string): string => {
  const codeBlockRegex = /```(\w*)\n[\s\S]*?```|```[\s\S]*?$/g;
  const matches = content.match(codeBlockRegex);

  if (matches) {
    content = matches.reduce((acc, match) => {
      if (!match.match(/```\w+/)) {
        return acc.replace(match, match.replace("```", "```plaintext"));
      }
      return acc;
    }, content);

    const lastMatch = matches[matches.length - 1];
    if (lastMatch && !lastMatch.endsWith("```")) {
      return preprocessLaTeX(content);
    }
  }

  const processed = preprocessLaTeX(content);
  return processed;
};

/**
 * Hook that provides markdown component callbacks for consistent rendering.
 * The `code` renderer reads the parsed source from MarkdownSourceProvider
 * (set by renderMarkdown), so it stays stable while content streams.
 */
export const useMarkdownComponents = (
  state: FullChatState | undefined,
  className?: string,
  foregroundStyle?: CSSProperties
) => {
  const paragraphCallback = useCallback(
    (props: any) => (
      <MemoizedParagraph className={className} style={foregroundStyle}>
        {props.children}
      </MemoizedParagraph>
    ),
    [className, foregroundStyle]
  );

  // Read through a ref rather than depending on this state directly: any of
  // these fields (esp. citations) can change mid-stream, and a new
  // anchorCallback identity would rebuild markdownComponents, remounting
  // every code block (and a Mermaid diagram's state) on that update.
  const anchorStateRef = useRef({
    docs: state?.docs,
    userFiles: state?.userFiles,
    citations: state?.citations,
    setPresentingDocument: state?.setPresentingDocument,
  });
  anchorStateRef.current = {
    docs: state?.docs,
    userFiles: state?.userFiles,
    citations: state?.citations,
    setPresentingDocument: state?.setPresentingDocument,
  };

  const anchorCallback = useCallback((props: any) => {
    const imageFileId = extractChatImageFileId(
      props.href,
      String(props.children ?? "")
    );
    if (imageFileId) {
      return (
        <InMessageImage
          fileId={imageFileId}
          fileName={String(props.children ?? "")}
        />
      );
    }
    const { docs, userFiles, citations, setPresentingDocument } =
      anchorStateRef.current;
    return (
      <MemoizedAnchor
        updatePresentingDocument={setPresentingDocument || (() => {})}
        docs={docs || []}
        userFiles={userFiles || []}
        citations={citations}
        href={props.href}
      >
        {props.children}
      </MemoizedAnchor>
    );
  }, []);

  const { t } = useTranslation();
  const sendFollowUp = state?.onSendFollowUp;
  const requestFix = useMemo(
    () =>
      sendFollowUp
        ? (source: string, diagnostic: MermaidDiagnostic) =>
            sendFollowUp(buildMermaidFixRequest(t, source, diagnostic))
        : undefined,
    [sendFollowUp, t]
  );

  const markdownComponents = useMemo(
    () => ({
      a: anchorCallback,
      p: paragraphCallback,
      pre: ({ node, className, children }: any) => {
        // Don't render the pre wrapper - CodeBlock handles its own wrapper
        return <>{children}</>;
      },
      b: ({ node, className, children }: any) => {
        return <span className={className}>{children}</span>;
      },
      ul: ({ node, className, children, ...props }: any) => {
        return (
          <ul className={className} {...props}>
            {children}
          </ul>
        );
      },
      ol: ({ node, className, children, ...props }: any) => {
        return (
          <ol className={className} {...props}>
            {children}
          </ol>
        );
      },
      li: ({ node, className, children, ...props }: any) => {
        return (
          <li className={className} {...props}>
            {children}
          </li>
        );
      },
      table: ({ node, className, children, ...props }: any) => {
        return (
          <div className="markdown-table-breakout">
            <table className={cn(className, "min-w-full")} {...props}>
              {children}
            </table>
          </div>
        );
      },
      code: (props: any) => (
        <MarkdownCode
          {...props}
          mermaidVariant="chat"
          onRequestFix={requestFix}
        />
      ),
    }),
    [anchorCallback, paragraphCallback, requestFix]
  );

  return markdownComponents;
};

/**
 * Renders markdown content with consistent configuration
 */
export const renderMarkdown = (
  content: string,
  markdownComponents: any,
  textSize: string = "text-base",
  foregroundStyle?: CSSProperties,
  options: MarkdownRenderOptions = {}
): JSX.Element => {
  return (
    <MarkdownSourceProvider
      value={{ markdown: content, isStreaming: options.isStreaming ?? false }}
    >
      <div dir="auto" style={foregroundStyle}>
        <ReactMarkdown
          className={`prose dark:prose-invert font-main-content-body max-w-full ${textSize}`}
          components={markdownComponents}
          remarkPlugins={[
            remarkGfm,
            [remarkMath, { singleDollarTextMath: true }],
          ]}
          rehypePlugins={[rehypeHighlight, rehypeKatex]}
          urlTransform={transformLinkUri}
        >
          {content}
        </ReactMarkdown>
      </div>
    </MarkdownSourceProvider>
  );
};

/**
 * Complete markdown processing and rendering utility
 */
export const useMarkdownRenderer = (
  content: string,
  state: FullChatState | undefined,
  textSize: string,
  foregroundStyle?: CSSProperties,
  options: MarkdownRenderOptions = {}
) => {
  const isStreaming = options.isStreaming ?? false;
  const processedContent = useMemo(() => processContent(content), [content]);
  const markdownComponents = useMarkdownComponents(
    state,
    textSize,
    foregroundStyle
  );

  const renderedContent = useMemo(
    () =>
      renderMarkdown(
        processedContent,
        markdownComponents,
        textSize,
        foregroundStyle,
        { isStreaming }
      ),
    [
      processedContent,
      markdownComponents,
      textSize,
      foregroundStyle,
      isStreaming,
    ]
  );

  return {
    processedContent,
    markdownComponents,
    renderedContent,
  };
};
