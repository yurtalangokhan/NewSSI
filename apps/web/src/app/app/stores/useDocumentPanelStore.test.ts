import { beforeEach, describe, expect, it } from "@jest/globals";
import {
  initialDocumentPanelState,
  selectDocumentContext,
  selectIsDirty,
  selectViewedRevision,
  useDocumentPanelStore,
} from "./useDocumentPanelStore";

const store = () => useDocumentPanelStore.getState();

describe("useDocumentPanelStore", () => {
  beforeEach(() => useDocumentPanelStore.setState(initialDocumentPanelState));

  it("opens a document at a revision and tab", () => {
    store().openDocument("d", 2, "changes");
    expect(store()).toMatchObject({
      isOpen: true,
      documentId: "d",
      revisionNo: 2,
      tab: "changes",
      contextEnabled: true,
    });
  });

  it("falls back to preview when opening changes on the first draft", () => {
    store().openDocument("d", 1, "changes");
    expect(store().tab).toBe("preview");
  });

  it("follows the head when the viewer was on the head", () => {
    store().openDocument("d", 3);
    store().syncHead("d", 3);
    store().revisionPublished("d", 4);
    expect(store()).toMatchObject({
      revisionNo: 4,
      knownHead: 4,
      pendingHead: null,
    });
  });

  it("stays on an older draft and records the new head as pending", () => {
    store().openDocument("d", 2);
    store().syncHead("d", 3);
    store().revisionPublished("d", 4);
    expect(store()).toMatchObject({
      revisionNo: 2,
      knownHead: 4,
      pendingHead: 4,
    });
  });

  it("never moves an open editor; the new head becomes pending", () => {
    store().openDocument("d", 3);
    store().syncHead("d", 3);
    store().editDraft(3, "# mine");
    store().revisionPublished("d", 4);
    expect(store()).toMatchObject({
      tab: "edit",
      revisionNo: 3,
      pendingHead: 4,
    });
    expect(store().edit?.text).toBe("# mine");
  });

  it("ignores announcements for another document", () => {
    store().openDocument("d", 1);
    store().revisionPublished("other", 9);
    expect(store()).toMatchObject({ revisionNo: 1, pendingHead: null });
  });

  it("keeps the user's text through a conflict and both resolutions", () => {
    store().openDocument("d", 3);
    store().editDraft(3, "# mine");
    store().markConflict(5);
    expect(store().edit).toMatchObject({
      text: "# mine",
      conflictHeadNo: 5,
      baseRevisionNo: 3,
    });

    store().setTab("compare");
    expect(store().edit?.text).toBe("# mine");

    store().rebaseDraft(5, { review: true });
    expect(store().edit).toMatchObject({
      text: "# mine",
      baseRevisionNo: 5,
      conflictHeadNo: null,
      mergeWith: 5,
    });
    expect(store().tab).toBe("edit");

    store().rebaseDraft(5, { review: false });
    expect(store().edit).toMatchObject({ mergeWith: null, baseRevisionNo: 5 });
  });

  it("resumes an existing edit session instead of replacing it", () => {
    store().openDocument("d", 3);
    store().editDraft(3, "# mine");
    store().updateDraft("# mine 2");
    store().setTab("preview");
    store().editDraft(3, "# server text");
    expect(store().edit?.text).toBe("# mine 2");
  });

  it("builds document_context from the viewed draft unless removed", () => {
    store().openDocument("d");
    expect(selectDocumentContext(store())).toBeNull();
    store().syncHead("d", 3);
    expect(selectViewedRevision(store())).toBe(3);
    expect(selectDocumentContext(store())).toEqual({
      document_id: "d",
      revision_no: 3,
    });
    store().removeContext();
    expect(selectDocumentContext(store())).toBeNull();
  });

  it("has no document_context for a legacy file or a closed panel", () => {
    store().openLegacyFile({
      fileId: "f",
      filename: "a.pdf",
      mimeType: "application/pdf",
    });
    expect(selectDocumentContext(store())).toBeNull();
    store().close();
    expect(store()).toMatchObject({
      isOpen: false,
      documentId: null,
      legacyFile: null,
      edit: null,
    });
  });
});

describe("unsaved edit guard", () => {
  const dirtyEdit = () => {
    store().openDocument("d", 3);
    store().editDraft(3, "# base");
    store().updateDraft("# base\nmine");
  };

  beforeEach(() => useDocumentPanelStore.setState(initialDocumentPanelState));

  it("is dirty only when the text differs from the text edit started with", () => {
    store().openDocument("d", 3);
    expect(selectIsDirty(store())).toBe(false);
    store().editDraft(3, "# base");
    expect(selectIsDirty(store())).toBe(false);
    store().updateDraft("# base!");
    expect(selectIsDirty(store())).toBe(true);
    store().updateDraft("# base");
    expect(selectIsDirty(store())).toBe(false);
  });

  it("records whether the edit started from a draft older than the head", () => {
    store().openDocument("d", 2);
    store().syncHead("d", 3);
    store().editDraft(2, "# old");
    expect(store().edit?.staleAtStart).toBe(true);

    store().rebaseDraft(3, { review: false });
    expect(store().edit?.staleAtStart).toBe(false);

    store().discardDraft();
    store().selectRevision(3);
    store().editDraft(3, "# head");
    expect(store().edit?.staleAtStart).toBe(false);
  });

  it("stays dirty across a rebase onto the head", () => {
    dirtyEdit();
    store().markConflict(4);
    store().rebaseDraft(4, { review: true });
    expect(selectIsDirty(store())).toBe(true);
  });

  it("runs guarded actions immediately when nothing is unsaved", () => {
    store().openDocument("d", 3);
    store().editDraft(3, "# base");
    const proceed = jest.fn();
    expect(store().guardUnsaved(proceed)).toBe(true);
    expect(proceed).toHaveBeenCalledTimes(1);
    expect(store().pendingDiscard).toBeNull();
  });

  it("holds a guarded action until the user confirms", () => {
    dirtyEdit();
    const proceed = jest.fn();
    expect(store().guardUnsaved(proceed)).toBe(false);
    expect(proceed).not.toHaveBeenCalled();
    expect(store().pendingDiscard).not.toBeNull();

    store().confirmDiscard();
    expect(proceed).toHaveBeenCalledTimes(1);
    expect(store().pendingDiscard).toBeNull();
  });

  it("keeps the edit and reports the cancel when the user keeps editing", () => {
    dirtyEdit();
    const proceed = jest.fn();
    const cancel = jest.fn();
    store().guardUnsaved(proceed, cancel);
    store().keepEditing();
    expect(proceed).not.toHaveBeenCalled();
    expect(cancel).toHaveBeenCalledTimes(1);
    expect(store().edit?.text).toBe("# base\nmine");
    expect(store().pendingDiscard).toBeNull();
  });

  it("requestClose closes at once when clean and asks when dirty", () => {
    store().openDocument("d", 3);
    store().requestClose();
    expect(store().isOpen).toBe(false);

    dirtyEdit();
    store().requestClose();
    expect(store().isOpen).toBe(true);
    expect(store().pendingDiscard).not.toBeNull();
    store().confirmDiscard();
    expect(store()).toMatchObject({ isOpen: false, edit: null });
  });

  it("asks before opening another document or a legacy file", () => {
    dirtyEdit();
    store().requestOpenDocument("other", 1);
    expect(store().documentId).toBe("d");
    store().confirmDiscard();
    expect(store()).toMatchObject({ documentId: "other", edit: null });

    useDocumentPanelStore.setState(initialDocumentPanelState);
    dirtyEdit();
    store().requestOpenLegacyFile({
      fileId: "f",
      filename: "a.pdf",
      mimeType: "application/pdf",
    });
    expect(store().legacyFile).toBeNull();
    store().confirmDiscard();
    expect(store().legacyFile?.fileId).toBe("f");
  });

  it("does not ask when re-opening the document being edited", () => {
    dirtyEdit();
    store().requestOpenDocument("d", 3);
    expect(store().pendingDiscard).toBeNull();
    expect(store().edit?.text).toBe("# base\nmine");
  });

  it("asks before Cancel discards a dirty edit", () => {
    dirtyEdit();
    store().requestDiscardDraft();
    expect(store().edit).not.toBeNull();
    store().confirmDiscard();
    expect(store().edit).toBeNull();
  });
});
