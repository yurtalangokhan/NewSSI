import { useRef, useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { MemoryItem } from "@/lib/types";

export interface LocalMemory {
  id: number;
  dbId: string | null; // UUID from backend, null for unsaved new items
  content: string;
  isNew: boolean;
}

export const MAX_MEMORY_LENGTH = 200;
export const MAX_MEMORY_COUNT = 10;

interface UseMemoryManagerArgs {
  memories: MemoryItem[];
  onSaveMemories: (memories: MemoryItem[]) => Promise<boolean>;
  onDeleteMemory?: (id: string) => Promise<boolean>;
  onNotify: (message: string, type: "success" | "error") => void;
}

export function useMemoryManager({
  memories,
  onSaveMemories,
  onDeleteMemory,
  onNotify,
}: UseMemoryManagerArgs) {
  const { t } = useTranslation();
  const [localMemories, setLocalMemories] = useState<LocalMemory[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const initialMemoriesRef = useRef<MemoryItem[]>([]);
  const isSavingRef = useRef(false);
  const saveQueueRef = useRef<Promise<void>>(Promise.resolve());

  const queueSave = useCallback(
    async (
      newMemories: MemoryItem[],
      successMessage: string,
      errorMessage: string,
      onSuccess?: () => void
    ): Promise<boolean> => {
      let success = false;

      saveQueueRef.current = saveQueueRef.current.then(async () => {
        isSavingRef.current = true;
        try {
          success = await onSaveMemories(newMemories);
          if (success) {
            initialMemoriesRef.current = newMemories;
            onSuccess?.();
            onNotify(successMessage, "success");
          } else {
            onNotify(errorMessage, "error");
          }
        } catch {
          success = false;
          onNotify(errorMessage, "error");
        } finally {
          isSavingRef.current = false;
        }
      });

      await saveQueueRef.current;
      return success;
    },
    [onNotify, onSaveMemories]
  );

  // Initialize local memories from props
  useEffect(() => {
    const existingMemories: LocalMemory[] = memories.map((mem, index) => ({
      id: index + 1,
      dbId: mem.id,
      content: mem.content,
      isNew: false,
    }));

    setLocalMemories((prev) => {
      const emptyNewItems = prev.filter((m) => m.isNew && !m.content.trim());
      return [...emptyNewItems, ...existingMemories];
    });
    initialMemoriesRef.current = memories;
  }, [memories]);

  const canAddMemory = localMemories.length < MAX_MEMORY_COUNT;

  const handleAddMemory = useCallback((): number | null => {
    if (localMemories.length >= MAX_MEMORY_COUNT) {
      return null;
    }

    const existingEmpty = localMemories.find(
      (m) => m.isNew && !m.content.trim()
    );
    if (existingEmpty) {
      return existingEmpty.id;
    }

    // Save any unsaved new item with content before creating a new one
    const unsavedNewItem = localMemories.find(
      (m) => m.isNew && m.content.trim()
    );
    if (unsavedNewItem && !isSavingRef.current) {
      const newMemories: MemoryItem[] = localMemories
        .filter((m) => m.content.trim())
        .map((m) => ({
          id: m.dbId ?? "",
          content: m.content,
          source: "manual" as const,
          time_created: "",
          time_updated: "",
        }));

      const memoriesChanged =
        JSON.stringify(newMemories) !==
        JSON.stringify(initialMemoriesRef.current);

      if (memoriesChanged) {
        void queueSave(
          newMemories,
          t("memories.memorySaved"),
          t("memories.memorySaveFailed")
        );
      }
    }

    const newId = Date.now();
    setLocalMemories((prev) => [
      { id: newId, dbId: null, content: "", isNew: true },
      ...prev,
    ]);
    return newId;
  }, [localMemories, queueSave, t]);

  const handleUpdateMemory = useCallback((index: number, value: string) => {
    setLocalMemories((prev) =>
      prev.map((memory, i) =>
        i === index ? { ...memory, content: value } : memory
      )
    );
  }, []);

  const handleRemoveMemory = useCallback(
    async (index: number) => {
      const memory = localMemories[index];
      if (!memory) return;

      if (memory.isNew) {
        setLocalMemories((prev) => prev.filter((_, i) => i !== index));
        return;
      }

      // If we have a direct delete callback and a backend ID, use it
      if (onDeleteMemory && memory.dbId) {
        const success = await onDeleteMemory(memory.dbId);
        if (success) {
          setLocalMemories((prev) => prev.filter((_, i) => i !== index));
          onNotify(t("memories.memoryDeleted"), "success");
        } else {
          onNotify(t("memories.memoryDeleteFailed"), "error");
        }
        return;
      }

      // Fallback: save the remaining list
      const newMemories: MemoryItem[] = localMemories
        .filter((_, i) => i !== index)
        .filter((m) => !m.isNew || m.content.trim())
        .map((m) => ({
          id: m.dbId ?? "",
          content: m.content,
          source: "manual" as const,
          time_created: "",
          time_updated: "",
        }));

      const success = await queueSave(
        newMemories,
        t("memories.memoryDeleted"),
        t("memories.memoryDeleteFailed")
      );
      if (success) {
        setLocalMemories((prev) => prev.filter((_, i) => i !== index));
      }
    },
    [localMemories, onDeleteMemory, onNotify, queueSave, t]
  );

  const handleBlurMemory = useCallback(
    async (index: number) => {
      const memory = localMemories[index];
      if (!memory || !memory.content.trim()) return;
      if (isSavingRef.current) return;

      const newMemories: MemoryItem[] = localMemories
        .filter((m) => m.content.trim())
        .map((m) => ({
          id: m.dbId ?? "",
          content: m.content,
          source: "manual" as const,
          time_created: "",
          time_updated: "",
        }));

      const memoriesChanged =
        JSON.stringify(newMemories) !==
        JSON.stringify(initialMemoriesRef.current);

      if (!memoriesChanged) return;

      await queueSave(
        newMemories,
        t("memories.memorySaved"),
        t("memories.memorySaveFailed")
      );
    },
    [localMemories, queueSave, t]
  );

  const filteredMemories = localMemories
    .map((memory, originalIndex) => ({ memory, originalIndex }))
    .filter(({ memory }) => {
      if (!searchQuery.trim()) return true;
      return memory.content
        .toLowerCase()
        .includes(searchQuery.trim().toLowerCase());
    });

  const totalLineCount = localMemories.filter(
    (m) => m.content.trim() || m.isNew
  ).length;

  return {
    localMemories,
    searchQuery,
    setSearchQuery,
    filteredMemories,
    totalLineCount,
    canAddMemory,
    handleAddMemory,
    handleUpdateMemory,
    handleRemoveMemory,
    handleBlurMemory,
  };
}
