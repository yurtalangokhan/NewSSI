"use client";

import { Fragment, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import MinimalMarkdown from "@/components/chat/MinimalMarkdown";
import type { BlockDiffEntry } from "@/lib/documents/diff/blockDiff";
import {
  describeModification,
  InlineSegment,
  TableDiff,
} from "@/lib/documents/diff/inlineDiff";
import { cn } from "@/lib/utils";
import { fenceCode } from "@/sections/document-panel/fence";
import Text from "@/refresh-components/texts/Text";

const STATUS_CLASS = {
  added: "border-l-2 border-status-success-05 bg-status-success-00",
  removed: "border-l-2 border-status-error-05 bg-status-error-00 opacity-80",
  modified: "border-l-2 border-status-warning-05 bg-status-warning-00",
} as const;

interface SegmentsProps {
  segments: InlineSegment[];
}

function Segments({ segments }: SegmentsProps) {
  return (
    <Text as="p" mainContentBody>
      {segments.map((segment, i) =>
        segment.kind === "ins" ? (
          <ins
            key={i}
            className="no-underline bg-status-success-01 text-status-text-success-05 rounded-04"
          >
            {segment.value}
          </ins>
        ) : segment.kind === "del" ? (
          <del
            key={i}
            className="bg-status-error-01 text-status-text-error-05 rounded-04"
          >
            {segment.value}
          </del>
        ) : (
          <Fragment key={i}>{segment.value}</Fragment>
        )
      )}
    </Text>
  );
}

interface TableChangesProps {
  table: TableDiff;
}

function TableChanges({ table }: TableChangesProps) {
  const { t } = useTranslation();
  const rows = [table.header, ...table.rows];
  return (
    <div className="flex flex-col gap-1">
      <Text as="p" secondaryBody text03>
        {t("documentPanel.changes.table", {
          cells: table.changedCells,
          added: table.addedRows,
          removed: table.removedRows,
        })}
      </Text>
      <table className="w-full text-sm border-collapse">
        <tbody>
          {rows.map((row, r) => (
            <tr
              key={r}
              className={cn(
                row.status === "added" && "bg-status-success-01",
                row.status === "removed" && "bg-status-error-01"
              )}
            >
              {row.cells.map((cell, c) => (
                <td
                  key={c}
                  className={cn(
                    "border border-border-01 px-2 py-1",
                    r === 0 && "font-semibold"
                  )}
                >
                  {cell.kind === "changed" ? (
                    <Segments segments={cell.segments} />
                  ) : (
                    cell.after ?? cell.before
                  )}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface ModifiedBlockProps {
  entry: BlockDiffEntry;
}

function ModifiedBlock({ entry }: ModifiedBlockProps) {
  const { t } = useTranslation();
  const modification = describeModification(entry);
  if (modification.kind === "text")
    return <Segments segments={modification.segments} />;
  if (modification.kind === "table")
    return <TableChanges table={modification.table} />;
  const lang =
    entry.after!.type === "mermaid"
      ? "mermaid"
      : entry.after!.type === "code"
        ? ""
        : null;
  const asMarkdown = (body: string) =>
    lang === null ? body : fenceCode(body, lang);
  return (
    <div className="flex flex-col gap-1">
      {entry.after!.type === "mermaid" && (
        <Text as="p" secondaryBody text03>
          {t("documentPanel.changes.diagram")}
        </Text>
      )}
      <div className="grid grid-cols-2 gap-2">
        {(
          [
            ["before", modification.before],
            ["after", modification.after],
          ] as const
        ).map(([side, body]) => (
          <div key={side} className="flex flex-col gap-1 min-w-0">
            <Text as="p" figureSmallLabel text03>
              {t(`documentPanel.changes.${side}`)}
            </Text>
            <MinimalMarkdown content={asMarkdown(body)} />
          </div>
        ))}
      </div>
    </div>
  );
}

type Row =
  | { kind: "run"; entries: BlockDiffEntry[]; key: string }
  | { kind: "block"; entry: BlockDiffEntry; key: string };

function toRows(entries: BlockDiffEntry[]): Row[] {
  const rows: Row[] = [];
  entries.forEach((entry, i) => {
    const last = rows[rows.length - 1];
    if (entry.status === "unchanged" && last?.kind === "run")
      last.entries.push(entry);
    else if (entry.status === "unchanged")
      rows.push({ kind: "run", entries: [entry], key: `run-${i}` });
    else rows.push({ kind: "block", entry, key: `block-${i}` });
  });
  return rows;
}

interface RenderedDiffProps {
  entries: BlockDiffEntry[];
}

export function RenderedDiff({ entries }: RenderedDiffProps) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  return (
    <div className="flex flex-col gap-2">
      {toRows(entries).map((row) => {
        if (row.kind === "run") {
          if (expanded.has(row.key)) {
            return (
              <div key={row.key} className="opacity-70">
                <MinimalMarkdown
                  content={row.entries.map((e) => e.after!.source).join("\n\n")}
                />
              </div>
            );
          }
          return (
            <Button
              key={row.key}
              size="sm"
              prominence="tertiary"
              onClick={() => setExpanded((prev) => new Set(prev).add(row.key))}
            >
              {t("documentPanel.changes.unchangedRun", {
                count: row.entries.length,
              })}
            </Button>
          );
        }
        const { entry } = row;
        return (
          <div
            key={row.key}
            data-testid="diff-block"
            data-status={entry.status}
            className={cn(
              "rounded-08 px-3 py-2",
              STATUS_CLASS[entry.status as keyof typeof STATUS_CLASS]
            )}
          >
            <Text as="p" figureSmallLabel text03>
              {t(`documentPanel.changes.status.${entry.status}`)}
            </Text>
            {entry.status === "modified" ? (
              <ModifiedBlock entry={entry} />
            ) : (
              <MinimalMarkdown
                content={(entry.after ?? entry.before)!.source}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
