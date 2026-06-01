"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MemoryItem } from "@/lib/types";

interface MemoryListResponse {
  items: MemoryItem[];
  total: number;
}

interface UseUserMemoriesOptions {
  onError?: (error: unknown) => void;
}

export default function useUserMemories(options?: UseUserMemoriesOptions) {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isMutating, setIsMutating] = useState(false);

  // Keep a stable ref so fetchMemories doesn't need onError in its dep array
  const onErrorRef = useRef(options?.onError);
  useEffect(() => {
    onErrorRef.current = options?.onError;
  });

  const fetchMemories = useCallback(async (offset = 0, limit = 50) => {
    setIsLoading(true);
    try {
      const res = await fetch(
        `/api/user/memories?offset=${offset}&limit=${limit}`
      );
      if (!res.ok) throw new Error("Failed to fetch memories");
      const data: MemoryListResponse = await res.json();
      setMemories(data.items);
      setTotal(data.total);
    } catch (error) {
      onErrorRef.current?.(error);
    } finally {
      setIsLoading(false);
    }
  }, []); // stable — no onError dep

  useEffect(() => {
    fetchMemories();
  }, [fetchMemories]);

  const createMemory = useCallback(
    async (content: string): Promise<MemoryItem | null> => {
      setIsMutating(true);
      try {
        const res = await fetch("/api/user/memories", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content }),
        });
        if (!res.ok) throw new Error("Failed to create memory");
        const item: MemoryItem = await res.json();
        setMemories((prev) => [...prev, item]);
        setTotal((prev) => prev + 1);
        return item;
      } catch (error) {
        onErrorRef.current?.(error);
        return null;
      } finally {
        setIsMutating(false);
      }
    },
    []
  );

  const updateMemory = useCallback(
    async (id: string, content: string): Promise<MemoryItem | null> => {
      setIsMutating(true);
      try {
        const res = await fetch(`/api/user/memories/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content }),
        });
        if (!res.ok) throw new Error("Failed to update memory");
        const item: MemoryItem = await res.json();
        setMemories((prev) => prev.map((m) => (m.id === id ? item : m)));
        return item;
      } catch (error) {
        onErrorRef.current?.(error);
        return null;
      } finally {
        setIsMutating(false);
      }
    },
    []
  );

  const deleteMemory = useCallback(
    async (id: string): Promise<boolean> => {
      setIsMutating(true);
      try {
        const res = await fetch(`/api/user/memories/${id}`, {
          method: "DELETE",
        });
        if (!res.ok) throw new Error("Failed to delete memory");
        setMemories((prev) => prev.filter((m) => m.id !== id));
        setTotal((prev) => prev - 1);
        return true;
      } catch (error) {
        onErrorRef.current?.(error);
        return false;
      } finally {
        setIsMutating(false);
      }
    },
    []
  );

  const deleteAllMemories = useCallback(async (): Promise<number> => {
    setIsMutating(true);
    try {
      const res = await fetch("/api/user/memories", { method: "DELETE" });
      if (!res.ok) throw new Error("Failed to delete all memories");
      const data: { deleted: number } = await res.json();
      setMemories([]);
      setTotal(0);
      return data.deleted;
    } catch (error) {
      onErrorRef.current?.(error);
      return 0;
    } finally {
      setIsMutating(false);
    }
  }, []);

  return {
    memories,
    total,
    isLoading,
    isMutating,
    fetchMemories,
    createMemory,
    updateMemory,
    deleteMemory,
    deleteAllMemories,
  };
}
