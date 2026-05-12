import { useRef, useCallback, useEffect, useState } from "react";
import { MemoryItem } from "@/lib/types";

export interface LocalMemory {
  id: number;
  content: string;
  isNew: boolean;
}

export const MAX_MEMORY_LENGTH = 200;
export const MAX_MEMORY_COUNT = 10;

interface UseMemoryManagerArgs {
  memories: MemoryItem[];
  onSaveMemories: (memories: MemoryItem[]) => Promise<boolean>;
  onNotify: (message: string, type: "success" | "error") => void;
}

export function useMemoryManager({
  memories,
  onSaveMemories,
  onNotify,
}: UseMemoryManagerArgs) {
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
      id: mem.id ?? -(index + 1),
      content: mem.content,
      // Memories from props are already persisted, even if backend doesn't provide IDs.
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
          id: m.isNew || m.id < 0 ? null : m.id,
          content: m.content,
        }));

      const memoriesChanged =
        JSON.stringify(newMemories) !==
        JSON.stringify(initialMemoriesRef.current);

      if (memoriesChanged) {
        void queueSave(
          newMemories,
          "Memory saved",
          "Failed to save memory"
        );
      }
    }

    const newId = Date.now();
    setLocalMemories((prev) => [
      { id: newId, content: "", isNew: true },
      ...prev,
    ]);
    return newId;
  }, [localMemories, queueSave]);

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

      const newMemories: MemoryItem[] = localMemories
        .filter((_, i) => i !== index)
        .filter((m) => !m.isNew || m.content.trim())
        .map((m) => ({
          id: m.isNew || m.id < 0 ? null : m.id,
          content: m.content,
        }));

      const success = await queueSave(
        newMemories,
        "Memory deleted",
        "Failed to delete memory"
      );
      if (success) {
        setLocalMemories((prev) => prev.filter((_, i) => i !== index));
      }
    },
    [localMemories, queueSave]
  );

  const handleBlurMemory = useCallback(
    async (index: number) => {
      const memory = localMemories[index];
      if (!memory || !memory.content.trim()) return;
      if (isSavingRef.current) return;

      const newMemories: MemoryItem[] = localMemories
        .filter((m) => m.content.trim())
        .map((m) => ({
          id: m.isNew || m.id < 0 ? null : m.id,
          content: m.content,
        }));

      const memoriesChanged =
        JSON.stringify(newMemories) !==
        JSON.stringify(initialMemoriesRef.current);

      if (!memoriesChanged) return;

      await queueSave(newMemories, "Memory saved", "Failed to save memory");
    },
    [localMemories, queueSave]
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
