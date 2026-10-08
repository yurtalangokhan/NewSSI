"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@opal/components";
import { SvgCheck, SvgSliders } from "@opal/icons";
import Popover, { PopoverMenu } from "@/refresh-components/Popover";
import LineItem from "@/refresh-components/buttons/LineItem";
import Text from "@/refresh-components/texts/Text";
import BlankIcon from "@/sections/knowledge-search/components/BlankIcon";
import { SEARCH_RESULT_LIMITS } from "@/lib/api/domains/knowledge/knowledge-search-types";

interface SearchSettingsPopoverProps {
  limit: number;
  onLimitChange: (limit: number) => void;
}

/** Search settings: how many fused results one search returns. */
export default function SearchSettingsPopover({
  limit,
  onLimitChange,
}: SearchSettingsPopoverProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <Button
          icon={SvgSliders}
          prominence="tertiary"
          size="md"
          tooltip={t("knowledgeSearch.settings.label")}
          aria-label={t("knowledgeSearch.settings.label")}
        />
      </Popover.Trigger>
      <Popover.Content align="end" width="lg">
        <PopoverMenu>
          {[
            <Text
              key="title"
              as="p"
              secondaryAction
              text03
              className="px-2 pt-1.5 pb-1"
            >
              {t("knowledgeSearch.settings.resultLimit")}
            </Text>,
            ...SEARCH_RESULT_LIMITS.map((option) => (
              <LineItem
                key={option}
                icon={option === limit ? SvgCheck : BlankIcon}
                selected={option === limit}
                emphasized
                onClick={() => {
                  onLimitChange(option);
                  setOpen(false);
                }}
              >
                {t("knowledgeSearch.settings.limitOption", { count: option })}
              </LineItem>
            )),
          ]}
        </PopoverMenu>
      </Popover.Content>
    </Popover>
  );
}
