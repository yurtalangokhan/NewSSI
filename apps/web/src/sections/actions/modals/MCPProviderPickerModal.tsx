"use client";

import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import Button from "@/refresh-components/buttons/Button";
import InputTypeIn from "@/refresh-components/inputs/InputTypeIn";
import Modal from "@/refresh-components/Modal";
import Text from "@/refresh-components/texts/Text";
import { useModal } from "@/refresh-components/contexts/ModalContext";
import { MCPServer } from "@/lib/tools/interfaces";
import { isRegisteredMcpProvider } from "@/lib/tools/mcpUtils";
import { cn } from "@/lib/utils";
import { SvgArrowRight, SvgCheck, SvgMcp } from "@opal/icons";

interface MCPProviderPickerModalProps {
  skipOverlay?: boolean;
  /** Providers a system admin already registered (built-in excluded). */
  providers: MCPServer[];
  onSelect: (server: MCPServer) => void;
}

/** Host part of a server URL ("mcp.deepwiki.com"); falls back to the raw value. */
function hostOf(serverUrl: string): string {
  try {
    return new URL(serverUrl).host;
  } catch {
    return serverUrl;
  }
}

/**
 * Enterprise-admin entry point into "Add MCP server": pick a provider a system
 * admin registered, then supply credentials in the auth modal. There is
 * deliberately no URL field — new URLs are system-admin territory.
 */
export default function MCPProviderPickerModal({
  skipOverlay = false,
  providers,
  onSelect,
}: MCPProviderPickerModalProps) {
  const { t } = useTranslation();
  const { isOpen, toggle } = useModal();
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return providers;
    return providers.filter((provider) =>
      [provider.name, provider.server_url].join(" ").toLowerCase().includes(q)
    );
  }, [providers, query]);

  return (
    <Modal open={isOpen} onOpenChange={toggle}>
      <Modal.Content width="sm" skipOverlay={skipOverlay}>
        <Modal.Header
          icon={SvgMcp}
          title={t("admin.mcp.pickProviderTitle", {
            defaultValue: "Select an MCP server",
          })}
          description={t("admin.mcp.pickProviderDescription", {
            defaultValue:
              "Choose a server registered by a system admin, then add its credentials.",
          })}
          onClose={() => toggle(false)}
        />
        <Modal.Body>
          <InputTypeIn
            leftSearchIcon
            value={query}
            placeholder={t("admin.mcp.searchServersPlaceholder")}
            onChange={(event) => setQuery(event.target.value)}
          />
          {filtered.length === 0 ? (
            <Text
              as="p"
              secondaryBody
              text03
              className="py-8 text-center max-w-sm mx-auto"
            >
              {t("admin.mcp.noProvidersAvailable", {
                defaultValue:
                  "No MCP servers are available to connect yet. Ask a system admin to register one.",
              })}
            </Text>
          ) : (
            <ul className="flex flex-col gap-2 max-h-[22rem] overflow-y-auto -mx-1 px-1 py-1">
              {filtered.map((provider) => {
                // Only a merely registered provider can be added. One that is
                // already on the actions list (connected, awaiting auth, ...)
                // is managed from its card, so show it inert and labelled.
                const alreadyAdded = !isRegisteredMcpProvider(provider);
                const host = hostOf(provider.server_url);
                return (
                  <li key={provider.id}>
                    <button
                      type="button"
                      disabled={alreadyAdded}
                      onClick={() => onSelect(provider)}
                      className={cn(
                        "group flex w-full items-center gap-3 rounded-12 border p-3 text-left",
                        "transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-border-05",
                        alreadyAdded
                          ? "cursor-default border-border-01 bg-background-tint-00"
                          : "border-border-01 bg-background-neutral-00 hover:border-border-03 hover:bg-background-tint-01"
                      )}
                    >
                      <span
                        className={cn(
                          "flex size-10 shrink-0 items-center justify-center rounded-08 border",
                          alreadyAdded
                            ? "border-border-01 bg-background-tint-01 text-text-03"
                            : "border-border-01 bg-background-tint-01 text-text-05"
                        )}
                      >
                        <SvgMcp className="size-5 stroke-current" />
                      </span>

                      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                        <Text
                          as="p"
                          mainUiAction
                          text04={alreadyAdded}
                          text05={!alreadyAdded}
                          className="truncate"
                        >
                          {provider.name}
                        </Text>
                        {provider.description && (
                          <Text
                            as="p"
                            secondaryBody
                            text03
                            className="line-clamp-2 break-words"
                          >
                            {provider.description}
                          </Text>
                        )}
                        <Text
                          as="p"
                          secondaryMono
                          text02
                          className="truncate pt-0.5"
                        >
                          {host}
                        </Text>
                      </span>

                      {alreadyAdded ? (
                        <span className="inline-flex shrink-0 items-center gap-1 rounded-full border border-status-success-02 bg-status-success-00 px-2 py-0.5 text-status-success-05">
                          <SvgCheck className="size-3.5 stroke-current" />
                          <Text as="span" secondaryBody>
                            {t("admin.mcp.alreadyAdded", {
                              defaultValue: "Added",
                            })}
                          </Text>
                        </span>
                      ) : (
                        <SvgArrowRight className="size-4 shrink-0 stroke-text-03 transition-transform group-hover:translate-x-0.5 group-hover:stroke-text-05" />
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Modal.Body>
        <Modal.Footer>
          <Button secondary onClick={() => toggle(false)}>
            {t("modals.cancel")}
          </Button>
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
