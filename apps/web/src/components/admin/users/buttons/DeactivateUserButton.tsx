import { type User } from "@/lib/types";
import { toast } from "@/hooks/useToast";
import Button from "@/refresh-components/buttons/Button";
import useSWRMutation from "swr/mutation";
import userMutationFetcher from "@/lib/admin/users/userMutationFetcher";
import { SvgXCircle } from "@opal/icons";
import { useTranslation } from "react-i18next";
const DeactivateUserButton = ({
  user,
  deactivate,
  mutate,
  onSuccess,
  className,
  children,
}: {
  user: User;
  deactivate: boolean;
  mutate: () => void;
  onSuccess?: (user: User) => void;
  className?: string;
  children?: string;
}) => {
  const { t } = useTranslation();
  const { trigger, isMutating } = useSWRMutation(
    `/api/user-service/users/${user.id}/active`,
    userMutationFetcher,
    {
      onSuccess: (updatedUser: User) => {
        onSuccess?.(updatedUser);
        if (!onSuccess) {
          mutate();
        }
        toast.success(
          deactivate
            ? t("admin.users.deactivatedSuccess")
            : t("admin.users.activatedSuccess")
        );
      },
      onError: (errorMsg) => toast.error(errorMsg.message),
    }
  );
  return (
    <Button
      className={className}
      onClick={() => trigger({ is_active: !deactivate })}
      disabled={isMutating}
      leftIcon={SvgXCircle}
      tertiary
    >
      {children}
    </Button>
  );
};

export default DeactivateUserButton;
