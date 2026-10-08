"use client";

import { useTranslation } from "react-i18next";
import Skeleton from "@/refresh-components/skeletons/Skeleton";

const PLACEHOLDER_ROWS = [0, 1, 2];

/** Placeholder cards while the first search runs. */
export default function ResultListSkeleton() {
  const { t } = useTranslation();
  return (
    <div role="status" className="flex flex-col gap-2 px-4 py-2">
      <span className="sr-only">{t("knowledgeSearch.results.loading")}</span>
      {PLACEHOLDER_ROWS.map((row) => (
        <div key={row} className="flex flex-col gap-2 py-2" aria-hidden>
          <div className="flex items-center gap-2.5">
            <Skeleton className="h-[1.625rem] w-[1.625rem]" />
            <Skeleton className="h-4 w-1/2" />
          </div>
          <Skeleton className="h-3.5 w-1/3" />
          <Skeleton className="h-3.5 w-full" />
        </div>
      ))}
    </div>
  );
}
