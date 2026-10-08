"use client";

import { useTranslation } from "react-i18next";
import { Interactive } from "@opal/core";
import { Tag } from "@opal/components";
import type { IconProps } from "@opal/types";
import { cn } from "@/lib/utils";
import Text from "@/refresh-components/texts/Text";

interface CollectionFacetRowProps {
  icon: React.FunctionComponent<IconProps>;
  tone: string;
  name: string;
  subtitle: string;
  count: number;
  pressed: boolean;
  failed?: boolean;
  onClick: () => void;
}

/** One row of the collection facet: icon, name, type, and hit count. */
export default function CollectionFacetRow({
  icon: Icon,
  tone,
  name,
  subtitle,
  count,
  pressed,
  failed = false,
  onClick,
}: CollectionFacetRowProps) {
  const { t } = useTranslation();
  return (
    <Interactive.Base
      variant="select"
      prominence="light"
      selected={pressed}
      group="group/FacetRow"
      onClick={onClick}
    >
      <Interactive.Container
        type="button"
        aria-pressed={pressed}
        heightVariant="fit"
        widthVariant="full"
        roundingVariant="default"
      >
        <span
          className={cn(
            "flex w-full items-center gap-2.5 rounded-12 border px-2.5 py-2 text-left transition-colors",
            pressed
              ? "border-action-link-05 bg-action-link-01"
              : "border-border-01 bg-background-neutral-01 group-hover/FacetRow:bg-background-tint-01"
          )}
        >
          <span
            className={cn(
              "flex h-7 w-7 shrink-0 items-center justify-center rounded-08",
              tone
            )}
          >
            <Icon className="h-4 w-4 stroke-inherit" />
          </span>
          <span className="flex min-w-0 flex-1 flex-col">
            <Text
              as="span"
              mainUiBody
              text05
              className={cn("truncate", pressed && "text-action-link-05")}
            >
              {name}
            </Text>
            <Text as="span" secondaryBody text02 className="truncate">
              {subtitle}
            </Text>
          </span>
          {failed && (
            <Tag title={t("knowledgeSearch.rail.failed")} color="amber" />
          )}
          <Text as="span" secondaryMono text03 className="tabular-nums">
            {count}
          </Text>
        </span>
      </Interactive.Container>
    </Interactive.Base>
  );
}
