import { type User } from "@/lib/types";
import { toast } from "@/hooks/useToast";
import Button from "@/refresh-components/buttons/Button";
import useSWRMutation from "swr/mutation";
import { setDirectoryUserActive } from "@/lib/api/domains/access/api";
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
    ["set-directory-user-active", user.id, deactivate],
    () => setDirectoryUserActive(user.id, !deactivate),
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
      onClick={() => trigger()}
      disabled={isMutating}
      leftIcon={SvgXCircle}
      tertiary
    >
      {children}
    </Button>
  );
};

export default DeactivateUserButton;
