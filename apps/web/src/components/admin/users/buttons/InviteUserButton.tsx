import {
  errorMessageFromUnknown,
  parseApiErrorResponse,
} from "@/lib/api/errors";
import { accessEndpoints } from "@/lib/api/domains/access/endpoints";

import { inviteDirectoryUsersBulk as inviteDirectoryUser } from "@/lib/api/domains/access/api";
import { uninviteDirectoryUser } from "@/lib/api/domains/access/api";

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
    accessEndpoints.inviteDirectoryUsersBulk.browserPath,
    async (url, { arg }: { arg: { emails: string[] } }) => {
      const response = await inviteDirectoryUser(arg);
      if (!response.ok) {
        throw new Error((await parseApiErrorResponse(response)).userMessage);
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
        toast.error(
          t("admin.users.singleInviteError", {
            error: errorMessageFromUnknown(errorMsg),
          })
        );
      },
    }
  );

  const { trigger: uninviteTrigger, isMutating: isUninviting } = useSWRMutation(
    invited && user.id
      ? accessEndpoints.directoryUser(user.id).browserPath
      : null,
    async (url: string) => {
      const response = await uninviteDirectoryUser(user.id);
      if (!response.ok) {
        throw new Error((await parseApiErrorResponse(response)).userMessage);
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
        toast.error(
          t("admin.users.singleUninviteError", {
            error: errorMessageFromUnknown(errorMsg),
          })
        );
      },
    }
  );

  const [showInviteModal, setShowInviteModal] = useState(false);

  const handleConfirm = () => {
    const normalizedEmail = user.email.toLowerCase();
    if (invited) {
      if (!user.id) {
        toast.error(
          t("admin.users.singleUninviteError", {
            error: errorMessageFromUnknown(undefined),
          })
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
