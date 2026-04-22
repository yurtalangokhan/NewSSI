"use client";

import { useEffect, useRef } from "react";

interface DocxPreviewProps {
  blob: Blob;
  className?: string;
}

export default function DocxPreview({ blob, className }: DocxPreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || !blob) return;

    let cancelled = false;

    import("docx-preview").then(({ renderAsync }) => {
      if (cancelled || !containerRef.current) return;
      renderAsync(blob, containerRef.current, undefined, {
        className: "docx",
        inWrapper: true,
        ignoreWidth: false,
        ignoreHeight: false,
        breakPages: true,
        renderHeaders: true,
        renderFooters: true,
        renderFootnotes: true,
        renderEndnotes: true,
      }).catch(console.error);
    });

    return () => {
      cancelled = true;
    };
  }, [blob]);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ background: "#f5f5f5" }}
    />
  );
}
