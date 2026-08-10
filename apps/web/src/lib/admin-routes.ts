import { IconFunctionComponent } from "@opal/types";
import {
  SvgActions,
  SvgActivity,
  SvgArrowExchange,
  SvgBarChart,
  SvgBookOpen,
  SvgBubbleText,
  SvgClipboard,
  SvgCpu,
  SvgDiscordMono,
  SvgDownload,
  SvgFileText,
  SvgFolder,
  SvgGlobe,
  SvgImage,
  SvgKey,
  SvgMcp,
  SvgNetworkGraph,
  SvgOnyxOctagon,
  SvgPaintBrush,
  SvgSearch,
  SvgServer,
  SvgShield,
  SvgSlack,
  SvgTerminal,
  SvgThumbsUp,
  SvgUploadCloud,
  SvgUser,
  SvgUsers,
  SvgWallet,
  SvgZoomIn,
} from "@opal/icons";

/**
 * Canonical path constants for every admin route.
 */
export const ADMIN_PATHS = {
  INDEXING_STATUS: "/admin/indexing/status",
  ADD_CONNECTOR: "/admin/add-connector",
  DOCUMENT_SETS: "/admin/documents/sets",
  DOCUMENT_EXPLORER: "/admin/documents/explorer",
  DOCUMENT_FEEDBACK: "/admin/documents/feedback",
  AGENTS: "/admin/agents",
  SLACK_BOTS: "/admin/bots",
  DISCORD_BOTS: "/admin/discord-bot",
  MCP_ACTIONS: "/admin/actions/mcp",
  OPENAPI_ACTIONS: "/admin/actions/open-api",
  STANDARD_ANSWERS: "/admin/standard-answer",
  GROUPS: "/admin/groups",
  CHAT_PREFERENCES: "/admin/configuration/chat-preferences",
  LLM_MODELS: "/admin/configuration/llm",
  WEB_SEARCH: "/admin/configuration/web-search",
  IMAGE_GENERATION: "/admin/configuration/image-generation",
  CODE_INTERPRETER: "/admin/configuration/code-interpreter",
  MAIL_CONFIGS: "/admin/configuration/mail-configs",
  SEARCH_SETTINGS: "/admin/configuration/search",
  DOCUMENT_PROCESSING: "/admin/configuration/document-processing",
  KNOWLEDGE_GRAPH: "/admin/kg",
  USERS: "/admin/users",
  API_KEYS: "/admin/api-key",
  ROLES: "/admin/roles",
  ORGANIZATIONS: "/admin/organizations",
  TOKEN_RATE_LIMITS: "/admin/token-rate-limits",
  USAGE: "/admin/performance/usage",
  QUERY_HISTORY: "/admin/performance/query-history",
  CUSTOM_ANALYTICS: "/admin/performance/custom-analytics",
  THEME: "/admin/theme",
  BILLING: "/admin/billing",
  INDEX_MIGRATION: "/admin/document-index-migration",
  DEBUG: "/admin/debug",
  SYSTEM_SETTINGS: "/admin/system-settings",
  SYSTEM_INFO: "/admin/systeminfo",
  // Prefix-only entries (used in SETTINGS_LAYOUT_PREFIXES but have no
  // single page header of their own)
  DOCUMENTS: "/admin/documents",
  PERFORMANCE: "/admin/performance",
} as const;

interface AdminRouteConfig {
  icon: IconFunctionComponent;
  title: string;
  sidebarLabel: string;
  requiredPermissions?: string[];
  titleKey?: string;
  sidebarLabelKey?: string;
}

/**
 * Single source of truth for icon, page-header title, and sidebar label
 * for every admin route. Keyed by path from `ADMIN_PATHS`.
 */
export const ADMIN_ROUTE_CONFIG: Record<string, AdminRouteConfig> = {
  [ADMIN_PATHS.INDEXING_STATUS]: {
    icon: SvgBookOpen,
    title: "Existing Connectors",
    sidebarLabel: "Existing Connectors",
    requiredPermissions: ["datasource:read"],
    titleKey: "admin.navigation.routes.indexingStatus.title",
    sidebarLabelKey: "admin.navigation.routes.indexingStatus.sidebar",
  },
  [ADMIN_PATHS.ADD_CONNECTOR]: {
    icon: SvgUploadCloud,
    title: "Add Connector",
    sidebarLabel: "Add Connector",
    requiredPermissions: ["datasource:create"],
    titleKey: "admin.navigation.routes.addConnector.title",
    sidebarLabelKey: "admin.navigation.routes.addConnector.sidebar",
  },
  [ADMIN_PATHS.DOCUMENT_SETS]: {
    icon: SvgFolder,
    title: "Document Sets",
    sidebarLabel: "Document Sets",
    requiredPermissions: ["collection:list"],
    titleKey: "admin.navigation.routes.documentSets.title",
    sidebarLabelKey: "admin.navigation.routes.documentSets.sidebar",
  },
  [ADMIN_PATHS.DOCUMENT_EXPLORER]: {
    icon: SvgZoomIn,
    title: "Document Explorer",
    sidebarLabel: "Explorer",
    requiredPermissions: ["document:search"],
    titleKey: "admin.navigation.routes.documentExplorer.title",
    sidebarLabelKey: "admin.navigation.routes.documentExplorer.sidebar",
  },
  [ADMIN_PATHS.DOCUMENT_FEEDBACK]: {
    icon: SvgThumbsUp,
    title: "Document Feedback",
    sidebarLabel: "Feedback",
    requiredPermissions: ["document:read"],
    titleKey: "admin.navigation.routes.documentFeedback.title",
    sidebarLabelKey: "admin.navigation.routes.documentFeedback.sidebar",
  },
  [ADMIN_PATHS.AGENTS]: {
    icon: SvgOnyxOctagon,
    title: "Agents",
    sidebarLabel: "Agents",
    requiredPermissions: ["agent:list"],
    titleKey: "admin.navigation.routes.agents.title",
    sidebarLabelKey: "admin.navigation.routes.agents.sidebar",
  },
  [ADMIN_PATHS.SLACK_BOTS]: {
    icon: SvgSlack,
    title: "Slack Bots",
    sidebarLabel: "Slack Bots",
    requiredPermissions: ["settings:read"],
    titleKey: "admin.navigation.routes.slackBots.title",
    sidebarLabelKey: "admin.navigation.routes.slackBots.sidebar",
  },
  [ADMIN_PATHS.DISCORD_BOTS]: {
    icon: SvgDiscordMono,
    title: "Discord Bots",
    sidebarLabel: "Discord Bots",
    requiredPermissions: ["settings:read"],
    titleKey: "admin.navigation.routes.discordBots.title",
    sidebarLabelKey: "admin.navigation.routes.discordBots.sidebar",
  },
  [ADMIN_PATHS.MCP_ACTIONS]: {
    icon: SvgMcp,
    title: "MCP Actions",
    sidebarLabel: "MCP Actions",
    requiredPermissions: ["mcp_tool:read"],
    titleKey: "admin.navigation.routes.mcpActions.title",
    sidebarLabelKey: "admin.navigation.routes.mcpActions.sidebar",
  },
  [ADMIN_PATHS.OPENAPI_ACTIONS]: {
    icon: SvgActions,
    title: "OpenAPI Actions",
    sidebarLabel: "OpenAPI Actions",
    requiredPermissions: ["mcp_tool:read"],
    titleKey: "admin.navigation.routes.openapiActions.title",
    sidebarLabelKey: "admin.navigation.routes.openapiActions.sidebar",
  },
  [ADMIN_PATHS.STANDARD_ANSWERS]: {
    icon: SvgClipboard,
    title: "Standard Answers",
    sidebarLabel: "Standard Answers",
    requiredPermissions: ["assistant:read"],
    titleKey: "admin.navigation.routes.standardAnswers.title",
    sidebarLabelKey: "admin.navigation.routes.standardAnswers.sidebar",
  },
  [ADMIN_PATHS.GROUPS]: {
    icon: SvgUsers,
    title: "Manage User Groups",
    sidebarLabel: "Groups",
    requiredPermissions: ["user:list"],
    titleKey: "admin.navigation.routes.groups.title",
    sidebarLabelKey: "admin.navigation.routes.groups.sidebar",
  },
  [ADMIN_PATHS.CHAT_PREFERENCES]: {
    icon: SvgBubbleText,
    title: "Chat Preferences",
    sidebarLabel: "Chat Preferences",
    requiredPermissions: ["settings:read"],
    titleKey: "admin.navigation.routes.chatPreferences.title",
    sidebarLabelKey: "admin.navigation.routes.chatPreferences.sidebar",
  },
  [ADMIN_PATHS.LLM_MODELS]: {
    icon: SvgCpu,
    title: "LLM Models",
    sidebarLabel: "LLM Models",
    requiredPermissions: ["provider:read"],
    titleKey: "admin.navigation.routes.llmModels.title",
    sidebarLabelKey: "admin.navigation.routes.llmModels.sidebar",
  },
  [ADMIN_PATHS.WEB_SEARCH]: {
    icon: SvgGlobe,
    title: "Web Search",
    sidebarLabel: "Web Search",
    requiredPermissions: ["web_search:manage"],
    titleKey: "admin.navigation.routes.webSearch.title",
    sidebarLabelKey: "admin.navigation.routes.webSearch.sidebar",
  },
  [ADMIN_PATHS.IMAGE_GENERATION]: {
    icon: SvgImage,
    title: "Image Generation",
    sidebarLabel: "Image Generation",
    requiredPermissions: ["provider:read"],
    titleKey: "admin.navigation.routes.imageGeneration.title",
    sidebarLabelKey: "admin.navigation.routes.imageGeneration.sidebar",
  },
  [ADMIN_PATHS.CODE_INTERPRETER]: {
    icon: SvgTerminal,
    title: "Code Interpreter",
    sidebarLabel: "Code Interpreter",
    requiredPermissions: ["settings:read"],
    titleKey: "admin.navigation.routes.codeInterpreter.title",
    sidebarLabelKey: "admin.navigation.routes.codeInterpreter.sidebar",
  },
  [ADMIN_PATHS.MAIL_CONFIGS]: {
    icon: SvgServer,
    title: "Mail Configs",
    sidebarLabel: "Mail Configs",
    requiredPermissions: ["settings:read"],
    titleKey: "admin.navigation.routes.mailConfigs.title",
    sidebarLabelKey: "admin.navigation.routes.mailConfigs.sidebar",
  },
  [ADMIN_PATHS.SEARCH_SETTINGS]: {
    icon: SvgSearch,
    title: "Search Settings",
    sidebarLabel: "Search Settings",
    requiredPermissions: ["settings:read"],
    titleKey: "admin.navigation.routes.searchSettings.title",
    sidebarLabelKey: "admin.navigation.routes.searchSettings.sidebar",
  },
  [ADMIN_PATHS.DOCUMENT_PROCESSING]: {
    icon: SvgFileText,
    title: "Document Processing",
    sidebarLabel: "Document Processing",
    requiredPermissions: ["settings:read"],
    titleKey: "admin.navigation.routes.documentProcessing.title",
    sidebarLabelKey: "admin.navigation.routes.documentProcessing.sidebar",
  },
  [ADMIN_PATHS.KNOWLEDGE_GRAPH]: {
    icon: SvgNetworkGraph,
    title: "Knowledge Graph",
    sidebarLabel: "Knowledge Graph",
    requiredPermissions: ["graph:read"],
    titleKey: "admin.navigation.routes.knowledgeGraph.title",
    sidebarLabelKey: "admin.navigation.routes.knowledgeGraph.sidebar",
  },
  [ADMIN_PATHS.ORGANIZATIONS]: {
    icon: SvgUser,
    title: "Manage Organizations",
    sidebarLabel: "Organizations",
    requiredPermissions: ["org:list"],
    titleKey: "admin.navigation.routes.organizations.title",
    sidebarLabelKey: "admin.navigation.routes.organizations.sidebar",
  },
  [ADMIN_PATHS.USERS]: {
    icon: SvgUser,
    title: "Manage Users",
    sidebarLabel: "Users",
    requiredPermissions: ["user:list"],
    titleKey: "admin.navigation.routes.users.title",
    sidebarLabelKey: "admin.navigation.routes.users.sidebar",
  },
  [ADMIN_PATHS.API_KEYS]: {
    icon: SvgKey,
    title: "API Keys",
    sidebarLabel: "API Keys",
    requiredPermissions: ["api_key:read"],
    titleKey: "admin.navigation.routes.apiKeys.title",
    sidebarLabelKey: "admin.navigation.routes.apiKeys.sidebar",
  },
  [ADMIN_PATHS.ROLES]: {
    icon: SvgShield,
    title: "Roles & Permissions",
    sidebarLabel: "Roles & Permissions",
    requiredPermissions: ["role:list", "role:read", "permission:list"],
    titleKey: "admin.navigation.routes.roles.title",
    sidebarLabelKey: "admin.navigation.routes.roles.sidebar",
  },
  [ADMIN_PATHS.TOKEN_RATE_LIMITS]: {
    icon: SvgShield,
    title: "Token Rate Limits",
    sidebarLabel: "Token Rate Limits",
    requiredPermissions: ["user:list"],
    titleKey: "admin.navigation.routes.tokenRateLimits.title",
    sidebarLabelKey: "admin.navigation.routes.tokenRateLimits.sidebar",
  },
  [ADMIN_PATHS.USAGE]: {
    icon: SvgActivity,
    title: "Usage Statistics",
    sidebarLabel: "Usage Statistics",
    requiredPermissions: ["audit_log:read"],
    titleKey: "admin.navigation.routes.usage.title",
    sidebarLabelKey: "admin.navigation.routes.usage.sidebar",
  },
  [ADMIN_PATHS.QUERY_HISTORY]: {
    icon: SvgServer,
    title: "Query History",
    sidebarLabel: "Query History",
    requiredPermissions: ["audit_log:read"],
    titleKey: "admin.navigation.routes.queryHistory.title",
    sidebarLabelKey: "admin.navigation.routes.queryHistory.sidebar",
  },
  [ADMIN_PATHS.CUSTOM_ANALYTICS]: {
    icon: SvgBarChart,
    title: "Custom Analytics",
    sidebarLabel: "Custom Analytics",
    requiredPermissions: ["settings:read"],
    titleKey: "admin.navigation.routes.customAnalytics.title",
    sidebarLabelKey: "admin.navigation.routes.customAnalytics.sidebar",
  },
  [ADMIN_PATHS.THEME]: {
    icon: SvgPaintBrush,
    title: "Appearance & Theming",
    sidebarLabel: "Appearance & Theming",
    requiredPermissions: ["settings:update"],
    titleKey: "admin.navigation.routes.theme.title",
    sidebarLabelKey: "admin.navigation.routes.theme.sidebar",
  },
  [ADMIN_PATHS.BILLING]: {
    icon: SvgWallet,
    title: "Plans & Billing",
    sidebarLabel: "Plans & Billing",
    requiredPermissions: ["system.settings:read"],
    titleKey: "admin.navigation.routes.billing.title",
    sidebarLabelKey: "admin.navigation.routes.billing.sidebar",
  },
  [ADMIN_PATHS.INDEX_MIGRATION]: {
    icon: SvgArrowExchange,
    title: "Document Index Migration",
    sidebarLabel: "Document Index Migration",
    requiredPermissions: ["system.settings:read"],
    titleKey: "admin.navigation.routes.indexMigration.title",
    sidebarLabelKey: "admin.navigation.routes.indexMigration.sidebar",
  },
  [ADMIN_PATHS.DEBUG]: {
    icon: SvgDownload,
    title: "Debug Logs",
    sidebarLabel: "Debug Logs",
    requiredPermissions: ["audit_log:read"],
    titleKey: "admin.navigation.routes.debug.title",
    sidebarLabelKey: "admin.navigation.routes.debug.sidebar",
  },
  [ADMIN_PATHS.SYSTEM_SETTINGS]: {
    icon: SvgShield,
    title: "System Settings",
    sidebarLabel: "System Settings",
    requiredPermissions: ["*"],
    titleKey: "admin.navigation.routes.systemSettings.title",
    sidebarLabelKey: "admin.navigation.routes.systemSettings.sidebar",
  },
  [ADMIN_PATHS.SYSTEM_INFO]: {
    icon: SvgServer,
    title: "System Information",
    sidebarLabel: "System Information",
    requiredPermissions: ["system.settings:read"],
    titleKey: "admin.navigation.routes.systemInfo.title",
    sidebarLabelKey: "admin.navigation.routes.systemInfo.sidebar",
  },
};

/**
 * Helper that converts a route config entry into the `{ name, icon, link }`
 * shape expected by the sidebar. Extra fields (e.g. `error`) can be spread in.
 */
export function sidebarItem(
  path: string,
  t?: (key: string, options?: { defaultValue?: string }) => string
) {
  const config = ADMIN_ROUTE_CONFIG[path]!;
  return {
    name:
      config.sidebarLabelKey && t
        ? t(config.sidebarLabelKey, { defaultValue: config.sidebarLabel })
        : config.sidebarLabel,
    icon: config.icon,
    link: path,
    requiredPermissions: config.requiredPermissions ?? [],
  };
}

export function getAdminRouteConfigForPathname(pathname: string) {
  const matchingPath = Object.keys(ADMIN_ROUTE_CONFIG)
    .filter((path) => pathname === path || pathname.startsWith(`${path}/`))
    .sort((a, b) => b.length - a.length)[0];

  return matchingPath ? ADMIN_ROUTE_CONFIG[matchingPath] : null;
}
