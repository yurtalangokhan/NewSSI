import {
  type InvitedUserSnapshot,
  type AcceptedUserSnapshot,
} from "@/lib/types";

import { toast } from "@/hooks/useToast";
import useSWRMutation from "swr/mutation";
import Button from "@/refresh-components/buttons/Button";
import GenericConfirmModal from "@/components/modals/GenericConfirmModal";
import { useState } from "react";
import { useTranslation } from "react-i18next";

export const InviteUserButton = ({
  user,
  invited,
  mutate,
}: {
  user: AcceptedUserSnapshot | InvitedUserSnapshot;
  invited: boolean;
  mutate: (() => void) | (() => void)[];
}) => {
  const { t } = useTranslation();
  const { trigger: inviteTrigger, isMutating: isInviting } = useSWRMutation(
    "/api/user-service/users/invite",
    async (url, { arg }: { arg: { emails: string[] } }) => {
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(arg),
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    },
    {
      onSuccess: () => {
        setShowInviteModal(false);
        if (typeof mutate === "function") {
          mutate();
        } else {
          mutate.forEach((fn) => fn());
        }
        toast.success(t("admin.users.singleInviteSuccess"));
      },
      onError: (errorMsg) => {
        setShowInviteModal(false);
        toast.error(t("admin.users.singleInviteError", { error: errorMsg }));
      },
    }
  );

  const { trigger: uninviteTrigger, isMutating: isUninviting } = useSWRMutation(
    invited && user.id ? `/api/user-service/users/${user.id}` : null,
    async (url: string) => {
      const response = await fetch(url, {
        method: "DELETE",
      });
      if (!response.ok) {
        throw new Error(await response.text());
      }
      return response.json();
    },
    {
      onSuccess: () => {
        setShowInviteModal(false);
        if (typeof mutate === "function") {
          mutate();
        } else {
          mutate.forEach((fn) => fn());
        }
        toast.success(t("admin.users.singleUninviteSuccess"));
      },
      onError: (errorMsg) => {
        setShowInviteModal(false);
        toast.error(t("admin.users.singleUninviteError", { error: errorMsg }));
      },
    }
  );

  const [showInviteModal, setShowInviteModal] = useState(false);

  const handleConfirm = () => {
    const normalizedEmail = user.email.toLowerCase();
    if (invited) {
      if (!user.id) {
        toast.error(
          t("admin.users.singleUninviteError", { error: "Missing user id" })
        );
        return;
      }
      uninviteTrigger();
    } else {
      inviteTrigger({ emails: [normalizedEmail] });
    }
  };

  const isMutating = isInviting || isUninviting;

  return (
    <>
      {showInviteModal && (
        <GenericConfirmModal
          title={
            invited
              ? t("admin.users.uninviteUserTitle")
              : t("admin.users.inviteUserTitle")
          }
          message={
            invited
              ? t("admin.users.uninviteConfirmation", { email: user.email })
              : t("admin.users.inviteConfirmation", { email: user.email })
          }
          onClose={() => setShowInviteModal(false)}
          onConfirm={handleConfirm}
        />
      )}

      <Button onClick={() => setShowInviteModal(true)} disabled={isMutating}>
        {invited
          ? t("admin.users.uninviteButton")
          : t("admin.users.inviteButton")}
      </Button>
    </>
  );
};
