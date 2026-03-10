"use client";

import React from "react";

/**
 * Recursively renders a configuration object as a key-value tree.
 * Nested objects are rendered as collapsible sections with indentation.
 * Primitive values (string, number, boolean) are displayed inline.
 * Arrays are displayed as comma-separated values or as nested items.
 */

function isPlainObject(val: unknown): val is Record<string, unknown> {
  return typeof val === "object" && val !== null && !Array.isArray(val);
}

function renderValue(value: unknown): React.ReactNode {
  if (value === null || value === undefined) {
    return <span className="text-muted-foreground italic">null</span>;
  }
  if (typeof value === "boolean") {
    return <span className="font-mono">{value ? "true" : "false"}</span>;
  }
  if (typeof value === "number") {
    return <span className="font-mono">{value}</span>;
  }
  if (typeof value === "string") {
    // Mask values that look like secrets
    const secretKeys =
      /password|secret|token|key|credential|connection_string/i;
    if (secretKeys.test(value)) {
      return <span className="font-mono">••••••••</span>;
    }
    return <span className="font-mono break-all">{value}</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-muted-foreground italic">[]</span>;
    if (value.every((v) => typeof v === "string" || typeof v === "number")) {
      return <span className="font-mono break-all">{value.join(", ")}</span>;
    }
    return (
      <div className="ml-4 space-y-1">
        {value.map((item, idx) => (
          <div key={idx} className="text-xs">
            {isPlainObject(item) ? (
              <ConfigTreeInner data={item} />
            ) : (
              renderValue(item)
            )}
          </div>
        ))}
      </div>
    );
  }
  if (isPlainObject(value)) {
    return <ConfigTreeInner data={value} />;
  }
  return <span className="font-mono">{String(value)}</span>;
}

function ConfigTreeInner({ data }: { data: Record<string, unknown> }) {
  const entries = Object.entries(data);
  if (entries.length === 0) {
    return <span className="text-muted-foreground italic">{"{}"}</span>;
  }

  return (
    <div className="space-y-1">
      {entries.map(([key, value]) => {
        // Mask keys that look like secrets
        const isSecret =
          /password|secret|token|key|credential|connection_string/i.test(key);

        if (isPlainObject(value)) {
          return (
            <div key={key}>
              <span className="text-xs text-muted-foreground font-medium">
                {key}
              </span>
              <div className="ml-4 mt-0.5 pl-2 border-l border-border">
                <ConfigTreeInner data={value} />
              </div>
            </div>
          );
        }

        return (
          <div key={key} className="flex justify-between text-xs gap-2">
            <span className="text-muted-foreground shrink-0">{key}</span>
            {isSecret ? (
              <span className="font-mono">••••••••</span>
            ) : (
              renderValue(value)
            )}
          </div>
        );
      })}
    </div>
  );
}

export function ConfigTree({ data }: { data: Record<string, unknown> }) {
  return <ConfigTreeInner data={data} />;
}
