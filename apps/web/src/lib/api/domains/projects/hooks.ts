"use client";
import { projectsEndpoints } from "@/lib/api/domains/projects/endpoints";

import useSWR from "swr";
import type { Project } from "./types";
import { fetchProjectCatalog } from "./api";

export function useProjects() {
  const { data, error, mutate } = useSWR<Project[]>(
    projectsEndpoints.listProjects.browserPath,
    () => fetchProjectCatalog() as Promise<Project[]>,
    {
      revalidateOnFocus: false,
      dedupingInterval: 30000,
    }
  );

  return {
    projects: data ?? [],
    isLoading: !error && !data,
    error,
    refreshProjects: mutate,
  };
}
