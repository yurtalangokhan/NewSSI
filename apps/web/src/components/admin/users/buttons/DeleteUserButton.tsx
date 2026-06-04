import { type User } from "@/lib/types";
import { toast } from "@/hooks/useToast";
import userMutationFetcher from "@/lib/admin/users/userMutationFetcher";
import useSWRMutation from "swr/mutation";
import Button from "@/refresh-components/buttons/Button";
import { useState } from "react";
import { ConfirmEntityModal } from "@/components/modals/ConfirmEntityModal";
import { useTranslation } from "react-i18next";

const DeleteUserButton = ({
  user,
  mutate,
  className,
  children,
  onSuccess,
}: {
  user: User;
  mutate: () => void;
  className?: string;
  children?: React.ReactNode;
  onSuccess?: () => void;
}) => {
  const { t } = useTranslation();
  const { trigger, isMutating } = useSWRMutation(
    `/api/user-service/users/${user.id}`,
    userMutationFetcher,
    {
      onSuccess: () => {
        mutate();
        onSuccess?.();
        toast.success(t("admin.users.deletedSuccess"));
      },
      onError: (errorMsg) =>
        toast.error(t("admin.users.deleteError", { error: errorMsg.message })),
    }
  );

  const [showDeleteModal, setShowDeleteModal] = useState(false);
  return (
    <>
      {showDeleteModal && (
        <ConfirmEntityModal
          entityType={t("admin.users.userEntity")}
          entityName={user.email}
          onClose={() => setShowDeleteModal(false)}
          onSubmit={() => trigger({ method: "DELETE" })}
          additionalDetails={t("admin.users.deleteAdditionalDetails")}
        />
      )}

      <Button
        className={className}
        onClick={() => setShowDeleteModal(true)}
        disabled={isMutating}
        danger
      >
        {children}
      </Button>
    </>
  );
};

export default DeleteUserButton;
