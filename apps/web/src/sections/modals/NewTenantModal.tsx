"use client";

import { useState } from "react";
import Modal, { BasicModalFooter } from "@/refresh-components/Modal";
import Button from "@/refresh-components/buttons/Button";
import { toast } from "@/hooks/useToast";
import { SvgArrowRight, SvgUsers, SvgX } from "@opal/icons";
import { logout } from "@/lib/user";
import { useUser } from "@/providers/UserProvider";
import { NewTenantInfo } from "@/lib/types";
import Text from "@/refresh-components/texts/Text";
import { ErrorTextLayout } from "@/layouts/input-layouts";
import { useTranslation } from "react-i18next";

// App domain should not be hardcoded
const APP_DOMAIN = process.env.NEXT_PUBLIC_APP_DOMAIN || "onyx.app";

export interface NewTenantModalProps {
  tenantInfo: NewTenantInfo;
  isInvite?: boolean;
  onClose?: () => void;
}

export default function NewTenantModal({
  tenantInfo,
  isInvite = false,
  onClose,
}: NewTenantModalProps) {
  const { user } = useUser();
  const { t } = useTranslation();
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleJoinTenant() {
    setIsLoading(true);
    setError(null);

    try {
      if (isInvite) {
        // Accept the invitation through the API
        const response = await fetch("/api/tenants/users/invite/accept", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ tenant_id: tenantInfo.tenant_id }),
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.message || "Failed to accept invitation");
        }

        toast.success(t("newTenantModal.toastAccepted"));
      } else {
        // For non-invite flow, just show success message
        toast.success(t("newTenantModal.toastProcessing"));
      }

      // Common logout and redirect for both flows
      await logout(`/auth/join?email=${encodeURIComponent(user?.email || "")}`);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : t("newTenantModal.toastJoinFailed");

      setError(message);
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }

  async function handleRejectInvite() {
    if (!isInvite) return;

    setIsLoading(true);
    setError(null);

    try {
      // Deny the invitation through the API
      const response = await fetch("/api/tenants/users/invite/deny", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ tenant_id: tenantInfo.tenant_id }),
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.message || "Failed to decline invitation");
      }

      toast.info(t("newTenantModal.toastDeclined"));
      onClose?.();
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : t("newTenantModal.toastDeclineFailed");

      setError(message);
      toast.error(message);
    } finally {
      setIsLoading(false);
    }
  }

  const title = isInvite
    ? t("newTenantModal.inviteTitle", { count: tenantInfo.number_of_users, domain: APP_DOMAIN })
    : t("newTenantModal.joinApprovedTitle", { count: tenantInfo.number_of_users, domain: APP_DOMAIN });

  const description = isInvite
    ? t("newTenantModal.inviteDescription", { domain: APP_DOMAIN })
    : t("newTenantModal.joinDescription", { email: user?.email });

  return (
    <Modal open>
      <Modal.Content width="sm" height="sm" preventAccidentalClose={false}>
        <Modal.Header icon={SvgUsers} title={title} onClose={onClose} />

        <Modal.Body>
          <Text>{description}</Text>
          {error && <ErrorTextLayout>{error}</ErrorTextLayout>}
        </Modal.Body>

        <Modal.Footer>
          <BasicModalFooter
            cancel={
              isInvite ? (
                <Button
                  onClick={handleRejectInvite}
                  secondary
                  disabled={isLoading}
                  leftIcon={SvgX}
                >
                  {t("newTenantModal.declineButton")}
                </Button>
              ) : undefined
            }
            submit={
              <Button
                onClick={handleJoinTenant}
                disabled={isLoading}
                rightIcon={SvgArrowRight}
              >
                {isLoading
                  ? isInvite
                    ? t("newTenantModal.acceptingButton")
                    : t("newTenantModal.joiningButton")
                  : isInvite
                    ? t("newTenantModal.acceptButton")
                    : t("newTenantModal.reauthenticateButton")}
              </Button>
            }
          />
        </Modal.Footer>
      </Modal.Content>
    </Modal>
  );
}
