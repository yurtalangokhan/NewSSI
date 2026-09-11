"use client";
import Skeleton from "@/refresh-components/skeletons/Skeleton";

import { createContext, useContext } from "react";
import { useRouter } from "next/navigation";
import { useOnboardingModal } from "@/app/craft/onboarding/hooks/useOnboardingModal";
import BuildOnboardingModal from "@/app/craft/onboarding/components/BuildOnboardingModal";
import NoLlmProvidersModal from "@/app/craft/onboarding/components/NoLlmProvidersModal";
import { OnboardingModalController } from "@/app/craft/onboarding/types";
import { useUser } from "@/providers/UserProvider";

// Context for accessing onboarding modal controls
const OnboardingContext = createContext<OnboardingModalController | null>(null);

export function useOnboarding(): OnboardingModalController {
  const ctx = useContext(OnboardingContext);
  if (!ctx) {
    throw new Error(
      "useOnboarding must be used within BuildOnboardingProvider"
    );
  }
  return ctx;
}

interface BuildOnboardingProviderProps {
  children: React.ReactNode;
}

export function BuildOnboardingProvider({
  children,
}: BuildOnboardingProviderProps) {
  const router = useRouter();
  const { user } = useUser();
  const controller = useOnboardingModal();

  // Show loading state while user data is loading
  if (!user) {
    return (
      <div className="flex w-full h-screen bg-background-neutral-01">
        <div className="w-64 border-r border-border-02 p-4 flex flex-col gap-3">
          <Skeleton className="h-8 w-36 rounded-08" />
          <Skeleton className="h-6 w-full rounded-08" />
          <Skeleton className="h-6 w-full rounded-08" />
        </div>
        <div className="flex-1 p-6 flex flex-col gap-4">
          <Skeleton className="h-10 w-64 rounded-08" />
          <Skeleton className="h-64 w-full rounded-08" />
        </div>
      </div>
    );
  }

  // Non-admin users with no LLM providers cannot use Craft
  // Don't show modal while loading to prevent flash
  const showNoProvidersModal =
    !controller.isLoading && !controller.isAdmin && !controller.hasAnyProvider;

  return (
    <OnboardingContext.Provider value={controller}>
      {/* Block non-admin users when no LLM providers are configured */}
      <NoLlmProvidersModal
        open={showNoProvidersModal}
        onClose={() => router.push("/app")}
      />

      {/* Unified onboarding modal - only show if not blocked by no providers */}
      {!showNoProvidersModal && (
        <BuildOnboardingModal
          mode={controller.mode}
          llmProviders={controller.llmProviders}
          initialValues={controller.initialValues}
          isAdmin={controller.isAdmin}
          hasUserInfo={controller.hasUserInfo}
          allProvidersConfigured={controller.allProvidersConfigured}
          hasAnyProvider={controller.hasAnyProvider}
          onComplete={controller.completeUserInfo}
          onLlmComplete={controller.completeLlmSetup}
          onClose={controller.close}
        />
      )}

      {/* Build content - always rendered, modals overlay it */}
      {children}
    </OnboardingContext.Provider>
  );
}
