"use client";

import SimpleTabs from "@/refresh-components/SimpleTabs";
import * as SettingsLayouts from "@/layouts/settings-layouts";
import Text from "@/components/ui/text";
import { useState } from "react";
import {
  insertGlobalTokenRateLimit,
  insertGroupTokenRateLimit,
  insertUserTokenRateLimit,
} from "./lib";
import { Scope, TokenRateLimit } from "./types";
import { GenericTokenRateLimitTable } from "./TokenRateLimitTables";
import { mutate } from "swr";
import { toast } from "@/hooks/useToast";
import CreateRateLimitModal from "./CreateRateLimitModal";
import { usePaidEnterpriseFeaturesEnabled } from "@/components/settings/usePaidEnterpriseFeaturesEnabled";
import CreateButton from "@/refresh-components/buttons/CreateButton";
import { SvgGlobe, SvgUser, SvgUsers } from "@opal/icons";
import { Section } from "@/layouts/general-layouts";
import { ADMIN_ROUTE_CONFIG, ADMIN_PATHS } from "@/lib/admin-routes";
import { useTranslation } from "react-i18next";

const route = ADMIN_ROUTE_CONFIG[ADMIN_PATHS.TOKEN_RATE_LIMITS]!;
const BASE_URL = "/api/admin/token-rate-limits";
const GLOBAL_TOKEN_FETCH_URL = `${BASE_URL}/global`;
const USER_TOKEN_FETCH_URL = `${BASE_URL}/users`;
const USER_GROUP_FETCH_URL = `${BASE_URL}/user-groups`;

const GLOBAL_DESCRIPTION =
  "Global rate limits apply to all users, user groups, and API keys. When the global \
  rate limit is reached, no more tokens can be spent.";
const USER_DESCRIPTION =
  "User rate limits apply to individual users. When a user reaches a limit, they will \
  be temporarily blocked from spending tokens.";
const USER_GROUP_DESCRIPTION =
  "User group rate limits apply to all users in a group. When a group reaches a limit, \
  all users in the group will be temporarily blocked from spending tokens, regardless \
  of their individual limits. If a user is in multiple groups, the most lenient limit \
  will apply.";

const handleCreateTokenRateLimit = async (
  target_scope: Scope,
  period_hours: number,
  token_budget: number,
  group_id: number = -1
) => {
  const tokenRateLimitArgs = {
    enabled: true,
    token_budget: token_budget,
    period_hours: period_hours,
  };

  if (target_scope === Scope.GLOBAL) {
    return await insertGlobalTokenRateLimit(tokenRateLimitArgs);
  } else if (target_scope === Scope.USER) {
    return await insertUserTokenRateLimit(tokenRateLimitArgs);
  } else if (target_scope === Scope.USER_GROUP) {
    return await insertGroupTokenRateLimit(tokenRateLimitArgs, group_id);
  } else {
    throw new Error(`Invalid target_scope: ${target_scope}`);
  }
};

function Main() {
  const { t } = useTranslation();
  const [tabIndex, setTabIndex] = useState(0);
  const [modalIsOpen, setModalIsOpen] = useState(false);

  const isPaidEnterpriseFeaturesEnabled = usePaidEnterpriseFeaturesEnabled();

  const updateTable = (target_scope: Scope) => {
    if (target_scope === Scope.GLOBAL) {
      mutate(GLOBAL_TOKEN_FETCH_URL);
      setTabIndex(0);
    } else if (target_scope === Scope.USER) {
      mutate(USER_TOKEN_FETCH_URL);
      setTabIndex(1);
    } else if (target_scope === Scope.USER_GROUP) {
      mutate(USER_GROUP_FETCH_URL);
      setTabIndex(2);
    }
  };

  const handleSubmit = (
    target_scope: Scope,
    period_hours: number,
    token_budget: number,
    group_id: number = -1
  ) => {
    handleCreateTokenRateLimit(
      target_scope,
      period_hours,
      token_budget,
      group_id
    )
      .then(() => {
        setModalIsOpen(false);
        toast.success(t("admin.tokenRateLimits.createdSuccess"));
        updateTable(target_scope);
      })
      .catch((error) => {
        toast.error(error.message);
      });
  };

  return (
    <Section alignItems="stretch" justifyContent="start" height="auto">
      <Text>{t("admin.tokenRateLimits.description")}</Text>

      <ul className="list-disc ml-4">
        <li>
          <Text>{t("admin.tokenRateLimits.globalRateLimit")}</Text>
        </li>
        {isPaidEnterpriseFeaturesEnabled && (
          <>
            <li>
              <Text>{t("admin.tokenRateLimits.userRateLimit")}</Text>
            </li>
            <li>
              <Text>{t("admin.tokenRateLimits.groupRateLimit")}</Text>
            </li>
          </>
        )}
        <li>
          <Text>{t("admin.tokenRateLimits.enableDisable")}</Text>
        </li>
      </ul>

      <CreateButton onClick={() => setModalIsOpen(true)}>
        {t("admin.tokenRateLimits.createButton")}
      </CreateButton>

      {isPaidEnterpriseFeaturesEnabled ? (
        <SimpleTabs
          tabs={{
            "0": {
              name: t("admin.tokenRateLimits.globalTab"),
              icon: SvgGlobe,
              content: (
                <GenericTokenRateLimitTable
                  fetchUrl={GLOBAL_TOKEN_FETCH_URL}
                  title={t("admin.tokenRateLimits.globalTitle")}
                  description={t("admin.tokenRateLimits.globalDescription")}
                />
              ),
            },
            "1": {
              name: t("admin.tokenRateLimits.userTab"),
              icon: SvgUser,
              content: (
                <GenericTokenRateLimitTable
                  fetchUrl={USER_TOKEN_FETCH_URL}
                  title={t("admin.tokenRateLimits.userTitle")}
                  description={t("admin.tokenRateLimits.userDescription")}
                />
              ),
            },
            "2": {
              name: t("admin.tokenRateLimits.userGroupsTab"),
              icon: SvgUsers,
              content: (
                <GenericTokenRateLimitTable
                  fetchUrl={USER_GROUP_FETCH_URL}
                  title={t("admin.tokenRateLimits.groupTitle")}
                  description={t("admin.tokenRateLimits.groupDescription")}
                  responseMapper={(data: Record<string, TokenRateLimit[]>) =>
                    Object.entries(data).flatMap(([group_name, elements]) =>
                      elements.map((element) => ({
                        ...element,
                        group_name,
                      }))
                    )
                  }
                />
              ),
            },
          }}
          value={tabIndex.toString()}
          onValueChange={(val) => setTabIndex(parseInt(val))}
        />
      ) : (
        <GenericTokenRateLimitTable
          fetchUrl={GLOBAL_TOKEN_FETCH_URL}
          title={t("admin.tokenRateLimits.globalTitle")}
          description={t("admin.tokenRateLimits.globalDescription")}
        />
      )}

      <CreateRateLimitModal
        isOpen={modalIsOpen}
        setIsOpen={() => setModalIsOpen(false)}
        onSubmit={handleSubmit}
        forSpecificScope={
          isPaidEnterpriseFeaturesEnabled ? undefined : Scope.GLOBAL
        }
      />
    </Section>
  );
}

export default function Page() {
  return (
    <SettingsLayouts.Root>
      <SettingsLayouts.Header title={route.title} icon={route.icon} separator />
      <SettingsLayouts.Body>
        <Main />
      </SettingsLayouts.Body>
    </SettingsLayouts.Root>
  );
}
