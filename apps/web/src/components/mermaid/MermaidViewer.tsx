"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import type React from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgRefreshCw, SvgZoomIn, SvgZoomOut } from "@/icons";
import Modal from "@/refresh-components/Modal";
import Text from "@/refresh-components/texts/Text";
import { sanitizeMermaidSvg } from "@/components/mermaid/mermaidSanitize";
import {
  createSvgScopeId,
  rescopeSvgIds,
} from "@/components/mermaid/mermaidSvg";
import {
  INITIAL_VIEWPORT,
  MAX_SCALE,
  MIN_SCALE,
  keyToViewportAction,
  normalizeWheelDelta,
  viewportReducer,
} from "@/components/mermaid/mermaidViewport";

interface MermaidViewerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** The on-page SVG copy; the viewer renders its own rescoped copy. */
  svg: string;
  /** The scope id currently used inside `svg`. */
  svgScopeId: string;
}

/**
 * A large Radix dialog rather than the Fullscreen API, which the app's
 * Permissions-Policy (`fullscreen=()`) forbids.
 */
export function MermaidViewer({
  open,
  onOpenChange,
  title,
  svg,
  svgScopeId,
}: MermaidViewerProps) {
  const { t } = useTranslation();
  const [viewerScopeId] = useState(createSvgScopeId);
  const [viewport, dispatch] = useReducer(viewportReducer, INITIAL_VIEWPORT);
  // A callback ref, not a plain useRef: Radix mounts the dialog content one
  // render after `open` flips (Presence), so an effect keyed on `open` would
  // read a stale `null` .current. Tracking the node in state re-runs the
  // wheel-listener effect exactly when the real element appears. The mutable
  // ref stays in sync for handlers that need the node immediately, before
  // the state update triggered by the same callback has re-rendered.
  const [canvasNode, setCanvasNode] = useState<HTMLDivElement | null>(null);
  const canvasNodeRef = useRef<HTMLDivElement | null>(null);
  const canvasRef = useCallback((node: HTMLDivElement | null) => {
    canvasNodeRef.current = node;
    setCanvasNode(node);
  }, []);
  const drag = useRef<{ x: number; y: number } | null>(null);
  const markup = useMemo(
    () => sanitizeMermaidSvg(rescopeSvgIds(svg, svgScopeId, viewerScopeId)),
    [svg, svgScopeId, viewerScopeId]
  );

  useEffect(() => {
    if (open) dispatch({ type: "reset" });
  }, [open]);

  function originOf(clientX: number, clientY: number) {
    const rect = canvasNodeRef.current?.getBoundingClientRect();
    if (!rect) return { x: 0, y: 0 };
    return {
      x: clientX - rect.left - rect.width / 2,
      y: clientY - rect.top - rect.height / 2,
    };
  }

  // React's onWheel is a passive listener, so it cannot preventDefault to
  // stop the ctrl/meta+wheel or trackpad-pinch browser page zoom. A native
  // listener with `{ passive: false }` is required.
  //
  // Convention (matches Figma/Google Maps/most canvas editors): a plain
  // wheel or two-finger trackpad swipe pans the canvas along both axes;
  // ctrl+wheel, meta+wheel or a pinch gesture (browsers report pinch as
  // wheel + ctrlKey) zooms around the cursor.
  useEffect(() => {
    if (!canvasNode) return undefined;
    const canvas = canvasNode;

    function handleNativeWheel(event: WheelEvent) {
      event.preventDefault();
      const deltaX = normalizeWheelDelta(
        event.deltaX,
        event.deltaMode,
        canvas.clientWidth
      );
      const deltaY = normalizeWheelDelta(
        event.deltaY,
        event.deltaMode,
        canvas.clientHeight
      );
      if (event.ctrlKey || event.metaKey) {
        const origin = originOf(event.clientX, event.clientY);
        dispatch({
          type: "wheel",
          deltaY,
          originX: origin.x,
          originY: origin.y,
        });
        return;
      }
      dispatch({ type: "pan", dx: -deltaX, dy: -deltaY });
    }

    canvasNode.addEventListener("wheel", handleNativeWheel, {
      passive: false,
    });
    return () => canvasNode.removeEventListener("wheel", handleNativeWheel);
  }, [canvasNode]);

  function handleKeyDown(event: React.KeyboardEvent<HTMLDivElement>) {
    const action = keyToViewportAction(event.key);
    if (!action) return;
    event.preventDefault();
    dispatch(action);
  }

  function handlePointerDown(event: React.PointerEvent<HTMLDivElement>) {
    if (event.button !== 0 || !event.isPrimary) return;
    drag.current = { x: event.clientX, y: event.clientY };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function handlePointerMove(event: React.PointerEvent<HTMLDivElement>) {
    if (!drag.current) return;
    dispatch({
      type: "pan",
      dx: event.clientX - drag.current.x,
      dy: event.clientY - drag.current.y,
    });
    drag.current = { x: event.clientX, y: event.clientY };
  }

  function endDrag() {
    drag.current = null;
  }

  return (
    <Modal open={open} onOpenChange={onOpenChange}>
      <Modal.Content
        width="lg"
        height="full"
        onOpenAutoFocus={(event) => {
          event.preventDefault();
          canvasNodeRef.current?.focus();
        }}
      >
        <Modal.Header title={title} onClose={() => onOpenChange(false)}>
          <div className="flex items-center gap-1">
            <Button
              size="sm"
              prominence="tertiary"
              icon={SvgZoomOut}
              tooltip={t("mermaid.viewer.zoomOut")}
              aria-label={t("mermaid.viewer.zoomOut")}
              disabled={viewport.scale <= MIN_SCALE}
              onClick={() => dispatch({ type: "zoomOut" })}
            />
            <Text
              secondaryMono
              text03
              aria-live="polite"
              data-testid="mermaid-viewer-zoom"
              className="min-w-12 text-center"
            >
              {t("mermaid.viewer.zoomLevel", {
                percent: Math.round(viewport.scale * 100),
              })}
            </Text>
            <Button
              size="sm"
              prominence="tertiary"
              icon={SvgZoomIn}
              tooltip={t("mermaid.viewer.zoomIn")}
              aria-label={t("mermaid.viewer.zoomIn")}
              disabled={viewport.scale >= MAX_SCALE}
              onClick={() => dispatch({ type: "zoomIn" })}
            />
            <Button
              size="sm"
              prominence="tertiary"
              icon={SvgRefreshCw}
              tooltip={t("mermaid.viewer.resetZoom")}
              aria-label={t("mermaid.viewer.resetZoom")}
              onClick={() => dispatch({ type: "reset" })}
            />
          </div>
        </Modal.Header>
        <div
          ref={canvasRef}
          role="region"
          aria-label={t("mermaid.viewer.canvas")}
          tabIndex={0}
          data-testid="mermaid-viewer-canvas"
          className="relative flex min-h-[60dvh] flex-1 cursor-grab touch-none items-center justify-center overflow-hidden bg-background-tint-00 outline-none focus-visible:ring-2 focus-visible:ring-action-link-05 active:cursor-grabbing"
          onKeyDown={handleKeyDown}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={endDrag}
          onPointerCancel={endDrag}
        >
          <div
            data-testid="mermaid-viewer-content"
            className="[&_svg]:h-auto [&_svg]:max-w-none"
            style={{
              transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.scale})`,
              transformOrigin: "center center",
            }}
            dangerouslySetInnerHTML={{ __html: markup }}
          />
        </div>
      </Modal.Content>
    </Modal>
  );
}
