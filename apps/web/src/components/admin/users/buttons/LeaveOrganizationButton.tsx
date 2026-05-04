import { type User } from "@/lib/types";
import { useTranslation } from "react-i18next";
import { toast } from "@/hooks/useToast";
import userMutationFetcher from "@/lib/admin/users/userMutationFetcher";
import useSWRMutation from "swr/mutation";
import Button from "@/refresh-components/buttons/Button";
import { useState } from "react";
import { ConfirmEntityModal } from "@/components/modals/ConfirmEntityModal";
import { useRouter } from "next/navigation";

export const LeaveOrganizationButton = ({
  user,
  mutate,
  className,
  children,
}: {
  user: User;
  mutate: () => void;
  className?: string;
  children?: React.ReactNode;
}) => {
  const { t } = useTranslation();
  const router = useRouter();
  const { trigger, isMutating } = useSWRMutation(
    "/api/tenants/leave-team",
    userMutationFetcher,
    {
      onSuccess: () => {
        mutate();
        toast.success(t("admin.users.leaveTeamSuccess"));
      },
      onError: (errorMsg) =>
        toast.error(t("admin.users.leaveTeamError", { error: errorMsg })),
    }
  );

  const [showLeaveModal, setShowLeaveModal] = useState(false);

  const handleLeaveOrganization = async () => {
    await trigger({ user_email: user.email, method: "POST" });
    router.push("/");
  };

  return (
    <>
      {showLeaveModal && (
        <ConfirmEntityModal
          actionButtonText={t("admin.users.leaveButton")}
          entityType={t("admin.users.teamEntity")}
          entityName={t("admin.users.yourTeamEntity")}
          onClose={() => setShowLeaveModal(false)}
          onSubmit={handleLeaveOrganization}
          additionalDetails={t("admin.users.leaveTeamDetails")}
        />
      )}

      <Button
        className={className}
        onClick={() => setShowLeaveModal(true)}
        disabled={isMutating}
        internal
      >
        {children}
      </Button>
    </>
  );
};
