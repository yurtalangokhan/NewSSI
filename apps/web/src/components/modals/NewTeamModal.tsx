"use client";

import { authenticatedFetch } from "@/lib/fetcher";

import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useRouter, useSearchParams } from "next/navigation";
import type { Route } from "next";
import { Dialog } from "@headlessui/react";
import Button from "@/refresh-components/buttons/Button";
import { toast } from "@/hooks/useToast";
import { useUser } from "@/providers/UserProvider";
import { useModalContext } from "../context/ModalContext";
import SimpleLoader from "@/refresh-components/loaders/SimpleLoader";
import {
  SvgArrowRight,
  SvgArrowUp,
  SvgCheckCircle,
  SvgOrganization,
  SvgPlus,
} from "@opal/icons";
import Text from "@/refresh-components/texts/Text";
import FormSkeleton from "@/refresh-components/skeletons/FormSkeleton";
export interface TenantByDomainResponse {
  tenant_id: string;
  number_of_users: number;
  creator_email: string;
}

export default function NewTeamModal() {
  const { t } = useTranslation("common", { keyPrefix: "modals" });
  const { showNewTeamModal, setShowNewTeamModal } = useModalContext();
  const [existingTenant, setExistingTenant] =
    useState<TenantByDomainResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [hasRequestedInvite, setHasRequestedInvite] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { user } = useUser();
  const appDomain = user?.email.split("@")[1];
  const router = useRouter();
  const searchParams = useSearchParams();

  useEffect(() => {
    const hasNewTeamParam = searchParams?.has("new_team");
    if (hasNewTeamParam) {
      setShowNewTeamModal(true);
      fetchTenantInfo();

      // Remove the new_team parameter from the URL without page reload
      const newParams = new URLSearchParams(searchParams?.toString() || "");
      newParams.delete("new_team");
      const newUrl =
        window.location.pathname +
        (newParams.toString() ? `?${newParams.toString()}` : "");
      window.history.replaceState({}, "", newUrl);
    }
  }, [searchParams, setShowNewTeamModal]);

  const fetchTenantInfo = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch("/api/tenants/existing-team-by-domain");
      if (!response.ok) {
        throw new Error(`Failed to fetch team info: ${response.status}`);
      }
      const responseJson = await response.json();
      if (!responseJson) {
        setShowNewTeamModal(false);
        setExistingTenant(null);
        return;
      }

      const data = responseJson as TenantByDomainResponse;
      setExistingTenant(data);
    } catch (error) {
      console.error("Failed to fetch tenant info:", error);
      setError(t("newTeam.couldNotRetrieveTeam"));
    } finally {
      setIsLoading(false);
    }
  };

  const handleRequestInvite = async () => {
    if (!existingTenant) return;

    setIsSubmitting(true);
    setError(null);

    try {
      const response = await authenticatedFetch(
        "/api/tenants/users/invite/request",
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ tenant_id: existingTenant.tenant_id }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || t("newTeam.toastInviteFailed"));
      }

      setHasRequestedInvite(true);
      toast.success(t("newTeam.toastInviteSent"));
    } catch (error) {
      const message =
        error instanceof Error ? error.message : t("newTeam.toastInviteFailed");
      setError(message);
      toast.error(message);
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleContinueToNewOrg = () => {
    const newUrl = window.location.pathname;
    router.replace(newUrl as Route);
    setShowNewTeamModal(false);
  };

  // Update the close handler to use the context
  const handleClose = () => {
    setShowNewTeamModal(false);
  };

  // Only render if showNewTeamModal is true
  if (!showNewTeamModal || isLoading) return null;

  return (
    <Dialog
      open={showNewTeamModal}
      onClose={handleClose}
      className="relative z-[1000]"
    >
      {/* Modal backdrop */}
      <div className="fixed inset-0 bg-mask-03" aria-hidden="true" />

      <div className="fixed inset-0 flex items-center justify-center p-4">
        <Dialog.Panel className="mx-auto w-full max-w-md rounded-lg bg-background-neutral-00 p-6 shadow-xl border">
          <Dialog.Title className="text-xl font-semibold mb-4 flex items-center">
            {hasRequestedInvite ? (
              <>
                <SvgCheckCircle className="mr-2 h-5 w-5 stroke-text-05" />
                {t("newTeam.joinRequestSentTitle")}
              </>
            ) : (
              <>
                <SvgOrganization className="mr-2 h-5 w-5 stroke-text-04" />
                {t("newTeam.existingTeamFoundTitle", { domain: appDomain })}
              </>
            )}
          </Dialog.Title>

          {isLoading ? (
            <div className="py-4">
              <FormSkeleton fieldCount={2} />
            </div>
          ) : error ? (
            <div className="space-y-4">
              <Text as="p" className="text-status-text-error-05">
                {error}
              </Text>
              <div className="flex w-full pt-2">
                <Button
                  onClick={handleContinueToNewOrg}
                  className="w-full"
                  rightIcon={SvgArrowRight}
                >
                  {t("newTeam.continueWithNewTeam")}
                </Button>
              </div>
            </div>
          ) : hasRequestedInvite ? (
            <div className="space-y-4">
              <Text as="p" className="text-text-04">
                {t("newTeam.joinRequestSentBody", { domain: appDomain })}
              </Text>
              <div className="flex w-full pt-2">
                <Button
                  onClick={handleContinueToNewOrg}
                  className="w-full"
                  rightIcon={SvgArrowRight}
                >
                  {t("newTeam.tryWhileWaiting")}
                </Button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <Text as="p" className="text-text-03 text-sm mb-2">
                {t("newTeam.joinRequestInfo", { domain: appDomain })}
              </Text>
              <div className="flex flex-col items-center justify-center gap-4 mt-4">
                <Button
                  onClick={handleRequestInvite}
                  className="w-full"
                  disabled={isSubmitting}
                  leftIcon={isSubmitting ? SimpleLoader : SvgArrowUp}
                >
                  {isSubmitting
                    ? t("newTeam.sendingRequest")
                    : t("newTeam.requestToJoin")}
                </Button>
              </div>
              <Button
                onClick={handleContinueToNewOrg}
                className="w-full"
                leftIcon={SvgPlus}
                secondary
              >
                {t("newTeam.continueWithNewTeam")}
              </Button>
            </div>
          )}
        </Dialog.Panel>
      </div>
    </Dialog>
  );
}
