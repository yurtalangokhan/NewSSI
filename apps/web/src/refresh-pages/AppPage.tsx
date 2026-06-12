"use client";

import { redirect, useRouter, useSearchParams } from "next/navigation";
import {
  personaIncludesRetrieval,
  getAvailableContextTokens,
} from "@/app/app/services/lib";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { toast } from "@/hooks/useToast";
import { SEARCH_PARAM_NAMES } from "@/app/app/services/searchParams";
import { useFederatedConnectors, useFilters, useLlmManager } from "@/lib/hooks";
import { useForcedTools } from "@/lib/hooks/useForcedTools";
import OnyxInitializingLoader from "@/components/OnyxInitializingLoader";
import { OnyxDocument, MinimalOnyxDocument } from "@/lib/search/interfaces";
import { useSettingsContext } from "@/providers/SettingsProvider";
import Dropzone from "react-dropzone";
import AppInputBar, { AppInputBarHandle } from "@/sections/input/AppInputBar";
import useChatSessions from "@/hooks/useChatSessions";
import useCCPairs from "@/hooks/useCCPairs";
import useTags from "@/hooks/useTags";
import { useDocumentSets } from "@/lib/hooks/useDocumentSets";
import { useAgents } from "@/hooks/useAgents";
import { AppPopup } from "@/app/app/components/AppPopup";
import ExceptionTraceModal from "@/components/modals/ExceptionTraceModal";
import { useUser } from "@/providers/UserProvider";
import NoAgentModal from "@/components/modals/NoAgentModal";
import PreviewModal from "@/sections/modals/PreviewModal";
import Modal from "@/refresh-components/Modal";
import { useSendMessageToParent } from "@/lib/extension/utils";
import { SUBMIT_MESSAGE_TYPES } from "@/lib/extension/constants";
import { getSourceMetadata } from "@/lib/sources";
import { SourceMetadata } from "@/lib/search/interfaces";
import { FederatedConnectorDetail, UserRole, ValidSources } from "@/lib/types";
import DocumentsSidebar from "@/sections/document-sidebar/DocumentsSidebar";
import useChatController from "@/hooks/useChatController";
import useAgentController from "@/hooks/useAgentController";
import useChatSessionController from "@/hooks/useChatSessionController";
import useDeepResearchToggle from "@/hooks/useDeepResearchToggle";
import useIsDefaultAgent from "@/hooks/useIsDefaultAgent";
import AgentDescription from "@/app/app/components/AgentDescription";
import {
  useChatSessionStore,
  useCurrentMessageHistory,
} from "@/app/app/stores/useChatSessionStore";
import {
  useCurrentChatState,
  useIsReady,
  useDocumentSidebarVisible,
} from "@/app/app/stores/useChatSessionStore";
import FederatedOAuthModal from "@/components/chat/FederatedOAuthModal";
import ChatScrollContainer, {
  ChatScrollContainerHandle,
} from "@/sections/chat/ChatScrollContainer";
import ProjectContextPanel from "@/app/app/components/projects/ProjectContextPanel";
import { useProjectsContext } from "@/providers/ProjectsContext";
import {
  getProjectTokenCount,
  getMaxSelectedDocumentTokens,
} from "@/app/app/projects/projectsService";
import ProjectChatSessionList from "@/app/app/components/projects/ProjectChatSessionList";
import { cn } from "@/lib/utils";
import Suggestions from "@/sections/Suggestions";
import OnboardingFlow from "@/refresh-components/onboarding/OnboardingFlow";
import { OnboardingStep } from "@/refresh-components/onboarding/types";
import { useShowOnboarding } from "@/hooks/useShowOnboarding";
import * as AppLayouts from "@/layouts/app-layouts";
import { SvgChevronDown, SvgChevronLeft, SvgFileText, SvgUploadCloud } from "@opal/icons";
import { Button } from "@opal/components";
import Spacer from "@/refresh-components/Spacer";
import { DEFAULT_CONTEXT_TOKENS } from "@/lib/constants";
import useAppFocus from "@/hooks/useAppFocus";
import { useQueryController } from "@/providers/QueryControllerProvider";
import WelcomeMessage from "@/app/app/components/WelcomeMessage";
import ChatUI from "@/sections/chat/ChatUI";
import { eeGated } from "@/ce";
import EESearchUI from "@/ee/sections/SearchUI";
const SearchUI = eeGated(EESearchUI);
import { motion, AnimatePresence } from "motion/react";
import { useAppMode } from "@/providers/AppModeProvider";
import { useTranslation } from "react-i18next";

interface FadeProps {
  show: boolean;
  children?: React.ReactNode;
  className?: string;
}

function Fade({ show, children, className }: FadeProps) {
  const { t } = useTranslation();
  return (
    <AnimatePresence>
      {show && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          className={className}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export interface ChatPageProps {
  firstMessage?: string;
}

interface DragOverlayProps {
  isDragging: boolean;
}

function DragOverlay({ isDragging }: DragOverlayProps) {
  const { t } = useTranslation();
  return (
    <AnimatePresence>
      {isDragging && (
        <motion.div
          key="drag-overlay"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="relative z-40 pointer-events-none flex flex-col items-center justify-center gap-4 py-12"
        >
          {/* Icon with glow effect */}
          <motion.div
            initial={{ scale: 0.5, opacity: 0, y: 10 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.5, opacity: 0, y: 10 }}
            transition={{
              duration: 0.4,
              type: "spring",
              stiffness: 260,
              damping: 20,
            }}
            className="relative"
          >
            {/* Glow background */}
            <motion.div
              animate={{
                boxShadow: [
                  "0 0 20px rgba(59, 130, 246, 0)",
                  "0 0 40px rgba(59, 130, 246, 0.3)",
                  "0 0 20px rgba(59, 130, 246, 0)",
                ],
              }}
              transition={{
                duration: 2,
                repeat: Infinity,
                ease: "easeInOut",
              }}
              className="absolute inset-0 rounded-full"
            />

            {/* Icon */}
            <div className="relative text-blue-500 dark:text-blue-400">
              <SvgUploadCloud size={48} className="w-12 h-12" />
            </div>
          </motion.div>

          {/* Text label with animation */}
          <motion.div
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 5 }}
            transition={{ duration: 0.3, delay: 0.1 }}
            className="text-center"
          >
            <h3 className="text-base font-semibold text-text-darker dark:text-white">
              {t("chat.dragDropFiles")}
            </h3>
            <p className="text-xs text-text-light dark:text-text-light mt-1">
              {t("chat.releaseToUpload")}
            </p>
          </motion.div>

          {/* Floating animation for extra visual interest */}
          <motion.div
            animate={{
              y: [0, -6, 0],
            }}
            transition={{
              duration: 3,
              repeat: Infinity,
              ease: "easeInOut",
            }}
            className="mt-1"
          >
            <div className="text-xs text-text-light dark:text-text-light/60 font-medium tracking-wide">
              ↑
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

export default function AppPage({ firstMessage }: ChatPageProps) {
  const { t } = useTranslation();
  // Performance tracking
  // Keeping this here in case we need to track down slow renders in the future
  // const renderCount = useRef(0);
  // renderCount.current++;
  // const renderStartTime = performance.now();

  // useEffect(() => {
  //   const renderTime = performance.now() - renderStartTime;
  //   if (renderTime > 10) {
  //     console.log(
  //       `[ChatPage] Slow render #${renderCount.current}: ${renderTime.toFixed(
  //         2
  //       )}ms`
  //     );
  //   }
  // });

  const router = useRouter();
  const appFocus = useAppFocus();
  const { setAppMode } = useAppMode();
  const searchParams = useSearchParams();

  // Use SWR hooks for data fetching
  const {
    chatSessions,
    refreshChatSessions,
    currentChatSession,
    currentChatSessionId,
    isLoading: isLoadingChatSessions,
  } = useChatSessions();
  // handle redirect if chat page is disabled
  // NOTE: this must be done here, in a client component since
  // settings are passed in via Context and therefore aren't
  // available in server-side components
  const settings = useSettingsContext();
  const vectorDbEnabled = settings?.settings.vector_db_enabled !== false;
  const { ccPairs } = useCCPairs(vectorDbEnabled);
  const { tags } = useTags();
  const { documentSets } = useDocumentSets();
  const {
    currentMessageFiles,
    setCurrentMessageFiles,
    currentProjectId,
    currentProjectDetails,
    refreshCurrentProjectDetails,
    lastFailedFiles,
    clearLastFailedFiles,
  } = useProjectsContext();

  // When changing from project chat to main chat (or vice-versa), clear forced tools
  const { setForcedToolIds } = useForcedTools();
  useEffect(() => {
    setForcedToolIds([]);
  }, [currentProjectId, setForcedToolIds]);

  const isInitialLoad = useRef(true);

  const { agents, isLoading: isLoadingAgents } = useAgents();

  // Also fetch federated connectors for the sources list
  const { data: federatedConnectorsData } = useFederatedConnectors();

  const { user } = useUser();

  function processSearchParamsAndSubmitMessage(searchParamsString: string) {
    const newSearchParams = new URLSearchParams(searchParamsString);
    const message = newSearchParams?.get("user-prompt");

    filterManager.buildFiltersFromQueryString(
      newSearchParams.toString(),
      sources,
      documentSets.map((ds) => ds.name),
      tags
    );

    newSearchParams.delete(SEARCH_PARAM_NAMES.SEND_ON_LOAD);

    router.replace(`?${newSearchParams.toString()}`, { scroll: false });

    // If there's a message, submit it
    if (message) {
      onSubmit({
        message,
        currentMessageFiles,
        deepResearch: deepResearchEnabled,
      });
    }
  }

  const { selectedAgent, setSelectedAgentFromId, liveAgent } =
    useAgentController({
      selectedChatSession: currentChatSession,
    });

  const { deepResearchEnabled, toggleDeepResearch } = useDeepResearchToggle({
    chatSessionId: currentChatSessionId,
    agentId: selectedAgent?.id,
  });

  const [presentingDocument, setPresentingDocument] =
    useState<MinimalOnyxDocument | null>(null);

  const [dragActive, setDragActive] = useState(false);

  const llmManager = useLlmManager(currentChatSession ?? undefined, liveAgent);

  const {
    showOnboarding,
    onboardingDismissed,
    onboardingState,
    onboardingActions,
    llmDescriptors,
    isLoadingOnboarding,
    finishOnboarding,
    hideOnboarding,
  } = useShowOnboarding({
    liveAgent,
    isLoadingProviders: llmManager.isLoadingProviders,
    hasAnyProvider: llmManager.hasAnyProvider,
    isLoadingChatSessions,
    chatSessionsCount: chatSessions.length,
    userId: user?.id,
  });

  const noAgents = liveAgent === null || liveAgent === undefined;

  const availableSources: ValidSources[] = useMemo(() => {
    return ccPairs.map((ccPair) => ccPair.source);
  }, [ccPairs]);

  const sources: SourceMetadata[] = useMemo(() => {
    const uniqueSources = Array.from(new Set(availableSources));
    const regularSources = uniqueSources.map((source) =>
      getSourceMetadata(source)
    );

    // Add federated connectors as sources
    const federatedSources =
      federatedConnectorsData?.map((connector: FederatedConnectorDetail) => {
        return getSourceMetadata(connector.source);
      }) || [];

    // Combine sources and deduplicate based on internalName
    const allSources = [...regularSources, ...federatedSources];
    const deduplicatedSources = allSources.reduce((acc, source) => {
      const existing = acc.find((s) => s.internalName === source.internalName);
      if (!existing) {
        acc.push(source);
      }
      return acc;
    }, [] as SourceMetadata[]);

    return deduplicatedSources;
  }, [availableSources, federatedConnectorsData]);

  // Show toast if any files failed in ProjectsContext reconciliation
  useEffect(() => {
    if (lastFailedFiles && lastFailedFiles.length > 0) {
      const names = lastFailedFiles.map((f) => f.name).join(", ");
      toast.error(
        lastFailedFiles.length === 1
          ? t("chat.fileFailed", { name: names })
          : t("chat.filesFailed", { names: names })
      );
      clearLastFailedFiles();
    }
  }, [lastFailedFiles, clearLastFailedFiles]);

  const chatInputBarRef = useRef<AppInputBarHandle>(null);

  const filterManager = useFilters();

  const isDefaultAgent = useIsDefaultAgent({
    liveAgent,
    existingChatSessionId: currentChatSessionId,
    selectedChatSession: currentChatSession ?? undefined,
    settings,
  });

  const scrollContainerRef = useRef<ChatScrollContainerHandle>(null);
  const [showScrollButton, setShowScrollButton] = useState(false);

  // Reset scroll button when session changes
  useEffect(() => {
    setShowScrollButton(false);
  }, [currentChatSessionId]);

  const handleScrollToBottom = useCallback(() => {
    scrollContainerRef.current?.scrollToBottom();
  }, []);

  const resetInputBar = useCallback(() => {
    chatInputBarRef.current?.reset();
    setCurrentMessageFiles([]);
  }, [setCurrentMessageFiles]);

  // Add refs needed by useChatSessionController
  const chatSessionIdRef = useRef<string | null>(currentChatSessionId);
  const loadedIdSessionRef = useRef<string | null>(currentChatSessionId);
  const submitOnLoadPerformed = useRef<boolean>(false);

  function loadNewPageLogic(event: MessageEvent) {
    if (event.data.type === SUBMIT_MESSAGE_TYPES.PAGE_CHANGE) {
      try {
        const url = new URL(event.data.href);
        processSearchParamsAndSubmitMessage(url.searchParams.toString());
      } catch (error) {
        console.error("Error parsing URL:", error);
      }
    }
  }

  // Equivalent to `loadNewPageLogic`
  useEffect(() => {
    if (searchParams?.get(SEARCH_PARAM_NAMES.SEND_ON_LOAD)) {
      processSearchParamsAndSubmitMessage(searchParams.toString());
    }
  }, [searchParams, router]);

  useEffect(() => {
    window.addEventListener("message", loadNewPageLogic);

    return () => {
      window.removeEventListener("message", loadNewPageLogic);
    };
  }, []);

  const [selectedDocuments, setSelectedDocuments] = useState<OnyxDocument[]>(
    []
  );

  // Access chat state directly from the store
  const currentChatState = useCurrentChatState();
  const isReady = useIsReady();
  const documentSidebarVisible = useDocumentSidebarVisible();
  const updateCurrentDocumentSidebarVisible = useChatSessionStore(
    (state) => state.updateCurrentDocumentSidebarVisible
  );
  const messageHistory = useCurrentMessageHistory();

  // Determine anchor: second-to-last message (last user message before current response)
  const anchorMessage = messageHistory.at(-2) ?? messageHistory[0];
  const anchorNodeId = anchorMessage?.nodeId;
  const anchorSelector = anchorNodeId ? `#message-${anchorNodeId}` : undefined;

  // Auto-scroll preference from user settings
  const autoScrollEnabled = user?.preferences?.auto_scroll !== false;
  const isStreaming = currentChatState === "streaming";

  const refreshProjectDetailsAfterSubmit = useCallback(async () => {
    if (currentProjectId) {
      await refreshCurrentProjectDetails();
    }
  }, [currentProjectId, refreshCurrentProjectDetails]);

  const { onSubmit, stopGenerating, handleMessageSpecificFileUpload } =
    useChatController({
      filterManager,
      llmManager,
      availableAgents: agents,
      liveAgent,
      existingChatSessionId: currentChatSessionId,
      selectedDocuments,
      searchParams,
      resetInputBar,
      setSelectedAgentFromId,
      onSubmitComplete: refreshProjectDetailsAfterSubmit,
    });

  const { onMessageSelection, currentSessionFileTokenCount } =
    useChatSessionController({
      existingChatSessionId: currentChatSessionId,
      searchParams,
      filterManager,
      firstMessage,
      setSelectedAgentFromId,
      setSelectedDocuments,
      setCurrentMessageFiles,
      chatSessionIdRef,
      loadedIdSessionRef,
      chatInputBarRef,
      isInitialLoad,
      submitOnLoadPerformed,
      refreshChatSessions,
      onSubmit,
    });

  useSendMessageToParent();

  const retrievalEnabled = useMemo(() => {
    if (liveAgent) {
      return personaIncludesRetrieval(liveAgent);
    }
    return false;
  }, [liveAgent]);

  useEffect(() => {
    if (
      (!personaIncludesRetrieval &&
        (!selectedDocuments || selectedDocuments.length === 0) &&
        documentSidebarVisible) ||
      !currentChatSessionId
    ) {
      updateCurrentDocumentSidebarVisible(false);
    }
  }, [currentChatSessionId]);

  const [stackTraceModalContent, setStackTraceModalContent] = useState<
    string | null
  >(null);

  const handleResubmitLastMessage = useCallback(() => {
    // Grab the last user-type message
    const lastUserMsg = messageHistory
      .slice()
      .reverse()
      .find((m) => m.type === "user");
    if (!lastUserMsg) {
      toast.error(t("chat.noPreviousMessage"));
      return;
    }

    // We call onSubmit, passing a `messageOverride`
    onSubmit({
      message: lastUserMsg.message,
      currentMessageFiles: currentMessageFiles,
      deepResearch: deepResearchEnabled,
      messageIdToResend: lastUserMsg.messageId,
    });
  }, [messageHistory, onSubmit, currentMessageFiles, deepResearchEnabled]);

  const toggleDocumentSidebar = useCallback(() => {
    if (!documentSidebarVisible) {
      updateCurrentDocumentSidebarVisible(true);
    } else {
      updateCurrentDocumentSidebarVisible(false);
    }
  }, [documentSidebarVisible, updateCurrentDocumentSidebarVisible]);

  if (!user) {
    redirect("/auth/login");
  }

  const onChat = useCallback(
    (message: string) => {
      resetInputBar();
      onSubmit({
        message,
        currentMessageFiles,
        deepResearch: deepResearchEnabled,
      });
      if (showOnboarding || !onboardingDismissed) {
        finishOnboarding();
      }
    },
    [
      resetInputBar,
      onSubmit,
      currentMessageFiles,
      deepResearchEnabled,
      showOnboarding,
      onboardingDismissed,
      finishOnboarding,
    ]
  );
  const { submit: submitQuery, classification } = useQueryController();

  const defaultAppMode =
    (user?.preferences?.default_app_mode?.toLowerCase() as "chat" | "search") ??
    "chat";

  const isNewSession = appFocus.isNewSession();

  // 1. Reset the app-mode back to the user's default when navigating back to the "New Sessions" tab.
  // 2. If we're navigating away from the "New Session" tab after performing a search, we reset the app-input-bar.
  useEffect(() => {
    if (isNewSession) setAppMode(defaultAppMode);
    if (!isNewSession && classification === "search") resetInputBar();
  }, [isNewSession, defaultAppMode, classification, resetInputBar, setAppMode]);

  const handleSearchDocumentClick = useCallback(
    (doc: MinimalOnyxDocument) => setPresentingDocument(doc),
    []
  );

  const handleSwitchAgent = useCallback(
    (agent: (typeof agents)[0]) => {
      const params = new URLSearchParams();
      params.set(
        SEARCH_PARAM_NAMES.PERSONA_ID,
        String(agent.external_id ?? agent.id)
      );
      // Preserve project context when switching agent
      if (currentProjectId) {
        params.set(
          SEARCH_PARAM_NAMES.PROJECT_ID,
          String(currentProjectId)
        );
      }
      router.push(`/app?${params.toString()}`, { scroll: false });
    },
    [router, currentProjectId]
  );

  const handleBackToProject = useCallback(() => {
    if (currentProjectId) {
      const params = new URLSearchParams();
      params.set(
        SEARCH_PARAM_NAMES.PROJECT_ID,
        String(currentProjectId)
      );
      router.push(`/app?${params.toString()}`, { scroll: false });
    }
  }, [currentProjectId, router]);

  const handleAppInputBarSubmit = useCallback(
    async (message: string) => {
      // If we're in an existing chat session, always use chat mode
      // (appMode only applies to new sessions)
      if (currentChatSessionId) {
        resetInputBar();
        const additionalContext = currentProjectDetails?.project?.instructions
          ? `Project Instructions:\n${currentProjectDetails.project.instructions}\n\n`
          : "";
        onSubmit({
          message,
          currentMessageFiles,
          deepResearch: deepResearchEnabled,
          additionalContext,
        });
        if (showOnboarding || !onboardingDismissed) {
          finishOnboarding();
        }
        return;
      }

      // For new sessions, let the query controller handle routing.
      // resetInputBar is called inside onChat for chat-routed queries.
      // For search-routed queries, the input bar is intentionally kept
      // so the user can see and refine their search query.
      await submitQuery(message, onChat);
    },
    [
      currentChatSessionId,
      submitQuery,
      onChat,
      currentProjectDetails,
      resetInputBar,
      onSubmit,
      currentMessageFiles,
      deepResearchEnabled,
      showOnboarding,
      onboardingDismissed,
      finishOnboarding,
    ]
  );

  // Memoized callbacks for DocumentsSidebar
  const handleMobileDocumentSidebarClose = useCallback(() => {
    updateCurrentDocumentSidebarVisible(false);
  }, [updateCurrentDocumentSidebarVisible]);

  const handleDesktopDocumentSidebarClose = useCallback(() => {
    setTimeout(() => updateCurrentDocumentSidebarVisible(false), 300);
  }, [updateCurrentDocumentSidebarVisible]);

  const desktopDocumentSidebar =
    retrievalEnabled && !settings.isMobile ? (
      <div
        className={cn(
          "flex-shrink-0 overflow-hidden transition-all duration-300 ease-in-out",
          documentSidebarVisible ? "w-[25rem]" : "w-[0rem]"
        )}
      >
        <div className="h-full w-[25rem]">
          <DocumentsSidebar
            setPresentingDocument={setPresentingDocument}
            modal={false}
            closeSidebar={handleDesktopDocumentSidebarClose}
            selectedDocuments={selectedDocuments}
          />
        </div>
      </div>
    ) : null;

  // When no chat session exists but a project is selected, fetch the
  // total tokens for the project's files so upload UX can compare
  // against available context similar to session-based flows.
  const [projectContextTokenCount, setProjectContextTokenCount] = useState(0);
  // Fetch project-level token count when no chat session exists.
  // Note: useEffect cannot be async, so we define an inner async function (run)
  // and invoke it. The `cancelled` guard prevents setting state after the
  // component unmounts or when the dependencies change and a newer effect run
  // supersedes an older in-flight request.
  useEffect(() => {
    let cancelled = false;
    async function run() {
      if (!currentChatSessionId && currentProjectId !== null) {
        try {
          const total = await getProjectTokenCount(currentProjectId);
          if (!cancelled) setProjectContextTokenCount(total || 0);
        } catch {
          if (!cancelled) setProjectContextTokenCount(0);
        }
      } else {
        setProjectContextTokenCount(0);
      }
    }
    run();
    return () => {
      cancelled = true;
    };
  }, [currentChatSessionId, currentProjectId, currentProjectDetails?.files]);

  // Available context tokens source of truth:
  // - If a chat session exists, fetch from session API (dynamic per session/model)
  // - If no session, derive from the default/current persona's max document tokens
  const [availableContextTokens, setAvailableContextTokens] = useState<number>(
    DEFAULT_CONTEXT_TOKENS * 0.5
  );
  useEffect(() => {
    let cancelled = false;
    async function run() {
      try {
        if (currentChatSessionId) {
          const available =
            await getAvailableContextTokens(currentChatSessionId);
          const capped_context_tokens =
            (available ?? DEFAULT_CONTEXT_TOKENS) * 0.5;
          if (!cancelled) setAvailableContextTokens(capped_context_tokens);
        } else {
          const personaId = (selectedAgent || liveAgent)?.id;
          if (personaId !== undefined && personaId !== null) {
            const maxTokens = await getMaxSelectedDocumentTokens(personaId);
            const capped_context_tokens =
              (maxTokens ?? DEFAULT_CONTEXT_TOKENS) * 0.5;
            if (!cancelled) setAvailableContextTokens(capped_context_tokens);
          } else if (!cancelled) {
            setAvailableContextTokens(DEFAULT_CONTEXT_TOKENS * 0.5);
          }
        }
      } catch (e) {
        if (!cancelled) setAvailableContextTokens(DEFAULT_CONTEXT_TOKENS * 0.5);
      }
    }
    run();
    return () => {
      cancelled = true;
    };
  }, [currentChatSessionId, selectedAgent?.id, liveAgent?.id]);

  // handle error case where no assistants are available
  // Only show this after agents have loaded to prevent flash during initial load
  if (noAgents && !isLoadingAgents) {
    return <NoAgentModal />;
  }

  const hasStarterMessages = (liveAgent?.starter_messages?.length ?? 0) > 0;

  const isSearch = classification === "search";
  const gridStyle = {
    gridTemplateColumns: "1fr",
    gridTemplateRows: isSearch
      ? "0fr auto 1fr"
      : appFocus.isChat()
        ? "1fr auto 0fr"
        : appFocus.isProject()
          ? "auto auto 1fr"
          : "1fr auto 1fr",
  };

  if (!isReady) return <OnyxInitializingLoader />;

  return (
    <>
      <AppPopup />

      {retrievalEnabled && documentSidebarVisible && settings.isMobile && (
        <div className="md:hidden">
          <Modal
            open
            onOpenChange={() => updateCurrentDocumentSidebarVisible(false)}
          >
            <Modal.Content>
              <Modal.Header
                icon={SvgFileText}
                title={t("chat.sources")}
                onClose={() => updateCurrentDocumentSidebarVisible(false)}
              />
              <Modal.Body>
                {/* IMPORTANT: this is a memoized component, and it's very important
                for performance reasons that this stays true. MAKE SURE that all function
                props are wrapped in useCallback. */}
                <DocumentsSidebar
                  setPresentingDocument={setPresentingDocument}
                  modal
                  closeSidebar={handleMobileDocumentSidebarClose}
                  selectedDocuments={selectedDocuments}
                />
              </Modal.Body>
            </Modal.Content>
          </Modal>
        </div>
      )}

      {presentingDocument && (
        <PreviewModal
          presentingDocument={presentingDocument}
          onClose={() => setPresentingDocument(null)}
        />
      )}

      {stackTraceModalContent && (
        <ExceptionTraceModal
          onOutsideClick={() => setStackTraceModalContent(null)}
          exceptionTrace={stackTraceModalContent}
        />
      )}

      <FederatedOAuthModal />

      <AppLayouts.Root enableBackground={!appFocus.isProject()}>
        <Dropzone
          onDrop={(acceptedFiles) => {
            handleMessageSpecificFileUpload(acceptedFiles);
            setDragActive(false);
          }}
          onDragEnter={() => setDragActive(true)}
          onDragLeave={() => setDragActive(false)}
          noClick
        >
          {({ getRootProps }) => (
            <div
              className="h-full w-full flex flex-col items-center outline-none relative"
              {...getRootProps({ tabIndex: -1 })}
            >
              {/* Main content grid — 3 rows, animated */}
              <div
                className="flex-1 w-full grid min-h-0 transition-[grid-template-rows] duration-150 ease-in-out"
                style={gridStyle}
              >
                {/* ── Top row: ChatUI / WelcomeMessage / ProjectUI ── */}
                <div className="row-start-1 min-h-0 overflow-hidden flex flex-col items-center">
                  {/* ChatUI */}
                  <Fade
                    show={
                      appFocus.isChat() && !!currentChatSessionId && !!liveAgent
                    }
                    className="h-full w-full flex flex-col items-center"
                  >
                    <ChatScrollContainer
                      ref={scrollContainerRef}
                      sessionId={currentChatSessionId!}
                      anchorSelector={anchorSelector}
                      autoScroll={autoScrollEnabled}
                      isStreaming={isStreaming}
                      onScrollButtonVisibilityChange={setShowScrollButton}
                    >
                      <ChatUI
                        liveAgent={liveAgent!}
                        llmManager={llmManager}
                        deepResearchEnabled={deepResearchEnabled}
                        currentMessageFiles={currentMessageFiles}
                        setPresentingDocument={setPresentingDocument}
                        onSubmit={onSubmit}
                        onMessageSelection={onMessageSelection}
                        stopGenerating={stopGenerating}
                        onResubmit={handleResubmitLastMessage}
                        anchorNodeId={anchorNodeId}
                      />
                    </ChatScrollContainer>
                  </Fade>

                  {/* ProjectUI */}
                  {appFocus.isProject() && (
                    <div className="w-full max-h-[50vh] overflow-y-auto overscroll-y-none">
                      <ProjectContextPanel
                        projectTokenCount={projectContextTokenCount}
                        availableContextTokens={availableContextTokens}
                        setPresentingDocument={setPresentingDocument}
                      />
                    </div>
                  )}

                  {/* WelcomeMessageUI */}
                  <Fade
                    show={
                      (appFocus.isNewSession() || appFocus.isAgent()) &&
                      !classification
                    }
                    className="w-full flex-1 flex flex-col items-center justify-end"
                  >
                    <WelcomeMessage
                      agent={liveAgent}
                      isDefaultAgent={isDefaultAgent}
                    />
                    <Spacer rem={1.5} />
                  </Fade>
                </div>

                {/* ── Middle-center: AppInputBar ── */}
                <div className="row-start-2 flex flex-col items-center">
                  <div className="relative w-full max-w-[var(--app-page-main-content-width)] flex flex-col">
                    {/* Back button - shown when chat is opened within a project */}
                    {appFocus.isChat() && 
                      currentChatSessionId && 
                      currentProjectId && 
                      currentProjectDetails?.project && (
                      <div className="mb-2 flex items-center gap-2 px-2">
                        <button
                          onClick={handleBackToProject}
                          aria-label={t("projectContextPanel.backToProject")}
                          className="inline-flex items-center gap-1 rounded-lg px-2 py-1 hover:bg-background-tint-02 transition-colors"
                        >
                          <SvgChevronLeft size={16} className="w-4 h-4" />
                          <span className="text-xs font-medium text-text-light">
                            {currentProjectDetails.project.name}
                          </span>
                        </button>
                      </div>
                    )}

                    {/* Scroll to bottom button - positioned absolutely above AppInputBar */}
                    {appFocus.isChat() && showScrollButton && (
                      <div className="absolute top-[-3.5rem] self-center">
                        <Button
                          icon={SvgChevronDown}
                          onClick={handleScrollToBottom}
                          aria-label={t("chat.scrollToBottom")}
                          prominence="secondary"
                        />
                      </div>
                    )}

                    {/* OnboardingUI */}
                    {(appFocus.isNewSession() || appFocus.isAgent()) &&
                      !classification &&
                      (showOnboarding || !user?.personalization?.name) &&
                      !onboardingDismissed && (
                        <OnboardingFlow
                          showOnboarding={showOnboarding}
                          handleHideOnboarding={hideOnboarding}
                          handleFinishOnboarding={finishOnboarding}
                          state={onboardingState}
                          actions={onboardingActions}
                          llmDescriptors={llmDescriptors}
                        />
                      )}

                    {/*
                      # Note (@raunakab)

                      `shadow-01` on AppInputBar extends ~14px below the element
                      (2px offset + 12px blur). Because the content area in `Root`
                      (app-layouts.tsx) uses `overflow-auto`, shadows that exceed
                      the container bounds are clipped.

                      The animated spacer divs above and below the AppInputBar
                      provide 14px of breathing room so the shadow renders fully.
                      They transition between h-0 and h-[14px] depending on whether
                      the classification is "search" (spacer above) or "chat"
                      (spacer below).

                      There is a corresponding note inside `app-layouts.tsx`
                      (Footer) that explains why the Footer removes its top
                      padding during chat to compensate for this extra space.
                    */}
                    <motion.div
                      layout
                      className={cn(
                        "relative w-full transition-all duration-300 ease-in-out overflow-hidden rounded-xl",
                        dragActive
                          ? "bg-white/5 dark:bg-black/10 backdrop-blur-sm border border-blue-400/20 dark:border-blue-500/10"
                          : ""
                      )}
                      animate={{
                        minHeight: dragActive ? "220px" : "auto",
                      }}
                      transition={{ duration: 0.3, ease: "easeInOut" }}
                    >
                      {dragActive && <DragOverlay isDragging={dragActive} />}
                      <div
                        className={cn(
                          "transition-all duration-150 ease-in-out overflow-hidden",
                          classification === "search" ? "h-[14px]" : "h-0"
                        )}
                      />
                      <AppInputBar
                        ref={chatInputBarRef}
                        deepResearchEnabled={deepResearchEnabled}
                        toggleDeepResearch={toggleDeepResearch}
                        toggleDocumentSidebar={toggleDocumentSidebar}
                        filterManager={filterManager}
                        llmManager={llmManager}
                        removeDocs={() => setSelectedDocuments([])}
                        retrievalEnabled={retrievalEnabled}
                        selectedDocuments={selectedDocuments}
                        initialMessage={
                          searchParams?.get(SEARCH_PARAM_NAMES.USER_PROMPT) ||
                          ""
                        }
                        stopGenerating={stopGenerating}
                        onSubmit={handleAppInputBarSubmit}
                        chatState={currentChatState}
                        currentSessionFileTokenCount={
                          currentChatSessionId
                            ? currentSessionFileTokenCount
                            : projectContextTokenCount
                        }
                        availableContextTokens={availableContextTokens}
                        selectedAgent={selectedAgent || liveAgent}
                        agents={agents}
                        onSwitchAgent={handleSwitchAgent}
                        handleFileUpload={handleMessageSpecificFileUpload}
                        setPresentingDocument={setPresentingDocument}
                        // Intentionally enabled during name-only onboarding (showOnboarding=false)
                        // since LLM providers are already configured and the user can chat.
                        disabled={
                          (!llmManager.isLoadingProviders &&
                            llmManager.hasAnyProvider === false) ||
                          (showOnboarding &&
                            !isLoadingOnboarding &&
                            onboardingState.currentStep !==
                              OnboardingStep.Complete)
                        }
                      />
                      <div
                        className={cn(
                          "transition-all duration-150 ease-in-out overflow-hidden",
                          appFocus.isChat() ? "h-[14px]" : "h-0"
                        )}
                      />
                    </motion.div>
                  </div>
                </div>

                {/* ── Bottom: SearchResults + SourceFilter / Suggestions / ProjectChatList ── */}
                <div className="row-start-3 min-h-0 overflow-hidden flex flex-col items-center w-full">
                  {/* Agent description below input */}
                  {(appFocus.isNewSession() || appFocus.isAgent()) &&
                    !isDefaultAgent && (
                      <>
                        <Spacer rem={1} />
                        <AgentDescription agent={liveAgent} />
                        <Spacer rem={1.5} />
                      </>
                    )}
                  {/* ProjectChatSessionList */}
                  {appFocus.isProject() && (
                    <div className="w-full max-w-[var(--app-page-main-content-width)] h-full overflow-y-auto overscroll-y-none mx-auto">
                      <ProjectChatSessionList />
                    </div>
                  )}

                  {/* SuggestionsUI */}
                  <Fade
                    show={
                      (appFocus.isNewSession() || appFocus.isAgent()) &&
                      hasStarterMessages
                    }
                    className="h-full flex-1 w-full max-w-[var(--app-page-main-content-width)]"
                  >
                    <Spacer rem={0.5} />
                    <Suggestions onSubmit={onSubmit} />
                  </Fade>

                  {/* SearchUI */}
                  <Fade
                    show={isSearch}
                    className="h-full flex-1 w-full max-w-[var(--app-page-main-content-width)] px-1 flex flex-col"
                  >
                    <Spacer rem={0.75} />
                    <SearchUI onDocumentClick={handleSearchDocumentClick} />
                  </Fade>
                </div>
              </div>
            </div>
          )}
        </Dropzone>
      </AppLayouts.Root>

      {desktopDocumentSidebar}
    </>
  );
}
