import { create } from "zustand";
import type { DocumentContextRef } from "@/lib/api/domains/documents/types";

export type DocumentPanelTab =
  | "preview"
  | "changes"
  | "compare"
  | "history"
  | "edit";

export interface LegacyFile {
  fileId: string;
  filename: string;
  mimeType: string;
}

/** The user's unsaved edit. Lives here so no remount or tab switch can lose it. */
export interface EditSession {
  documentId: string;
  baseRevisionNo: number;
  /** The text when editing started; the edit is dirty while `text` differs. */
  originalText: string;
  text: string;
  /** The base was already older than the head when editing started. */
  staleAtStart: boolean;
  /** Head reported by a 409; the ConflictNotice is shown while set. */
  conflictHeadNo: number | null;
  /** Head the editor shows a merge against ("apply on latest"). */
  mergeWith: number | null;
}

/** A navigation held back until the user decides about their unsaved edit. */
export interface PendingDiscard {
  proceed: () => void;
  cancel?: () => void;
}

export interface DocumentPanelData {
  isOpen: boolean;
  /** True while a DocumentWorkspace is mounted (false in shared chats). */
  hostMounted: boolean;
  documentId: string | null;
  legacyFile: LegacyFile | null;
  /** Viewed draft; null follows the head. */
  revisionNo: number | null;
  knownHead: number | null;
  tab: DocumentPanelTab;
  compare: { left: number; right: number } | null;
  edit: EditSession | null;
  /** A newer head that arrived while the user looked at an older draft or edited. */
  pendingHead: number | null;
  contextEnabled: boolean;
  pendingDiscard: PendingDiscard | null;
}

interface DocumentPanelActions {
  openDocument: (
    documentId: string,
    revisionNo?: number,
    tab?: DocumentPanelTab
  ) => void;
  openLegacyFile: (file: LegacyFile) => void;
  close: () => void;
  /** Guarded variants: ask first while an edit has unsaved changes. */
  requestClose: () => void;
  requestOpenDocument: (
    documentId: string,
    revisionNo?: number,
    tab?: DocumentPanelTab
  ) => void;
  requestOpenLegacyFile: (file: LegacyFile) => void;
  requestDiscardDraft: () => void;
  /**
   * Runs `proceed` now when nothing is unsaved (returns true); otherwise holds
   * it for the confirmation dialog (returns false).
   */
  guardUnsaved: (proceed: () => void, cancel?: () => void) => boolean;
  confirmDiscard: () => void;
  keepEditing: () => void;
  setHostMounted: (mounted: boolean) => void;
  selectRevision: (revisionNo: number) => void;
  setTab: (tab: DocumentPanelTab) => void;
  setCompare: (left: number, right: number) => void;
  syncHead: (documentId: string, head: number) => void;
  revisionPublished: (documentId: string, revisionNo: number) => void;
  editDraft: (baseRevisionNo: number, text: string) => void;
  updateDraft: (text: string) => void;
  markConflict: (headRevisionNo: number) => void;
  rebaseDraft: (headRevisionNo: number, options: { review: boolean }) => void;
  discardDraft: () => void;
  removeContext: () => void;
}

export type DocumentPanelState = DocumentPanelData & DocumentPanelActions;

export const initialDocumentPanelState: DocumentPanelData = {
  isOpen: false,
  hostMounted: false,
  documentId: null,
  legacyFile: null,
  revisionNo: null,
  knownHead: null,
  tab: "preview",
  compare: null,
  edit: null,
  pendingHead: null,
  contextEnabled: true,
  pendingDiscard: null,
};

export function selectIsDirty(state: DocumentPanelData): boolean {
  return state.edit !== null && state.edit.text !== state.edit.originalText;
}

export function selectViewedRevision(state: DocumentPanelData): number | null {
  return state.revisionNo ?? state.knownHead;
}

export function selectDocumentContext(
  state: DocumentPanelData
): DocumentContextRef | null {
  const revisionNo = selectViewedRevision(state);
  if (
    !state.isOpen ||
    !state.documentId ||
    !state.contextEnabled ||
    !revisionNo
  )
    return null;
  return { document_id: state.documentId, revision_no: revisionNo };
}

export const useDocumentPanelStore = create<DocumentPanelState>()(
  (set, get) => ({
    ...initialDocumentPanelState,

    openDocument: (documentId, revisionNo, tab = "preview") =>
      set((state) => ({
        ...initialDocumentPanelState,
        hostMounted: state.hostMounted,
        isOpen: true,
        documentId,
        revisionNo: revisionNo ?? null,
        knownHead: state.documentId === documentId ? state.knownHead : null,
        // A draft 1 has nothing to diff against.
        tab: tab === "changes" && (revisionNo ?? 0) <= 1 ? "preview" : tab,
        // An unsaved edit of the same document survives re-opening it.
        edit: state.edit?.documentId === documentId ? state.edit : null,
      })),

    openLegacyFile: (file) =>
      set((state) => ({
        ...initialDocumentPanelState,
        hostMounted: state.hostMounted,
        isOpen: true,
        legacyFile: file,
      })),

    close: () =>
      set((state) => ({
        ...initialDocumentPanelState,
        hostMounted: state.hostMounted,
      })),

    guardUnsaved: (proceed, cancel) => {
      if (!selectIsDirty(get())) {
        proceed();
        return true;
      }
      set({ pendingDiscard: { proceed, cancel } });
      return false;
    },

    confirmDiscard: () => {
      const pending = get().pendingDiscard;
      if (!pending) return;
      set({ pendingDiscard: null });
      pending.proceed();
    },

    keepEditing: () => {
      const pending = get().pendingDiscard;
      if (!pending) return;
      set({ pendingDiscard: null });
      pending.cancel?.();
    },

    requestClose: () => {
      get().guardUnsaved(() => get().close());
    },

    requestOpenDocument: (documentId, revisionNo, tab) => {
      const edit = get().edit;
      const open = () => get().openDocument(documentId, revisionNo, tab);
      if (edit?.documentId === documentId) open();
      else get().guardUnsaved(open);
    },

    requestOpenLegacyFile: (file) => {
      get().guardUnsaved(() => get().openLegacyFile(file));
    },

    requestDiscardDraft: () => {
      get().guardUnsaved(() => get().discardDraft());
    },

    setHostMounted: (hostMounted) => set({ hostMounted }),

    selectRevision: (revisionNo) =>
      set((state) => ({
        revisionNo,
        pendingHead:
          state.pendingHead !== null && revisionNo >= state.pendingHead
            ? null
            : state.pendingHead,
        tab: state.tab === "edit" ? "preview" : state.tab,
      })),

    setTab: (tab) =>
      set((state) => (tab === "edit" && !state.edit ? {} : { tab })),

    setCompare: (left, right) =>
      set({ compare: { left, right }, tab: "compare" }),

    syncHead: (documentId, head) =>
      set((state) =>
        state.documentId === documentId
          ? { knownHead: Math.max(head, state.knownHead ?? 0) }
          : {}
      ),

    revisionPublished: (documentId, revisionNo) => {
      const state = get();
      if (state.documentId !== documentId) return;
      const previousHead = state.knownHead;
      const knownHead = Math.max(revisionNo, previousHead ?? 0);
      const viewed = selectViewedRevision(state);
      const editing = state.edit?.documentId === documentId;
      const onHead = state.revisionNo === null || viewed === previousHead;
      if (!editing && onHead) {
        set({ knownHead, revisionNo: knownHead, pendingHead: null });
      } else {
        set({ knownHead, pendingHead: knownHead });
      }
    },

    editDraft: (baseRevisionNo, text) =>
      set((state) => {
        if (!state.documentId) return {};
        if (state.edit?.documentId === state.documentId) return { tab: "edit" };
        return {
          tab: "edit",
          edit: {
            documentId: state.documentId,
            baseRevisionNo,
            originalText: text,
            staleAtStart:
              state.knownHead !== null && baseRevisionNo < state.knownHead,
            text,
            conflictHeadNo: null,
            mergeWith: null,
          },
        };
      }),

    updateDraft: (text) =>
      set((state) => (state.edit ? { edit: { ...state.edit, text } } : {})),

    markConflict: (headRevisionNo) =>
      set((state) =>
        state.edit
          ? {
              edit: { ...state.edit, conflictHeadNo: headRevisionNo },
              knownHead: Math.max(headRevisionNo, state.knownHead ?? 0),
            }
          : {}
      ),

    rebaseDraft: (headRevisionNo, { review }) =>
      set((state) =>
        state.edit
          ? {
              tab: "edit",
              edit: {
                ...state.edit,
                baseRevisionNo: headRevisionNo,
                staleAtStart: false,
                conflictHeadNo: null,
                mergeWith: review ? headRevisionNo : null,
              },
            }
          : {}
      ),

    discardDraft: () =>
      set((state) => ({
        edit: null,
        tab: state.tab === "edit" ? "preview" : state.tab,
      })),

    removeContext: () => set({ contextEnabled: false }),
  })
);
