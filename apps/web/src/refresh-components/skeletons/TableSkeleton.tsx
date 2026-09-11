import React from "react";
import { cn } from "@/lib/utils";
import {
  Table,
  TableHeader,
  TableRow,
  TableHead,
  TableBody,
  TableCell,
} from "@/components/ui/table";

export type SkeletonCellType =
  | "text"
  | "avatar"
  | "badge"
  | "actions"
  | "checkbox"
  | "icon-text";

export interface SkeletonColumn {
  type?: SkeletonCellType;
  width?: string;
  headerWidth?: string;
}

export interface TableSkeletonProps {
  rowCount?: number;
  columns?: SkeletonColumn[];
  hasHeader?: boolean;
  standalone?: boolean;
  className?: string;
  rowHeight?: string;
}

const DEFAULT_COLUMNS: SkeletonColumn[] = [
  { type: "icon-text", width: "w-48", headerWidth: "w-24" },
  { type: "text", width: "w-32", headerWidth: "w-20" },
  { type: "badge", width: "w-20", headerWidth: "w-16" },
  { type: "text", width: "w-24", headerWidth: "w-16" },
  { type: "actions", width: "w-16", headerWidth: "w-12" },
];

function renderCellSkeleton(col: SkeletonColumn) {
  const width = col.width || "w-28";

  switch (col.type) {
    case "checkbox":
      return (
        <div className="h-4 w-4 rounded-04 bg-background-tint-02 animate-pulse" />
      );
    case "avatar":
      return (
        <div className="flex items-center gap-2.5">
          <div className="h-8 w-8 rounded-full bg-background-tint-02 animate-pulse shrink-0" />
          <div className="flex flex-col gap-1.5">
            <div
              className={cn(
                "h-3.5 rounded bg-background-tint-02 animate-pulse",
                width
              )}
            />
            <div className="h-2.5 w-24 rounded bg-background-tint-02 animate-pulse opacity-70" />
          </div>
        </div>
      );
    case "icon-text":
      return (
        <div className="flex items-center gap-2.5">
          <div className="h-5 w-5 rounded bg-background-tint-02 animate-pulse shrink-0" />
          <div
            className={cn(
              "h-3.5 rounded bg-background-tint-02 animate-pulse",
              width
            )}
          />
        </div>
      );
    case "badge":
      return (
        <div
          className={cn(
            "h-6 rounded-full bg-background-tint-02 animate-pulse",
            width
          )}
        />
      );
    case "actions":
      return (
        <div className="flex items-center gap-2 justify-end">
          <div className="h-7 w-7 rounded-08 bg-background-tint-02 animate-pulse" />
          <div className="h-7 w-7 rounded-08 bg-background-tint-02 animate-pulse" />
        </div>
      );
    case "text":
    default:
      return (
        <div
          className={cn(
            "h-3.5 rounded bg-background-tint-02 animate-pulse",
            width
          )}
        />
      );
  }
}

export default function TableSkeleton({
  rowCount = 5,
  columns = DEFAULT_COLUMNS,
  hasHeader = true,
  standalone = true,
  className,
  rowHeight = "h-14",
}: TableSkeletonProps) {
  const rows = Array.from({ length: rowCount }).map((_, rowIndex) => (
    <TableRow
      key={rowIndex}
      className={cn(
        "border-b border-border-01 hover:bg-transparent",
        rowHeight
      )}
    >
      {columns.map((col, colIndex) => (
        <TableCell key={colIndex} className="py-3 px-4">
          {renderCellSkeleton(col)}
        </TableCell>
      ))}
    </TableRow>
  ));

  if (!standalone) {
    return <>{rows}</>;
  }

  return (
    <div
      className={cn(
        "w-full overflow-hidden rounded-08 border border-border-01 bg-background-neutral-00",
        className
      )}
      role="status"
      aria-label="Loading table data..."
    >
      <Table>
        {hasHeader && (
          <TableHeader>
            <TableRow className="border-b border-border-01 bg-background-neutral-01">
              {columns.map((col, index) => (
                <TableHead key={index} className="h-10 px-4">
                  <div
                    className={cn(
                      "h-3 rounded bg-background-tint-03 animate-pulse",
                      col.headerWidth || "w-20"
                    )}
                  />
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
        )}
        <TableBody>{rows}</TableBody>
      </Table>
    </div>
  );
}
