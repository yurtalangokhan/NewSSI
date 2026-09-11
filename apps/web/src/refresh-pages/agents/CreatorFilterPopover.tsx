"use client";

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useUser } from "@/providers/UserProvider";
import type { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import { UNKNOWN_AGENT_OWNER_EMAIL } from "@/lib/agents";
import Popover, { PopoverMenu } from "@/refresh-components/Popover";
import FilterButton from "@/refresh-components/buttons/FilterButton";
import LineItem from "@/refresh-components/buttons/LineItem";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import { SvgCheck, SvgUser } from "@opal/icons";

export const UNKNOWN_OWNER_FILTER_ID = "__unknown_owner__";

export function creatorFilterId(
  owner: { id: string; email: string } | null | undefined
) {
  if (!owner) return undefined;
  return owner.email === UNKNOWN_AGENT_OWNER_EMAIL
    ? UNKNOWN_OWNER_FILTER_ID
    : owner.id;
}

export interface CreatorFilterPopoverProps {
  agents: MinimalPersonaSnapshot[];
  selectedCreatorIds: Set<string>;
  setSelectedCreatorIds: React.Dispatch<React.SetStateAction<Set<string>>>;
}

export default function CreatorFilterPopover({
  agents,
  selectedCreatorIds,
  setSelectedCreatorIds,
}: CreatorFilterPopoverProps) {
  const { t } = useTranslation();
  const { user } = useUser();
  const [creatorFilterOpen, setCreatorFilterOpen] = useState(false);
  const [creatorSearchQuery, setCreatorSearchQuery] = useState("");

  const uniqueCreators = useMemo(() => {
    const creatorsMap = new Map<string, { id: string; email: string }>();
    agents.forEach((agent) => {
      if (!agent.owner) return;
      const id = creatorFilterId(agent.owner);
      if (!id) return;
      if (id === UNKNOWN_OWNER_FILTER_ID) {
        creatorsMap.set(id, { id, email: t("agentsPage.unknownOwner") });
      } else {
        creatorsMap.set(id, agent.owner);
      }
    });

    let creators = Array.from(creatorsMap.values()).sort((a, b) =>
      a.email.localeCompare(b.email)
    );

    // Add current user if not in the list, and put them first
    if (user) {
      const userInList = creators.some((c) => c.id === user.id);
      if (!userInList && user.email) {
        creators = [{ id: user.id, email: user.email }, ...creators];
      } else {
        creators.sort((a, b) => {
          if (a.id === user.id) return -1;
          if (b.id === user.id) return 1;
          return 0;
        });
      }
    }

    return creators;
  }, [agents, user, t]);

  const filteredCreators = useMemo(() => {
    if (!creatorSearchQuery) return uniqueCreators;

    return uniqueCreators.filter((creator) =>
      creator.email.toLowerCase().includes(creatorSearchQuery.toLowerCase())
    );
  }, [uniqueCreators, creatorSearchQuery]);

  const creatorFilterButtonText = useMemo(() => {
    if (selectedCreatorIds.size === 0) {
      return t("agentsPage.creatorFilterEveryone");
    } else if (selectedCreatorIds.size === 1) {
      const selectedId = Array.from(selectedCreatorIds)[0];
      const creator = uniqueCreators.find((c) => c.id === selectedId);
      return creator
        ? t("agentsPage.creatorFilterBy", { email: creator.email })
        : t("agentsPage.creatorFilterEveryone");
    } else {
      return t("agentsPage.creatorFilterCount", {
        count: selectedCreatorIds.size,
      });
    }
  }, [selectedCreatorIds, uniqueCreators, t]);

  return (
    <Popover open={creatorFilterOpen} onOpenChange={setCreatorFilterOpen}>
      <Popover.Trigger asChild>
        <FilterButton
          leftIcon={SvgUser}
          active={selectedCreatorIds.size > 0}
          transient={creatorFilterOpen}
          onClear={() => setSelectedCreatorIds(new Set())}
        >
          {creatorFilterButtonText}
        </FilterButton>
      </Popover.Trigger>
      <Popover.Content align="end">
        <PopoverMenu>
          {[
            <InputTypeIn
              key="created-by"
              placeholder={t("agentsPage.createdByPlaceholder")}
              variant="internal"
              leftSearchIcon
              value={creatorSearchQuery}
              onChange={(e) => setCreatorSearchQuery(e.target.value)}
            />,
            ...filteredCreators.flatMap((creator, index) => {
              const isSelected = selectedCreatorIds.has(creator.id);
              const isCurrentUser = user && creator.id === user.id;

              const nextCreator = filteredCreators[index + 1];
              const nextIsCurrentUser =
                user && nextCreator && nextCreator.id === user.id;
              const needsSeparator =
                isCurrentUser && nextCreator && !nextIsCurrentUser;

              const icon = isCurrentUser
                ? SvgUser
                : isSelected
                  ? SvgCheck
                  : () => null;

              const lineItem = (
                <LineItem
                  key={creator.id}
                  icon={icon}
                  selected={isSelected}
                  emphasized
                  onClick={() => {
                    setSelectedCreatorIds((prev) => {
                      const newSet = new Set(prev);
                      if (newSet.has(creator.id)) {
                        newSet.delete(creator.id);
                      } else {
                        newSet.add(creator.id);
                      }
                      return newSet;
                    });
                  }}
                >
                  {creator.email}
                </LineItem>
              );

              return needsSeparator ? [lineItem, null] : [lineItem];
            }),
          ]}
        </PopoverMenu>
      </Popover.Content>
    </Popover>
  );
}
