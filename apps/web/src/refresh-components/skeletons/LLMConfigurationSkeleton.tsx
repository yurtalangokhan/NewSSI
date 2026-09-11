import React from "react";
import Card from "@/refresh-components/cards/Card";
import Separator from "@/refresh-components/Separator";

export function LLMConfigurationSkeleton() {
  return (
    <div className="flex flex-col gap-6 md:gap-8 w-full">
      {/* ── 1. Varsayılan Model Kartı ── */}
      <Card>
        <div className="flex flex-row items-center justify-between w-full py-0.5">
          <div className="flex flex-col gap-1.5 flex-1 pr-4">
            <div className="h-4 w-36 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
            <div className="h-3 w-80 max-w-full rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-70" />
          </div>
          <div className="h-9 w-64 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse shrink-0" />
        </div>
      </Card>

      {/* ── 2. Yerleşik Sağlayıcılar (Ollama Panel) ── */}
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1">
          <div className="h-5 w-44 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
          <div className="h-3.5 w-80 max-w-full rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-70" />
        </div>

        {/* Ollama Panel Card */}
        <Card padding={0.75} className="w-full">
          {/* Header row: Icon, title, online badge, url, action buttons */}
          <div className="flex flex-row items-center justify-between w-full">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse shrink-0" />
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center gap-2">
                  <div className="h-4 w-36 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                  <div className="h-4 w-16 rounded-full bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                </div>
                <div className="h-3 w-48 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-70" />
              </div>
            </div>
            <div className="flex items-center gap-1">
              <div className="h-8 w-8 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
              <div className="h-8 w-8 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
            </div>
          </div>

          {/* Divider */}
          <div className="w-full mt-3 flex flex-col gap-3 border-t border-border-01 pt-3">
            {/* Status bar: Checkmark, online, version, model count */}
            <div className="flex items-center gap-3">
              <div className="h-4 w-4 rounded-full bg-background-tint-03 dark:bg-background-tint-04 animate-pulse shrink-0" />
              <div className="h-3.5 w-16 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
              <div className="h-3.5 w-24 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-70" />
              <div className="h-3.5 w-20 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-70" />
            </div>

            {/* Model rows (matching the Ollama models table in the user's screenshot) */}
            <div className="flex flex-col gap-1">
              {[
                { nameWidth: "w-48", tags: ["w-14"] },
                { nameWidth: "w-36", tags: ["w-14"] },
                { nameWidth: "w-40", tags: ["w-12", "w-16", "w-12"] },
                { nameWidth: "w-44", tags: ["w-16", "w-12"] },
                { nameWidth: "w-40", tags: ["w-12", "w-16", "w-12"] },
                { nameWidth: "w-36", tags: ["w-12", "w-12"] },
                { nameWidth: "w-48", tags: ["w-16", "w-12"] },
                { nameWidth: "w-44", tags: ["w-16", "w-12"] },
                { nameWidth: "w-48", tags: ["w-14"] },
              ].map((row, i) => (
                <div
                  key={i}
                  className="flex min-h-9 items-center gap-2 rounded-md px-2 py-1.5"
                >
                  {/* Model name */}
                  <div
                    className={`h-4 ${row.nameWidth} rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse shrink-0`}
                  />
                  {/* Capability tags */}
                  <div className="flex items-center gap-1">
                    {row.tags.map((tagW, tagI) => (
                      <div
                        key={tagI}
                        className={`h-4 ${tagW} rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-80`}
                      />
                    ))}
                  </div>
                  <div className="flex-1" />
                  {/* Context tokens */}
                  <div className="h-3.5 w-24 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-70 mr-2" />
                  {/* Model size */}
                  <div className="h-3.5 w-14 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-70 mr-1" />
                  {/* Trash button */}
                  <div className="h-7 w-7 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse shrink-0" />
                </div>
              ))}
            </div>
          </div>
        </Card>
      </div>

      <Separator noPadding />

      {/* ── 3. Yerel / Self-Hosted Sağlayıcılar ── */}
      <div className="flex flex-col gap-3">
        <div className="flex justify-between items-center">
          <div className="flex flex-col gap-1">
            <div className="h-5 w-52 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
            <div className="h-3.5 w-80 max-w-full rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-70" />
          </div>
          <div className="h-9 w-32 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
        </div>
        <Card padding={0.5}>
          <div className="flex flex-row items-center justify-between w-full py-1">
            <div className="flex items-center gap-3">
              <div className="h-10 w-10 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse shrink-0" />
              <div className="flex flex-col gap-1.5">
                <div className="h-4 w-32 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
                <div className="h-3 w-48 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-70" />
              </div>
            </div>
            <div className="h-8 w-20 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
          </div>
        </Card>
      </div>

      <Separator noPadding />

      {/* ── 4. Bulut Sağlayıcılar ── */}
      <div className="flex flex-col gap-3">
        <div className="flex justify-between items-center">
          <div className="flex flex-col gap-1">
            <div className="h-5 w-44 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
            <div className="h-3.5 w-80 max-w-full rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-70" />
          </div>
          <div className="h-9 w-32 rounded-08 bg-background-tint-03 dark:bg-background-tint-04 animate-pulse" />
        </div>
        <div className="h-14 w-full rounded-16 border border-dashed border-border-01 flex items-center justify-center">
          <div className="h-3.5 w-48 rounded bg-background-tint-03 dark:bg-background-tint-04 animate-pulse opacity-60" />
        </div>
      </div>
    </div>
  );
}

export default LLMConfigurationSkeleton;
