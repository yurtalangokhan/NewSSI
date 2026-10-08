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
  SvgAtlasOctagon,
  SvgPaintBrush,
  SvgSearch,
  SvgServer,
  SvgSettings,
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
import { hasAllPermissions } from "@/lib/auth/permissions";

/**
 * Canonical path constants for every admin route.
 */
export const ADMIN_PATHS = {
  EMBEDDINGS: "/admin/embeddings",
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
  MCP_CONFIG: "/admin/configuration/mcp",
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
  requiredPermissions: string[];
  titleKey?: string;
  sidebarLabelKey?: string;
  description?: string;
  descriptionKey?: string;
  // Defaults to true. Set to false to 404 the page and hide it from the
  // sidebar, e.g. for MVP-scoped-out features that will return later.
  enabled?: boolean;
}

/**
 * Single source of truth for icon, page-header title, and sidebar label
 * for every admin route. Keyed by path from `ADMIN_PATHS`.
 */
export const ADMIN_ROUTE_CONFIG: Record<string, AdminRouteConfig> = {
  [ADMIN_PATHS.EMBEDDINGS]: {
    icon: SvgSearch,
    title: "Embedding Models",
    sidebarLabel: "Embedding Models",
    requiredPermissions: ["embedding:view"],
  },
  [ADMIN_PATHS.INDEXING_STATUS]: {
    icon: SvgBookOpen,
    title: "Existing Connectors",
    sidebarLabel: "Existing Connectors",
    requiredPermissions: ["datasource:view"],
    titleKey: "admin.navigation.routes.indexingStatus.title",
    sidebarLabelKey: "admin.navigation.routes.indexingStatus.sidebar",
    description:
      "View and manage your configured data connectors and indexing status.",
    descriptionKey: "admin.navigation.routes.indexingStatus.description",
  },
  [ADMIN_PATHS.ADD_CONNECTOR]: {
    icon: SvgUploadCloud,
    title: "Add Connector",
    sidebarLabel: "Add Connector",
    requiredPermissions: ["datasource_add:view"],
    titleKey: "admin.navigation.routes.addConnector.title",
    sidebarLabelKey: "admin.navigation.routes.addConnector.sidebar",
    description:
      "Connect new data sources and external services to ingest knowledge for your agents.",
    descriptionKey: "admin.navigation.routes.addConnector.description",
  },
  [ADMIN_PATHS.DOCUMENT_SETS]: {
    icon: SvgFolder,
    title: "Document Sets",
    sidebarLabel: "Document Sets",
    requiredPermissions: ["collection:view"],
    titleKey: "admin.navigation.routes.documentSets.title",
    sidebarLabelKey: "admin.navigation.routes.documentSets.sidebar",
    description:
      "Group documents into collections to define knowledge scopes for agents and search.",
    descriptionKey: "admin.navigation.routes.documentSets.description",
    enabled: false, // MVP: scoped out, pending rework
  },
  [ADMIN_PATHS.DOCUMENT_EXPLORER]: {
    icon: SvgZoomIn,
    title: "Document Explorer",
    sidebarLabel: "Explorer",
    requiredPermissions: ["document:view"],
    titleKey: "admin.navigation.routes.documentExplorer.title",
    sidebarLabelKey: "admin.navigation.routes.documentExplorer.sidebar",
    description:
      "Search, inspect, and verify indexed documents and their chunked contents.",
    descriptionKey: "admin.navigation.routes.documentExplorer.description",
    enabled: false, // MVP: scoped out, pending rework
  },
  [ADMIN_PATHS.DOCUMENT_FEEDBACK]: {
    icon: SvgThumbsUp,
    title: "Document Feedback",
    sidebarLabel: "Feedback",
    requiredPermissions: ["document_feedback:view"],
    titleKey: "admin.navigation.routes.documentFeedback.title",
    sidebarLabelKey: "admin.navigation.routes.documentFeedback.sidebar",
    description:
      "Review user ratings and feedback on document relevance and answer quality.",
    descriptionKey: "admin.navigation.routes.documentFeedback.description",
    enabled: false, // MVP: scoped out, pending rework
  },
  [ADMIN_PATHS.AGENTS]: {
    icon: SvgAtlasOctagon,
    title: "Agents",
    sidebarLabel: "Agents & Flows",
    requiredPermissions: ["agent:view"],
    titleKey: "admin.navigation.routes.agents.title",
    sidebarLabelKey: "admin.navigation.routes.agents.sidebar",
    description:
      "Create and manage AI agents equipped with custom instructions, tools, and knowledge sources.",
    descriptionKey: "admin.navigation.routes.agents.description",
  },
  [ADMIN_PATHS.SLACK_BOTS]: {
    icon: SvgSlack,
    title: "Slack Bots",
    sidebarLabel: "Slack Bots",
    requiredPermissions: ["slack_bot:view"],
    titleKey: "admin.navigation.routes.slackBots.title",
    sidebarLabelKey: "admin.navigation.routes.slackBots.sidebar",
    description:
      "Connect ATLAS to your Slack workspace and let users ask questions directly from Slack channels.",
    descriptionKey: "admin.navigation.routes.slackBots.description",
  },
  [ADMIN_PATHS.DISCORD_BOTS]: {
    icon: SvgDiscordMono,
    title: "Discord Bots",
    sidebarLabel: "Discord Bots",
    requiredPermissions: ["discord_bot:view"],
    titleKey: "admin.navigation.routes.discordBots.title",
    sidebarLabelKey: "admin.navigation.routes.discordBots.sidebar",
    description:
      "Connect ATLAS to your Discord servers. Users can ask questions directly in Discord channels.",
    descriptionKey: "admin.navigation.routes.discordBots.description",
  },
  [ADMIN_PATHS.MCP_ACTIONS]: {
    icon: SvgMcp,
    title: "MCP Actions",
    sidebarLabel: "MCP Actions",
    requiredPermissions: ["mcp_tool:view"],
    titleKey: "admin.navigation.routes.mcpActions.title",
    sidebarLabelKey: "admin.navigation.routes.mcpActions.sidebar",
    description:
      "Connect MCP (Model Context Protocol) servers to add custom actions and tools for your agents.",
    descriptionKey: "admin.navigation.routes.mcpActions.description",
  },
  [ADMIN_PATHS.OPENAPI_ACTIONS]: {
    icon: SvgActions,
    title: "OpenAPI Actions",
    sidebarLabel: "OpenAPI Actions",
    requiredPermissions: ["openapi_tool:view"],
    titleKey: "admin.navigation.routes.openapiActions.title",
    sidebarLabelKey: "admin.navigation.routes.openapiActions.sidebar",
    description:
      "Connect OpenAPI servers to add custom actions and tools for your agents.",
    descriptionKey: "admin.navigation.routes.openapiActions.description",
    enabled: false, // MVP: scoped out, pending rework
  },
  [ADMIN_PATHS.STANDARD_ANSWERS]: {
    icon: SvgClipboard,
    title: "Standard Answers",
    sidebarLabel: "Standard Answers",
    requiredPermissions: ["assistant:view"],
    titleKey: "admin.navigation.routes.standardAnswers.title",
    sidebarLabelKey: "admin.navigation.routes.standardAnswers.sidebar",
    description:
      "Configure predefined standard answers triggered by specific questions or keywords.",
    descriptionKey: "admin.navigation.routes.standardAnswers.description",
  },
  [ADMIN_PATHS.GROUPS]: {
    icon: SvgUsers,
    title: "Manage User Groups",
    sidebarLabel: "Groups",
    requiredPermissions: ["group:view"],
    titleKey: "admin.navigation.routes.groups.title",
    sidebarLabelKey: "admin.navigation.routes.groups.sidebar",
    description:
      "Create and organize user groups to manage permissions and document access collectively.",
    descriptionKey: "admin.navigation.routes.groups.description",
  },
  [ADMIN_PATHS.CHAT_PREFERENCES]: {
    icon: SvgBubbleText,
    title: "Chat Preferences",
    sidebarLabel: "Chat Preferences",
    requiredPermissions: ["chat_preferences:view"],
    titleKey: "admin.navigation.routes.chatPreferences.title",
    sidebarLabelKey: "admin.navigation.routes.chatPreferences.sidebar",
    description:
      "Configure default AI behaviors, team context, and chat preferences for your organization.",
    descriptionKey: "admin.navigation.routes.chatPreferences.description",
    enabled: false, // MVP: scoped out, pending rework
  },
  [ADMIN_PATHS.LLM_MODELS]: {
    icon: SvgCpu,
    title: "LLM Models",
    sidebarLabel: "LLM Models",
    requiredPermissions: ["provider:view"],
    titleKey: "admin.navigation.routes.llmModels.title",
    sidebarLabelKey: "admin.navigation.routes.llmModels.sidebar",
    description:
      "Configure LLM providers, API keys, and default models used across the system.",
    descriptionKey: "admin.navigation.routes.llmModels.description",
  },
  [ADMIN_PATHS.WEB_SEARCH]: {
    icon: SvgGlobe,
    title: "Web Search",
    sidebarLabel: "Web Search",
    requiredPermissions: ["web_search:view"],
    titleKey: "admin.navigation.routes.webSearch.title",
    sidebarLabelKey: "admin.navigation.routes.webSearch.sidebar",
    description: "Search settings for external search across the internet.",
    descriptionKey: "admin.navigation.routes.webSearch.description",
  },
  [ADMIN_PATHS.IMAGE_GENERATION]: {
    icon: SvgImage,
    title: "Image Generation",
    sidebarLabel: "Image Generation",
    requiredPermissions: ["image_generation:view"],
    titleKey: "admin.navigation.routes.imageGeneration.title",
    sidebarLabelKey: "admin.navigation.routes.imageGeneration.sidebar",
    description:
      "Configure image generation models for users to generate images directly from the chat interface.",
    descriptionKey: "admin.navigation.routes.imageGeneration.description",
    enabled: false, // MVP: scoped out, pending rework
  },
  [ADMIN_PATHS.CODE_INTERPRETER]: {
    icon: SvgTerminal,
    title: "Code Interpreter",
    sidebarLabel: "Code Interpreter",
    requiredPermissions: ["code_interpreter:view"],
    titleKey: "admin.navigation.routes.codeInterpreter.title",
    sidebarLabelKey: "admin.navigation.routes.codeInterpreter.sidebar",
    description:
      "Secure, isolated Python runtime available for your LLM. See docs for more details.",
    descriptionKey: "admin.navigation.routes.codeInterpreter.description",
    enabled: false, // MVP: scoped out, pending rework
  },
  [ADMIN_PATHS.MAIL_CONFIGS]: {
    icon: SvgServer,
    title: "Mail Configs",
    sidebarLabel: "Mail Configs",
    requiredPermissions: ["mail_config:view"],
    titleKey: "admin.navigation.routes.mailConfigs.title",
    sidebarLabelKey: "admin.navigation.routes.mailConfigs.sidebar",
    description: "Manage SMTP accounts that agents can use with send_email.",
    descriptionKey: "admin.navigation.routes.mailConfigs.description",
  },
  [ADMIN_PATHS.MCP_CONFIG]: {
    icon: SvgMcp,
    title: "MCP Configuration",
    sidebarLabel: "MCP Configuration",
    // Provider registration is system-admin only. The page has its own
    // permission rather than reusing `:create`, because enterprise admins may
    // hold registry write grants from before the connect/configure split.
    requiredPermissions: ["mcp_provider:configure"],
    titleKey: "admin.navigation.routes.mcpConfig.title",
    sidebarLabelKey: "admin.navigation.routes.mcpConfig.sidebar",
    description:
      "Register MCP servers so enterprise admins can connect them with their own credentials.",
    descriptionKey: "admin.navigation.routes.mcpConfig.description",
  },
  [ADMIN_PATHS.SEARCH_SETTINGS]: {
    icon: SvgSearch,
    title: "Search Settings",
    sidebarLabel: "Search Settings",
    requiredPermissions: ["search_settings:view"],
    titleKey: "admin.navigation.routes.searchSettings.title",
    sidebarLabelKey: "admin.navigation.routes.searchSettings.sidebar",
    description:
      "Configure embedding models, reindexing options, and search retrieval quality settings.",
    descriptionKey: "admin.navigation.routes.searchSettings.description",
    enabled: false, // MVP: scoped out, pending rework
  },
  [ADMIN_PATHS.DOCUMENT_PROCESSING]: {
    icon: SvgFileText,
    title: "Document Processing",
    sidebarLabel: "Document Processing",
    requiredPermissions: ["document_processing:view"],
    titleKey: "admin.navigation.routes.documentProcessing.title",
    sidebarLabelKey: "admin.navigation.routes.documentProcessing.sidebar",
    description:
      "Configure settings for the Document Processing & RAG Pipeline.",
    descriptionKey: "admin.navigation.routes.documentProcessing.description",
  },
  [ADMIN_PATHS.KNOWLEDGE_GRAPH]: {
    icon: SvgNetworkGraph,
    title: "Knowledge Graph",
    sidebarLabel: "Knowledge Graph",
    requiredPermissions: ["graph:view"],
    titleKey: "admin.navigation.routes.knowledgeGraph.title",
    sidebarLabelKey: "admin.navigation.routes.knowledgeGraph.sidebar",
    description:
      "Build, inspect, and search entity graphs across your indexed knowledge sources.",
    descriptionKey: "admin.navigation.routes.knowledgeGraph.description",
  },
  [ADMIN_PATHS.ORGANIZATIONS]: {
    icon: SvgUser,
    title: "Manage Organization",
    sidebarLabel: "Organization",
    requiredPermissions: ["org:view"],
    titleKey: "admin.navigation.routes.organizations.title",
    sidebarLabelKey: "admin.navigation.routes.organizations.sidebar",
    description:
      "Manage your organizational hierarchy, department tree, and user assignments.",
    descriptionKey: "admin.navigation.routes.organizations.description",
  },
  [ADMIN_PATHS.USERS]: {
    icon: SvgUser,
    title: "Manage Users",
    sidebarLabel: "Users",
    requiredPermissions: ["user:view"],
    titleKey: "admin.navigation.routes.users.title",
    sidebarLabelKey: "admin.navigation.routes.users.sidebar",
    description:
      "Manage user accounts, send invitations, and configure user roles.",
    descriptionKey: "admin.navigation.routes.users.description",
  },
  [ADMIN_PATHS.API_KEYS]: {
    icon: SvgKey,
    title: "API Keys",
    sidebarLabel: "API Keys",
    requiredPermissions: ["api_key:view"],
    titleKey: "admin.navigation.routes.apiKeys.title",
    sidebarLabelKey: "admin.navigation.routes.apiKeys.sidebar",
    description:
      "Generate and manage API keys for programmatic access to platform APIs.",
    descriptionKey: "admin.navigation.routes.apiKeys.description",
    enabled: false, // MVP: scoped out, pending rework
  },
  [ADMIN_PATHS.ROLES]: {
    icon: SvgShield,
    title: "Roles & Permissions",
    sidebarLabel: "Roles & Permissions",
    requiredPermissions: ["role:view"],
    titleKey: "admin.navigation.routes.roles.title",
    sidebarLabelKey: "admin.navigation.routes.roles.sidebar",
    description:
      "Configure access roles and granular permissions for users and teams.",
    descriptionKey: "admin.navigation.routes.roles.description",
  },
  [ADMIN_PATHS.TOKEN_RATE_LIMITS]: {
    icon: SvgShield,
    title: "Token Rate Limits",
    sidebarLabel: "Token Rate Limits",
    requiredPermissions: ["token_rate_limit:view"],
    titleKey: "admin.navigation.routes.tokenRateLimits.title",
    sidebarLabelKey: "admin.navigation.routes.tokenRateLimits.sidebar",
    description:
      "Manage token usage quotas and rate limits for users and groups.",
    descriptionKey: "admin.navigation.routes.tokenRateLimits.description",
  },
  [ADMIN_PATHS.USAGE]: {
    icon: SvgActivity,
    title: "Usage Statistics",
    sidebarLabel: "Usage Statistics",
    requiredPermissions: ["usage:view"],
    titleKey: "admin.navigation.routes.usage.title",
    sidebarLabelKey: "admin.navigation.routes.usage.sidebar",
    description:
      "Monitor query volumes, user activity, and system usage statistics.",
    descriptionKey: "admin.navigation.routes.usage.description",
  },
  [ADMIN_PATHS.QUERY_HISTORY]: {
    icon: SvgServer,
    title: "Query History",
    sidebarLabel: "Query History",
    requiredPermissions: ["query_history:view"],
    titleKey: "admin.navigation.routes.queryHistory.title",
    sidebarLabelKey: "admin.navigation.routes.queryHistory.sidebar",
    description:
      "Inspect and review past search and chat queries made by users.",
    descriptionKey: "admin.navigation.routes.queryHistory.description",
  },
  [ADMIN_PATHS.CUSTOM_ANALYTICS]: {
    icon: SvgBarChart,
    title: "Custom Analytics",
    sidebarLabel: "Custom Analytics",
    requiredPermissions: ["custom_analytics:view"],
    titleKey: "admin.navigation.routes.customAnalytics.title",
    sidebarLabelKey: "admin.navigation.routes.customAnalytics.sidebar",
    description:
      "Integrate third-party analytics tools to track user interactions and usage events.",
    descriptionKey: "admin.navigation.routes.customAnalytics.description",
  },
  [ADMIN_PATHS.THEME]: {
    icon: SvgPaintBrush,
    title: "Appearance & Theming",
    sidebarLabel: "Appearance & Theming",
    requiredPermissions: ["theme:view"],
    titleKey: "admin.navigation.routes.theme.title",
    sidebarLabelKey: "admin.navigation.routes.theme.sidebar",
    description:
      "Customize how the application looks to users across your organization.",
    descriptionKey: "admin.navigation.routes.theme.description",
  },
  [ADMIN_PATHS.BILLING]: {
    icon: SvgWallet,
    title: "Plans & Billing",
    sidebarLabel: "Plans & Billing",
    requiredPermissions: ["billing:view"],
    titleKey: "admin.navigation.routes.billing.title",
    sidebarLabelKey: "admin.navigation.routes.billing.sidebar",
    description:
      "Manage your subscription plan, seat licenses, and billing details.",
    descriptionKey: "admin.navigation.routes.billing.description",
  },
  [ADMIN_PATHS.INDEX_MIGRATION]: {
    icon: SvgArrowExchange,
    title: "Document Index Migration",
    sidebarLabel: "Document Index Migration",
    requiredPermissions: ["index_migration:view"],
    titleKey: "admin.navigation.routes.indexMigration.title",
    sidebarLabelKey: "admin.navigation.routes.indexMigration.sidebar",
    description:
      "Monitor migration from Vespa to OpenSearch and control active ingestion source.",
    descriptionKey: "admin.navigation.routes.indexMigration.description",
  },
  [ADMIN_PATHS.DEBUG]: {
    icon: SvgDownload,
    title: "Debug Logs",
    sidebarLabel: "Debug Logs",
    requiredPermissions: ["debug:view"],
    titleKey: "admin.navigation.routes.debug.title",
    sidebarLabelKey: "admin.navigation.routes.debug.sidebar",
    description: "Review system debug logs and download diagnostic bundles.",
    descriptionKey: "admin.navigation.routes.debug.description",
  },
  [ADMIN_PATHS.SYSTEM_SETTINGS]: {
    icon: SvgSettings,
    title: "System Settings",
    sidebarLabel: "System Settings",
    requiredPermissions: ["system.settings:view"],
    titleKey: "admin.navigation.routes.systemSettings.title",
    sidebarLabelKey: "admin.navigation.routes.systemSettings.sidebar",
    description:
      "Manage global system configurations, session settings, and authentication preferences.",
    descriptionKey: "admin.navigation.routes.systemSettings.description",
  },
  [ADMIN_PATHS.SYSTEM_INFO]: {
    icon: SvgServer,
    title: "System Information",
    sidebarLabel: "System Information",
    requiredPermissions: ["system_info:view"],
    titleKey: "admin.navigation.routes.systemInfo.title",
    sidebarLabelKey: "admin.navigation.routes.systemInfo.sidebar",
    description:
      "View system version information and runtime environment details.",
    descriptionKey: "admin.navigation.routes.systemInfo.description",
  },
};

export function canAccessAdminPanel(
  permissions: readonly string[] | null | undefined
): boolean {
  return getFirstAccessibleAdminPath(permissions) !== null;
}

export function getFirstAccessibleAdminPath(
  permissions: readonly string[] | null | undefined,
  preferredPaths: readonly string[] = []
): string | null {
  const canAccessRoute = (path: string) => {
    const route = ADMIN_ROUTE_CONFIG[path];
    return Boolean(
      route &&
        route.enabled !== false &&
        route.requiredPermissions?.length &&
        hasAllPermissions(permissions, route.requiredPermissions)
    );
  };

  return (
    preferredPaths.find(canAccessRoute) ??
    Object.keys(ADMIN_ROUTE_CONFIG).find(canAccessRoute) ??
    null
  );
}

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
    enabled: config.enabled ?? true,
  };
}

const ADMIN_ROUTE_ALIASES: Record<string, string> = {
  "/admin/connector": ADMIN_PATHS.INDEXING_STATUS,
  "/admin/connectors": ADMIN_PATHS.ADD_CONNECTOR,
  "/admin/federated": ADMIN_PATHS.INDEXING_STATUS,
  "/admin/actions": ADMIN_PATHS.MCP_ACTIONS,
};

export function getAdminRouteConfigForPathname(pathname: string) {
  const matchingPath = [
    ...Object.keys(ADMIN_ROUTE_CONFIG),
    ...Object.keys(ADMIN_ROUTE_ALIASES),
  ]
    .filter((path) => pathname === path || pathname.startsWith(`${path}/`))
    .sort((a, b) => b.length - a.length)[0];

  return matchingPath
    ? ADMIN_ROUTE_CONFIG[ADMIN_ROUTE_ALIASES[matchingPath] ?? matchingPath]
    : null;
}
