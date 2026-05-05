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
  SEARCH_SETTINGS: "/admin/configuration/search",
  DOCUMENT_PROCESSING: "/admin/configuration/document-processing",
  KNOWLEDGE_GRAPH: "/admin/kg",
  USERS: "/admin/users",
  API_KEYS: "/admin/api-key",
  TOKEN_RATE_LIMITS: "/admin/token-rate-limits",
  USAGE: "/admin/performance/usage",
  QUERY_HISTORY: "/admin/performance/query-history",
  CUSTOM_ANALYTICS: "/admin/performance/custom-analytics",
  THEME: "/admin/theme",
  BILLING: "/admin/billing",
  INDEX_MIGRATION: "/admin/document-index-migration",
  DEBUG: "/admin/debug",
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
    titleKey: "admin.navigation.routes.indexingStatus.title",
    sidebarLabelKey: "admin.navigation.routes.indexingStatus.sidebar",
  },
  [ADMIN_PATHS.ADD_CONNECTOR]: {
    icon: SvgUploadCloud,
    title: "Add Connector",
    sidebarLabel: "Add Connector",
    titleKey: "admin.navigation.routes.addConnector.title",
    sidebarLabelKey: "admin.navigation.routes.addConnector.sidebar",
  },
  [ADMIN_PATHS.DOCUMENT_SETS]: {
    icon: SvgFolder,
    title: "Document Sets",
    sidebarLabel: "Document Sets",
    titleKey: "admin.navigation.routes.documentSets.title",
    sidebarLabelKey: "admin.navigation.routes.documentSets.sidebar",
  },
  [ADMIN_PATHS.DOCUMENT_EXPLORER]: {
    icon: SvgZoomIn,
    title: "Document Explorer",
    sidebarLabel: "Explorer",
    titleKey: "admin.navigation.routes.documentExplorer.title",
    sidebarLabelKey: "admin.navigation.routes.documentExplorer.sidebar",
  },
  [ADMIN_PATHS.DOCUMENT_FEEDBACK]: {
    icon: SvgThumbsUp,
    title: "Document Feedback",
    sidebarLabel: "Feedback",
  },
  [ADMIN_PATHS.AGENTS]: {
    icon: SvgOnyxOctagon,
    title: "Agents",
    sidebarLabel: "Agents",
    titleKey: "admin.navigation.routes.agents.title",
    sidebarLabelKey: "admin.navigation.routes.agents.sidebar",
  },
  [ADMIN_PATHS.SLACK_BOTS]: {
    icon: SvgSlack,
    title: "Slack Bots",
    sidebarLabel: "Slack Bots",
  },
  [ADMIN_PATHS.DISCORD_BOTS]: {
    icon: SvgDiscordMono,
    title: "Discord Bots",
    sidebarLabel: "Discord Bots",
  },
  [ADMIN_PATHS.MCP_ACTIONS]: {
    icon: SvgMcp,
    title: "MCP Actions",
    sidebarLabel: "MCP Actions",
    titleKey: "admin.navigation.routes.mcpActions.title",
    sidebarLabelKey: "admin.navigation.routes.mcpActions.sidebar",
  },
  [ADMIN_PATHS.OPENAPI_ACTIONS]: {
    icon: SvgActions,
    title: "OpenAPI Actions",
    sidebarLabel: "OpenAPI Actions",
  },
  [ADMIN_PATHS.STANDARD_ANSWERS]: {
    icon: SvgClipboard,
    title: "Standard Answers",
    sidebarLabel: "Standard Answers",
  },
  [ADMIN_PATHS.GROUPS]: {
    icon: SvgUsers,
    title: "Manage User Groups",
    sidebarLabel: "Groups",
  },
  [ADMIN_PATHS.CHAT_PREFERENCES]: {
    icon: SvgBubbleText,
    title: "Chat Preferences",
    sidebarLabel: "Chat Preferences",
    titleKey: "admin.navigation.routes.chatPreferences.title",
    sidebarLabelKey: "admin.navigation.routes.chatPreferences.sidebar",
  },
  [ADMIN_PATHS.LLM_MODELS]: {
    icon: SvgCpu,
    title: "LLM Models",
    sidebarLabel: "LLM Models",
    titleKey: "admin.navigation.routes.llmModels.title",
    sidebarLabelKey: "admin.navigation.routes.llmModels.sidebar",
  },
  [ADMIN_PATHS.WEB_SEARCH]: {
    icon: SvgGlobe,
    title: "Web Search",
    sidebarLabel: "Web Search",
    titleKey: "admin.navigation.routes.webSearch.title",
    sidebarLabelKey: "admin.navigation.routes.webSearch.sidebar",
  },
  [ADMIN_PATHS.IMAGE_GENERATION]: {
    icon: SvgImage,
    title: "Image Generation",
    sidebarLabel: "Image Generation",
    titleKey: "admin.navigation.routes.imageGeneration.title",
    sidebarLabelKey: "admin.navigation.routes.imageGeneration.sidebar",
  },
  [ADMIN_PATHS.CODE_INTERPRETER]: {
    icon: SvgTerminal,
    title: "Code Interpreter",
    sidebarLabel: "Code Interpreter",
    titleKey: "admin.navigation.routes.codeInterpreter.title",
    sidebarLabelKey: "admin.navigation.routes.codeInterpreter.sidebar",
  },
  [ADMIN_PATHS.SEARCH_SETTINGS]: {
    icon: SvgSearch,
    title: "Search Settings",
    sidebarLabel: "Search Settings",
    titleKey: "admin.navigation.routes.searchSettings.title",
    sidebarLabelKey: "admin.navigation.routes.searchSettings.sidebar",
  },
  [ADMIN_PATHS.DOCUMENT_PROCESSING]: {
    icon: SvgFileText,
    title: "Document Processing",
    sidebarLabel: "Document Processing",
    titleKey: "admin.navigation.routes.documentProcessing.title",
    sidebarLabelKey: "admin.navigation.routes.documentProcessing.sidebar",
  },
  [ADMIN_PATHS.KNOWLEDGE_GRAPH]: {
    icon: SvgNetworkGraph,
    title: "Knowledge Graph",
    sidebarLabel: "Knowledge Graph",
    titleKey: "admin.navigation.routes.knowledgeGraph.title",
    sidebarLabelKey: "admin.navigation.routes.knowledgeGraph.sidebar",
  },
  [ADMIN_PATHS.USERS]: {
    icon: SvgUser,
    title: "Manage Users",
    sidebarLabel: "Users",
    titleKey: "admin.navigation.routes.users.title",
    sidebarLabelKey: "admin.navigation.routes.users.sidebar",
  },
  [ADMIN_PATHS.API_KEYS]: {
    icon: SvgKey,
    title: "API Keys",
    sidebarLabel: "API Keys",
    titleKey: "admin.navigation.routes.apiKeys.title",
    sidebarLabelKey: "admin.navigation.routes.apiKeys.sidebar",
  },
  [ADMIN_PATHS.TOKEN_RATE_LIMITS]: {
    icon: SvgShield,
    title: "Token Rate Limits",
    sidebarLabel: "Token Rate Limits",
  },
  [ADMIN_PATHS.USAGE]: {
    icon: SvgActivity,
    title: "Usage Statistics",
    sidebarLabel: "Usage Statistics",
  },
  [ADMIN_PATHS.QUERY_HISTORY]: {
    icon: SvgServer,
    title: "Query History",
    sidebarLabel: "Query History",
  },
  [ADMIN_PATHS.CUSTOM_ANALYTICS]: {
    icon: SvgBarChart,
    title: "Custom Analytics",
    sidebarLabel: "Custom Analytics",
  },
  [ADMIN_PATHS.THEME]: {
    icon: SvgPaintBrush,
    title: "Appearance & Theming",
    sidebarLabel: "Appearance & Theming",
  },
  [ADMIN_PATHS.BILLING]: {
    icon: SvgWallet,
    title: "Plans & Billing",
    sidebarLabel: "Plans & Billing",
  },
  [ADMIN_PATHS.INDEX_MIGRATION]: {
    icon: SvgArrowExchange,
    title: "Document Index Migration",
    sidebarLabel: "Document Index Migration",
  },
  [ADMIN_PATHS.DEBUG]: {
    icon: SvgDownload,
    title: "Debug Logs",
    sidebarLabel: "Debug Logs",
  },
  [ADMIN_PATHS.SYSTEM_INFO]: {
    icon: SvgServer,
    title: "System Information",
    sidebarLabel: "System Information",
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
  };
}
