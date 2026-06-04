import { useMemo, useState } from "react";
import Modal from "@/refresh-components/Modal";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import { User } from "@/lib/types";
import { toast } from "@/hooks/useToast";
import { LoadingAnimation } from "@/components/Loading";
import { SvgUser } from "@opal/icons";
import { useTranslation } from "react-i18next";
import DeleteUserButton from "./buttons/DeleteUserButton";
import { authenticatedFetch } from "@/lib/fetcher";

export interface EditUserModalProps {
  user: User;
  onClose: () => void;
  onSuccess: () => void;
  canDelete?: boolean;
}

export default function EditUserModal({
  user,
  onClose,
  onSuccess,
  canDelete = true,
}: EditUserModalProps) {
  const { t } = useTranslation();
  const fullNameParts = (user.full_name || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  const initialFirstName = user.first_name || fullNameParts[0] || "";
  const initialLastName =
    fullNameParts.length > 1 ? fullNameParts.slice(1).join(" ") : "";

  const [firstName, setFirstName] = useState(initialFirstName);
  const [lastName, setLastName] = useState(initialLastName);
  const [password, setPassword] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  const isProfileChanged = useMemo(() => {
    return (
      (firstName || "") !== initialFirstName ||
      (lastName || "") !== initialLastName
    );
  }, [firstName, initialFirstName, initialLastName, lastName]);

  const isPasswordChanged = useMemo(
    () => password.trim().length > 0,
    [password]
  );

  const handleSave = async () => {
    if (!isProfileChanged && !isPasswordChanged) {
      toast.warning(t("admin.users.editUserModal.noChanges"));
      return;
    }

    if (isPasswordChanged && password.trim().length < 8) {
      toast.error(t("admin.users.editUserModal.passwordTooShort"));
      return;
    }

    setIsSaving(true);
    try {
      if (isProfileChanged) {
        const profileRes = await authenticatedFetch(`/api/user-service/users/${user.id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            first_name: firstName.trim() || null,
            last_name: lastName.trim() || null,
          }),
        });

        if (!profileRes.ok) {
          const err = await profileRes.json().catch(() => ({}));
          throw new Error(
            err.detail || t("admin.users.editUserModal.updateProfileFailed")
          );
        }
      }

      if (isPasswordChanged) {
        const passRes = await authenticatedFetch(
          `/api/user-service/users/${user.id}/password`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              password: password.trim(),
            }),
          }
        );

        if (!passRes.ok) {
          const err = await passRes.json().catch(() => ({}));
          throw new Error(
            err.detail || t("admin.users.editUserModal.setPasswordFailed")
          );
        }
      }

      toast.success(t("admin.users.editUserModal.updateSuccess"));
      onSuccess();
      onClose();
    } catch (error) {
      toast.error(
        error instanceof Error
          ? error.message
          : t("admin.users.editUserModal.updateFailed")
      );
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Modal open onOpenChange={onClose}>
      <Modal.Content width="sm">
        <Modal.Header
          icon={SvgUser}
          title={t("admin.users.editUserModal.title")}
          onClose={onClose}
          description={t("admin.users.editUserModal.description")}
        />
        <Modal.Body>
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <Text as="p" text03>
                {t("admin.users.editUserModal.emailLabel")}
              </Text>
              <input
                type="text"
                value={user.email}
                readOnly
                className="h-10 rounded border border-border-subtle bg-background-100 px-3 opacity-70"
              />
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div className="flex flex-col gap-1">
                <Text as="p" text03>
                  {t("admin.users.editUserModal.firstNameLabel")}
                </Text>
                <input
                  type="text"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  className="h-10 rounded border border-border-subtle bg-background px-3"
                  placeholder={t(
                    "admin.users.editUserModal.firstNamePlaceholder"
                  )}
                />
              </div>

              <div className="flex flex-col gap-1">
                <Text as="p" text03>
                  {t("admin.users.editUserModal.lastNameLabel")}
                </Text>
                <input
                  type="text"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  className="h-10 rounded border border-border-subtle bg-background px-3"
                  placeholder={t(
                    "admin.users.editUserModal.lastNamePlaceholder"
                  )}
                />
              </div>
            </div>

            <div className="flex flex-col gap-1">
              <Text as="p" text03>
                {t("admin.users.editUserModal.passwordLabel")}
              </Text>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="h-10 rounded border border-border-subtle bg-background px-3"
                placeholder={t("admin.users.editUserModal.passwordPlaceholder")}
              />
            </div>

            <div className="mt-2 flex items-center justify-between gap-2">
              <div>
                {canDelete && (
                  <DeleteUserButton
                    user={user}
                    mutate={onSuccess}
                    onSuccess={onClose}
                  >
                    {t("admin.users.deleteUserButton")}
                  </DeleteUserButton>
                )}
              </div>
              <div className="flex items-center gap-2">
                <Button onClick={onClose} tertiary>
                  {t("admin.users.editUserModal.cancelButton")}
                </Button>
                <Button onClick={handleSave} disabled={isSaving}>
                  {isSaving ? (
                    <LoadingAnimation
                      text={t("admin.users.editUserModal.savingButton")}
                    />
                  ) : (
                    t("admin.users.editUserModal.save")
                  )}
                </Button>
              </div>
            </div>
          </div>
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
}
