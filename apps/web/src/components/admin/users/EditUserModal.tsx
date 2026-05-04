import { useMemo, useState } from "react";
import Modal from "@/refresh-components/Modal";
import Button from "@/refresh-components/buttons/Button";
import Text from "@/refresh-components/texts/Text";
import { User } from "@/lib/types";
import { toast } from "@/hooks/useToast";
import { LoadingAnimation } from "@/components/Loading";
import { SvgUser } from "@opal/icons";

export interface EditUserModalProps {
  user: User;
  onClose: () => void;
  onSuccess: () => void;
}

export default function EditUserModal({
  user,
  onClose,
  onSuccess,
}: EditUserModalProps) {
  const fullNameParts = (user.full_name || "").trim().split(/\s+/).filter(Boolean);
  const initialFirstName = user.first_name || fullNameParts[0] || "";
  const initialLastName = fullNameParts.length > 1 ? fullNameParts.slice(1).join(" ") : "";

  const [firstName, setFirstName] = useState(initialFirstName);
  const [lastName, setLastName] = useState(initialLastName);
  const [password, setPassword] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  const isProfileChanged = useMemo(() => {
    return (firstName || "") !== initialFirstName || (lastName || "") !== initialLastName;
  }, [firstName, initialFirstName, initialLastName, lastName]);

  const isPasswordChanged = useMemo(() => password.trim().length > 0, [password]);

  const handleSave = async () => {
    if (!isProfileChanged && !isPasswordChanged) {
      toast.warning("No changes to save");
      return;
    }

    if (isPasswordChanged && password.trim().length < 8) {
      toast.error("Password must be at least 8 characters");
      return;
    }

    setIsSaving(true);
    try {
      if (isProfileChanged) {
        const profileRes = await fetch("/api/manage/admin/update-user-profile", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_email: user.email,
            first_name: firstName.trim() || null,
            last_name: lastName.trim() || null,
          }),
        });

        if (!profileRes.ok) {
          const err = await profileRes.json().catch(() => ({}));
          throw new Error(err.detail || "Failed to update user profile");
        }
      }

      if (isPasswordChanged) {
        const passRes = await fetch("/api/manage/admin/set-user-password", {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            user_email: user.email,
            password: password.trim(),
            temporary: false,
          }),
        });

        if (!passRes.ok) {
          const err = await passRes.json().catch(() => ({}));
          throw new Error(err.detail || "Failed to set user password");
        }
      }

      toast.success("User updated successfully");
      onSuccess();
      onClose();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Failed to update user");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Modal open onOpenChange={onClose}>
      <Modal.Content width="sm">
        <Modal.Header
          icon={SvgUser}
          title="Edit User"
          onClose={onClose}
          description="Update name and set a new password. Username/email is immutable."
        />
        <Modal.Body>
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <Text as="p" text03>
                Email (immutable)
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
                  First Name
                </Text>
                <input
                  type="text"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                  className="h-10 rounded border border-border-subtle bg-background px-3"
                  placeholder="First name"
                />
              </div>

              <div className="flex flex-col gap-1">
                <Text as="p" text03>
                  Last Name
                </Text>
                <input
                  type="text"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                  className="h-10 rounded border border-border-subtle bg-background px-3"
                  placeholder="Last name"
                />
              </div>
            </div>

            <div className="flex flex-col gap-1">
              <Text as="p" text03>
                New Password
              </Text>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="h-10 rounded border border-border-subtle bg-background px-3"
                placeholder="Leave blank to keep current password"
              />
            </div>

            <div className="mt-2 flex items-center gap-2">
              <Button onClick={onClose} tertiary>
                Cancel
              </Button>
              <Button onClick={handleSave} disabled={isSaving}>
                {isSaving ? <LoadingAnimation text="Saving" /> : "Save Changes"}
              </Button>
            </div>
          </div>
        </Modal.Body>
      </Modal.Content>
    </Modal>
  );
}
