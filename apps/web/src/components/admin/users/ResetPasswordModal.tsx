import { useState } from "react";
import { useTranslation } from "react-i18next";
import Modal from "@/refresh-components/Modal";
import Button from "@/refresh-components/buttons/Button";
import { User } from "@/lib/types";
import { toast } from "@/hooks/useToast";
import Text from "@/refresh-components/texts/Text";
import { LoadingAnimation } from "@/components/Loading";
import CopyIconButton from "@/refresh-components/buttons/CopyIconButton";
import { SvgKey, SvgRefreshCw } from "@opal/icons";

export interface ResetPasswordModalProps {
  user: User;
  onClose: () => void;
}

export default function ResetPasswordModal({
  user,
  onClose,
}: ResetPasswordModalProps) {
  const { t } = useTranslation();
  const [newPassword, setNewPassword] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleResetPassword = async () => {
    setIsLoading(true);
    try {
      const response = await fetch(
        `/api/user-service/users/${user.id}/reset-password`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
        }
      );

      if (response.ok) {
        const data = await response.json();
        setNewPassword(data.password);
        toast.success(t("admin.users.passwordResetSuccess"));
      } else {
        const errorData = await response.json();
        toast.error(errorData.detail || t("admin.users.passwordResetFailed"));
      }
    } catch (error) {
      toast.error(t("admin.users.passwordResetError"));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Modal open onOpenChange={onClose}>
      <Modal.Content width="sm" height="sm">
        <Modal.Header
          icon={SvgKey}
          title={t("admin.users.resetPasswordTitle")}
          onClose={onClose}
          description={
            newPassword
              ? undefined
              : t("admin.users.resetPasswordConfirmation", {
                  email: user.email,
                })
          }
        />
        <Modal.Body>
          {newPassword ? (
            <div>
              <Text as="p">{t("admin.users.newPasswordLabel")}:</Text>
              <div className="flex items-center bg-background-tint-03 p-2 rounded gap-2">
                <Text as="p" data-testid="new-password" className="flex-grow">
                  {newPassword}
                </Text>
                <CopyIconButton getCopyText={() => newPassword} />
              </div>
              <Text as="p" text02>
                {t("admin.users.passwordCommunicateNote")}
              </Text>
            </div>
          ) : (
            <Button
              onClick={handleResetPassword}
              disabled={isLoading}
              leftIcon={SvgRefreshCw}
            >
              {isLoading ? (
                <Text as="p">
                  <LoadingAnimation text={t("admin.users.resettingLoading")} />
                </Text>
              ) : (
                t("admin.users.resetPasswordButton")
              )}
            </Button>
          )}
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
}
