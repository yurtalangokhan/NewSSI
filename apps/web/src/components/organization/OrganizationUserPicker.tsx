"use client";
import { accessEndpoints } from "@/lib/api/domains/access/endpoints";

import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import useSWR from "swr";

import { fetchOrganizationAssignableUsers } from "@/lib/api/domains/access/api";
import Button from "@/refresh-components/buttons/Button";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";

interface Candidate {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  username?: string;
}
interface Props {
  organizationId: string;
  onSelect: (id: string) => void;
}
function label(user: Candidate) {
  return [
    [user.first_name, user.last_name].filter(Boolean).join(" "),
    user.email || user.username,
  ]
    .filter(Boolean)
    .join(" · ");
}
export function OrganizationUserPicker({ organizationId, onSelect }: Props) {
  const { t } = useTranslation();
  const listId = useId();
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(query.trim()), 250);
    return () => window.clearTimeout(timer);
  }, [query]);
  const { data, error, isLoading } = useSWR(
    open
      ? accessEndpoints.organizationAssignableUsers(organizationId, search)
          .browserPath
      : null,
    () => fetchOrganizationAssignableUsers(organizationId, search)
  );
  const loading = isLoading || query.trim() !== search;
  const users = loading || error ? [] : data?.users ?? [];
  const activeId = users[active]?.id;
  useEffect(() => {
    if (open && activeId)
      document
        .getElementById(`${listId}-${activeId}`)
        ?.scrollIntoView?.({ block: "nearest" });
  }, [activeId, listId, open]);
  function choose(user: Candidate) {
    setQuery(label(user));
    setOpen(false);
    onSelect(user.id);
  }
  return (
    <div
      className={cn("relative min-w-0")}
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null))
          setOpen(false);
      }}
    >
      <InputTypeIn
        role="combobox"
        aria-label={t("admin.organizations.users.user")}
        aria-autocomplete="list"
        aria-controls={listId}
        aria-expanded={open}
        aria-activedescendant={
          open && users[active] ? `${listId}-${users[active]!.id}` : undefined
        }
        placeholder={t("admin.organizations.users.searchUser")}
        leftSearchIcon
        value={query}
        onFocus={() => setOpen(true)}
        onChange={(event) => {
          setQuery(event.target.value);
          onSelect("");
          setActive(-1);
          setOpen(true);
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            setOpen(false);
            return;
          }
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
            setActive((index) => {
              if (!users.length) return -1;
              if (index < 0)
                return event.key === "ArrowDown" ? 0 : users.length - 1;
              return (
                (index + (event.key === "ArrowDown" ? 1 : -1) + users.length) %
                users.length
              );
            });
          } else if (event.key === "Enter" && open && users[active]) {
            event.preventDefault();
            choose(users[active]!);
          }
        }}
      />
      {open && (
        <div
          className={cn(
            "absolute inset-x-0 top-full z-50 mt-1 max-h-80 overflow-y-auto rounded-08 border border-border-02 bg-background-neutral-00 p-1 shadow-lg"
          )}
        >
          <div
            id={listId}
            role="listbox"
            aria-label={t("admin.organizations.users.user")}
          >
            {users.map((user, index) => (
              <Button
                key={user.id}
                id={`${listId}-${user.id}`}
                role="option"
                aria-selected={active === index}
                tertiary
                className={cn(
                  "w-full justify-start",
                  active === index && "bg-background-neutral-02"
                )}
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => choose(user)}
              >
                {label(user)}
              </Button>
            ))}
          </div>
          {(loading || error || !users.length) && (
            <Text as="p" role="status" secondaryBody>
              {t(
                loading
                  ? "admin.organizations.users.searchLoading"
                  : error
                    ? "admin.organizations.users.searchFailed"
                    : "admin.organizations.users.noCandidates"
              )}
            </Text>
          )}
          {!loading && !error && data && data.total > users.length && (
            <Text as="p" secondaryBody>
              {t("admin.organizations.users.refineSearch")}
            </Text>
          )}
        </div>
      )}
    </div>
  );
}
