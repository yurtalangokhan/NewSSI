"use client";

import { usePathname } from "next/navigation";
import { useSettingsContext } from "@/providers/SettingsProvider";
import { CgArrowsExpandUpLeft } from "react-icons/cg";
import Text from "@/refresh-components/texts/Text";
import SidebarSection from "@/sections/sidebar/SidebarSection";
import SidebarWrapper from "@/sections/sidebar/SidebarWrapper";
import { useIsKGExposed } from "@/app/admin/kg/utils";
import { useCustomAnalyticsEnabled } from "@/lib/hooks/useCustomAnalyticsEnabled";
import { useUser } from "@/providers/UserProvider";
import { UserRole } from "@/lib/types";
import {
  useBillingInformation,
  useLicense,
  hasActiveSubscription,
} from "@/lib/billing";
import { usePaidEnterpriseFeaturesEnabled } from "@/components/settings/usePaidEnterpriseFeaturesEnabled";
import { CombinedSettings } from "@/interfaces/settings";
import SidebarTab from "@/refresh-components/buttons/SidebarTab";
import SidebarBody from "@/sections/sidebar/SidebarBody";
import { SvgArrowUpCircle } from "@opal/icons";
import { ADMIN_PATHS, sidebarItem } from "@/lib/admin-routes";
import UserAvatarPopover from "@/sections/sidebar/UserAvatarPopover";
import { useTranslation } from "react-i18next";

const connectors_items = (
  t: (key: string, options?: { defaultValue?: string }) => string
) => [
  sidebarItem(ADMIN_PATHS.INDEXING_STATUS, t),
  sidebarItem(ADMIN_PATHS.ADD_CONNECTOR, t),
];

const document_management_items = (
  t: (key: string, options?: { defaultValue?: string }) => string
) => [
  sidebarItem(ADMIN_PATHS.DOCUMENT_SETS, t),
  sidebarItem(ADMIN_PATHS.DOCUMENT_EXPLORER, t),
];

const custom_agents_items = (
  t: (key: string, options?: { defaultValue?: string }) => string,
  isCurator: boolean,
  enableEnterprise: boolean
) => {
  const items = [sidebarItem(ADMIN_PATHS.AGENTS, t)];

  if (!isCurator) {}

  items.push(
    sidebarItem(ADMIN_PATHS.MCP_ACTIONS, t)
  );

  if (enableEnterprise) {
    items.push(sidebarItem(ADMIN_PATHS.STANDARD_ANSWERS, t));
  }

  return items;
};

const collections = (
  t: (key: string, options?: { defaultValue?: string }) => string,
  isCurator: boolean,
  enableCloud: boolean,
  enableEnterprise: boolean,
  settings: CombinedSettings | null,
  kgExposed: boolean,
  customAnalyticsEnabled: boolean,
  hasSubscription: boolean
) => {
  const vectorDbEnabled = settings?.settings.vector_db_enabled !== false;

  return [
    ...(vectorDbEnabled
      ? [
          {
            name: t("admin.navigation.sections.connectors"),
            items: connectors_items(t),
          },
        ]
      : []),
    ...(vectorDbEnabled
      ? [
          {
            name: t("admin.navigation.sections.documentManagement"),
            items: document_management_items(t),
          },
        ]
      : []),
    {
      name: t("admin.navigation.sections.customAgents"),
      items: custom_agents_items(t, isCurator, enableEnterprise),
    },
    ...(isCurator && enableEnterprise
      ? [
          {
            name: t("admin.navigation.sections.userManagement"),
            items: [sidebarItem(ADMIN_PATHS.GROUPS, t)],
          },
        ]
      : []),
    ...(!isCurator
      ? [
          {
            name: t("admin.navigation.sections.configuration"),
            items: [
              sidebarItem(ADMIN_PATHS.CHAT_PREFERENCES, t),
              sidebarItem(ADMIN_PATHS.LLM_MODELS, t),
              sidebarItem(ADMIN_PATHS.WEB_SEARCH, t),
              sidebarItem(ADMIN_PATHS.IMAGE_GENERATION, t),
              sidebarItem(ADMIN_PATHS.CODE_INTERPRETER, t),
              ...(!enableCloud && vectorDbEnabled
                ? [
                    {
                      ...sidebarItem(ADMIN_PATHS.SEARCH_SETTINGS, t),
                      error: settings?.settings.needs_reindexing,
                    },
                  ]
                : []),
              sidebarItem(ADMIN_PATHS.DOCUMENT_PROCESSING, t),
              ...(kgExposed ? [sidebarItem(ADMIN_PATHS.KNOWLEDGE_GRAPH, t)] : []),
            ],
          },
          {
            name: t("admin.navigation.sections.userManagement"),
            items: [
              sidebarItem(ADMIN_PATHS.USERS, t),
              ...(enableEnterprise ? [sidebarItem(ADMIN_PATHS.GROUPS, t)] : []),
              sidebarItem(ADMIN_PATHS.API_KEYS, t),
            ],
          },
          ...(enableEnterprise
            ? [
                {
                  name: t("admin.navigation.sections.performance"),
                  items: [
                    sidebarItem(ADMIN_PATHS.USAGE, t),
                    ...(settings?.settings.query_history_type !== "disabled"
                      ? [sidebarItem(ADMIN_PATHS.QUERY_HISTORY, t)]
                      : []),
                    ...(!enableCloud && customAnalyticsEnabled
                      ? [sidebarItem(ADMIN_PATHS.CUSTOM_ANALYTICS, t)]
                      : []),
                  ],
                },
              ]
            : []),
          {
            name: t("admin.navigation.sections.settings"),
            items: [
              ...(enableEnterprise ? [sidebarItem(ADMIN_PATHS.THEME, t)] : []),
              ...(settings?.settings.opensearch_indexing_enabled
                ? [sidebarItem(ADMIN_PATHS.INDEX_MIGRATION, t)]
                : []),
            ],
          },
        ]
      : []),
  ];
};

interface AdminSidebarProps {
  // Cloud flag is passed from server component (Layout.tsx) since it's a build-time constant
  enableCloudSS: boolean;
  // Enterprise flag is also passed but we override it with runtime license check below
  enableEnterpriseSS: boolean;
}

export default function AdminSidebar({
  enableCloudSS,
  enableEnterpriseSS,
}: AdminSidebarProps) {
  const { t } = useTranslation();
  const { kgExposed } = useIsKGExposed();
  const pathname = usePathname();
  const { customAnalyticsEnabled } = useCustomAnalyticsEnabled();
  const { user } = useUser();
  const settings = useSettingsContext();
  const { data: billingData } = useBillingInformation();
  const { data: licenseData } = useLicense();

  // Use runtime license check for enterprise features
  // This checks settings.ee_features_enabled (set by backend based on license status)
  // Falls back to build-time check if LICENSE_ENFORCEMENT_ENABLED=false
  const enableEnterprise = usePaidEnterpriseFeaturesEnabled();

  const isCurator =
    user?.role === UserRole.CURATOR || user?.role === UserRole.GLOBAL_CURATOR;

  // Check if user has an active subscription or license for billing link text
  // Show "Plans & Billing" if they have either (even if Stripe connection fails)
  const hasSubscription = Boolean(
    (billingData && hasActiveSubscription(billingData)) ||
      licenseData?.has_license
  );

  const items = collections(
    t,
    isCurator,
    enableCloudSS,
    enableEnterprise,
    settings,
    kgExposed,
    customAnalyticsEnabled,
    hasSubscription
  );

  return (
    <SidebarWrapper>
      <SidebarBody
        scrollKey="admin-sidebar"
        actionButtons={
          <SidebarTab
            leftIcon={({ className }) => (
              <CgArrowsExpandUpLeft className={className} size={16} />
            )}
            href="/app"
          >
            {t("admin.navigation.exitAdmin")}
          </SidebarTab>
        }
        footer={
          <div className="flex flex-col gap-2">
            {settings.webVersion && (
              <Text as="p" text02 secondaryBody className="px-2">
                {t("admin.navigation.version", { version: settings.webVersion })}
              </Text>
            )}
            <UserAvatarPopover />
          </div>
        }
      >
        {items.map((collection, index) => (
          <SidebarSection key={index} title={collection.name}>
            <div className="flex flex-col w-full">
              {collection.items.map(({ link, icon: Icon, name }, index) => (
                <SidebarTab
                  key={index}
                  href={link}
                  transient={pathname.startsWith(link)}
                  leftIcon={({ className }) => (
                    <Icon className={className} size={16} />
                  )}
                >
                  {name}
                </SidebarTab>
              ))}
            </div>
          </SidebarSection>
        ))}
      </SidebarBody>
    </SidebarWrapper>
  );
}
