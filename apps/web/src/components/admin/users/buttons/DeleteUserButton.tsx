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
}: {
  user: User;
  mutate: () => void;
  className?: string;
  children?: React.ReactNode;
}) => {
  const { t } = useTranslation();
  const { trigger, isMutating } = useSWRMutation(
    `/api/user-service/users/${user.id}`,
    userMutationFetcher,
    {
      onSuccess: () => {
        mutate();
        toast.success("User deleted successfully!");
      },
      onError: (errorMsg) =>
        toast.error(`Unable to delete user - ${errorMsg.message}`),
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
          additionalDetails="All data associated with this user will be deleted (including personas, tools and chat sessions)."
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
