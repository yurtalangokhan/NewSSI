"use client";

import {
  NodeResizer,
  NodeToolbar as XyNodeToolbar,
  Position,
  type NodeProps,
} from "@xyflow/react";
import { memo, useCallback, useState, useEffect, type SVGProps } from "react";
import { useTranslation } from "react-i18next";
import { useStore, type StoreApi } from "zustand";
import { SvgCopy, SvgTrash } from "@opal/icons";
import IconButton from "@/refresh-components/buttons/IconButton";
import { cn } from "@/lib/utils";
import { NoteColorPicker, NoteTextArea } from "../components/NoteControls";
import type { CanvasNode } from "../types/flow";
import type { FlowStore } from "../stores/flowStore";

function SvgCopyPlus(props: SVGProps<SVGSVGElement>) {
  return (
    <span className="relative inline-flex">
      <SvgCopy {...props} />
      <svg
        viewBox="0 0 8 8"
        aria-hidden
        className="absolute -bottom-0.5 -right-0.5 h-2 w-2 text-current"
      >
        <path
          d="M4 1v6M1 4h6"
          stroke="currentColor"
          strokeWidth={1.5}
          strokeLinecap="round"
        />
      </svg>
    </span>
  );
}

const NOTE_COLORS: Record<
  string,
  { bg: string; border: string; text: string; dot: string; label: string }
> = {
  yellow: {
    label: "Yellow",
    bg: "bg-note-yellow-bg",
    border: "border-note-yellow-border",
    text: "text-note-yellow-text",
    dot: "bg-note-yellow-dot border-note-yellow-dot-border",
  },
  blue: {
    label: "Blue",
    bg: "bg-note-blue-bg",
    border: "border-note-blue-border",
    text: "text-note-blue-text",
    dot: "bg-note-blue-dot border-note-blue-dot-border",
  },
  green: {
    label: "Green",
    bg: "bg-note-green-bg",
    border: "border-note-green-border",
    text: "text-note-green-text",
    dot: "bg-note-green-dot border-note-green-dot-border",
  },
  pink: {
    label: "Pink",
    bg: "bg-note-pink-bg",
    border: "border-note-pink-border",
    text: "text-note-pink-text",
    dot: "bg-note-pink-dot border-note-pink-dot-border",
  },
  purple: {
    label: "Purple",
    bg: "bg-note-purple-bg",
    border: "border-note-purple-border",
    text: "text-note-purple-text",
    dot: "bg-note-purple-dot border-note-purple-dot-border",
  },
  neutral: {
    label: "Neutral",
    bg: "bg-note-neutral-bg",
    border: "border-note-neutral-border",
    text: "text-note-neutral-text",
    dot: "bg-note-neutral-dot border-note-neutral-dot-border",
  },
};

export function createNoteNode(
  store: StoreApi<FlowStore>,
  readOnly: boolean = false
) {
  return memo(function NoteNode({ id, data, selected }: NodeProps<CanvasNode>) {
    const { t } = useTranslation();
    const setNodeValues = useStore(store, (s) => s.setNodeValues);
    const takeSnapshot = useStore(store, (s) => s.takeSnapshot);
    const paste = useStore(store, (s) => s.paste);
    const setClipboard = useStore(store, (s) => s.setClipboard);
    const setNodes = useStore(store, (s) => s.setNodes);
    const nodes = useStore(store, (s) => s.nodes);

    const [colorMenuOpen, setColorMenuOpen] = useState(false);

    const values = (data?.values ?? {}) as Record<string, unknown>;
    const storeText =
      typeof values.text === "string"
        ? values.text
        : typeof (data as unknown as Record<string, unknown>).text === "string"
          ? ((data as unknown as Record<string, unknown>).text as string)
          : "";

    const [localText, setLocalText] = useState(storeText);

    useEffect(() => {
      setLocalText(storeText);
    }, [storeText]);

    const colorKey =
      typeof values.color === "string" && values.color in NOTE_COLORS
        ? values.color
        : "yellow";
    const colorStyle = NOTE_COLORS[colorKey] ?? NOTE_COLORS.yellow!;

    const handleTextChange = useCallback(
      (e: React.ChangeEvent<HTMLTextAreaElement>) => {
        const newText = e.target.value;
        setLocalText(newText);
        setNodeValues(id, { text: newText });
      },
      [id, setNodeValues]
    );

    const handleColorChange = useCallback(
      (newColor: string) => {
        takeSnapshot();
        setNodeValues(id, { color: newColor });
        setColorMenuOpen(false);
      },
      [id, takeSnapshot, setNodeValues]
    );

    const handleDelete = useCallback(() => {
      takeSnapshot();
      setNodes((current) => current.filter((n) => n.id !== id));
    }, [id, takeSnapshot, setNodes]);

    const handleCopy = useCallback(() => {
      const self = nodes.find((n) => n.id === id);
      if (self) {
        setClipboard({ nodes: [self], edges: [] });
      }
    }, [id, nodes, setClipboard]);

    const handleDuplicate = useCallback(() => {
      const self = nodes.find((n) => n.id === id);
      if (self) {
        takeSnapshot();
        paste(
          { nodes: [self], edges: [] },
          { x: self.position.x + 30, y: self.position.y + 30 }
        );
      }
    }, [id, nodes, takeSnapshot, paste]);

    const isMac =
      typeof window !== "undefined" &&
      /macintosh|mac os x/i.test(navigator.userAgent);

    return (
      <div
        className={cn(
          "group/note relative flex h-full w-full min-h-[120px] min-w-[200px] flex-col rounded-xl border p-3 transition-shadow",
          colorStyle.bg,
          colorStyle.border,
          colorStyle.text,
          !readOnly && (selected ? "shadow-lg" : "shadow-sm hover:shadow-md"),
          readOnly && "pointer-events-none select-none"
        )}
      >
        <NodeResizer
          minWidth={180}
          minHeight={100}
          isVisible={!readOnly && Boolean(selected)}
          lineClassName="!border-transparent"
          handleClassName="!h-2 !w-2 !rounded-full !border !border-border !bg-canvas-panel"
        />

        {/* Floating Toolbar above Note when selected (matches cards NodeToolbar) */}
        {!readOnly && selected && (
          <XyNodeToolbar nodeId={id} position={Position.Top}>
            <div
              className="nodrag flex items-center gap-1 rounded-08 border border-canvas-border bg-canvas-panel p-1 shadow-md"
              data-testid={`note-toolbar-${id}`}
            >
              {/* Color Picker Popover */}
              <NoteColorPicker
                colors={NOTE_COLORS}
                activeColorKey={colorKey}
                activeDotClassName={colorStyle.dot}
                open={colorMenuOpen}
                onOpenChange={setColorMenuOpen}
                onSelect={handleColorChange}
              />

              <div className="h-4 w-px bg-border my-auto" />

              <IconButton
                icon={SvgCopyPlus}
                tooltip={`${t(
                  "flowCanvas.stickyNote.duplicate",
                  "Duplicate"
                )} (${isMac ? "⌘D" : "Ctrl+D"})`}
                aria-label={t("flowCanvas.stickyNote.duplicate", "Duplicate")}
                onClick={handleDuplicate}
                small
              />
              <IconButton
                icon={SvgCopy}
                tooltip={`${t("flowCanvas.nodeToolbar.copy", "Copy")} (${
                  isMac ? "⌘C" : "Ctrl+C"
                })`}
                aria-label={t("flowCanvas.nodeToolbar.copy", "Copy")}
                onClick={handleCopy}
                small
              />
              <IconButton
                icon={SvgTrash}
                tooltip={`${t("flowCanvas.stickyNote.delete", "Delete")} (${
                  isMac ? "⌫" : "Del"
                })`}
                aria-label={t("flowCanvas.stickyNote.delete", "Delete")}
                onClick={handleDelete}
                small
              />
            </div>
          </XyNodeToolbar>
        )}

        {/* Note Text Content */}
        <NoteTextArea
          value={localText}
          onChange={handleTextChange}
          className={colorStyle.text}
        />
      </div>
    );
  });
}
