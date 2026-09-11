"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { buildImgUrl } from "@/app/app/components/files/images/utils";
import { cn } from "@/lib/utils";
import Button from "@/refresh-components/buttons/Button";
import Popover, { PopoverMenu } from "@/refresh-components/Popover";
import LineItem from "@/refresh-components/buttons/LineItem";
import SquareButton from "@/refresh-components/buttons/SquareButton";
import InputAvatar from "@/refresh-components/inputs/InputAvatar";
import CustomAgentAvatar, {
  agentAvatarIconMap,
} from "@/refresh-components/avatars/CustomAgentAvatar";
import { SvgImage } from "@opal/icons";

export type AgentIconValue = {
  uploadedImageId: string | null;
  iconName: string | null;
};

export interface AgentIconPickerProps {
  /** Shown as a fallback letter avatar while nothing else is picked. */
  name?: string;
  value: AgentIconValue;
  onChange: (next: AgentIconValue) => void;
  variant?: "agent" | "flow";
  size?: "default" | "large";
}

/**
 * The avatar picker, lifted out of AgentEditorPage so the flow creation
 * modal can use the same one. Formik-free by design: it reports a value,
 * the caller decides where that value lives.
 */
export default function AgentIconPicker({
  name,
  value,
  onChange,
  variant = "agent",
  size = "default",
}: AgentIconPickerProps) {
  const { t } = useTranslation();
  const [uploadedImagePreview, setUploadedImagePreview] = useState<
    string | null
  >(null);
  const [popoverOpen, setPopoverOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    setMounted(true);
  }, []);

  async function handleImageUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploadedImagePreview(null);

    const reader = new FileReader();
    reader.onloadend = () => {
      setUploadedImagePreview(reader.result as string);
    };
    reader.readAsDataURL(file);

    try {
      const formData = new FormData();
      formData.append("file", file);
      const response = await fetch("/api/admin/persona/upload-image", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        console.error("Failed to upload image");
        setUploadedImagePreview(null);
        return;
      }

      const { file_id } = await response.json();
      onChange({ uploadedImageId: file_id, iconName: null });
      setPopoverOpen(false);
    } catch (error) {
      console.error("Upload error:", error);
      setUploadedImagePreview(null);
    }
  }

  const imageSrc = uploadedImagePreview
    ? uploadedImagePreview
    : value.uploadedImageId
      ? buildImgUrl(value.uploadedImageId)
      : undefined;

  function handleIconClick(iconName: string | null) {
    onChange({ uploadedImageId: null, iconName });
    setUploadedImagePreview(null);
    setPopoverOpen(false);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  const isLarge = size === "large";
  // The medallion frame is now the whole avatar surface, so it fills the
  // InputAvatar circle the same way an uploaded image does.
  const avatarSizePx = isLarge ? 10 * 16 : 7.5 * 16;

  const fileInputNode = (
    <input
      ref={fileInputRef}
      type="file"
      accept="image/*"
      onChange={handleImageUpload}
      className="hidden"
    />
  );

  return (
    <>
      {mounted && typeof document !== "undefined"
        ? createPortal(fileInputNode, document.body)
        : null}

      <Popover open={popoverOpen} onOpenChange={setPopoverOpen}>
        <Popover.Trigger asChild>
          <InputAvatar
            className={cn(
              "group/InputAvatar relative flex flex-col items-center justify-center cursor-pointer",
              isLarge ? "h-[10rem] w-[10rem]" : "h-[7.5rem] w-[7.5rem]"
            )}
          >
            <CustomAgentAvatar
              size={avatarSizePx}
              src={imageSrc}
              iconName={value.iconName ?? undefined}
              name={name}
              variant={variant}
            />
            <Button
              className={cn(
                "absolute left-1/2 -translate-x-1/2 pointer-events-none invisible group-hover/InputAvatar:visible",
                isLarge
                  ? "bottom-2.5 h-[1.75rem] px-3"
                  : "bottom-0 mb-2 h-[1.75rem]"
              )}
              secondary
            >
              {t("agentEditor.editButton")}
            </Button>
          </InputAvatar>
        </Popover.Trigger>
        <Popover.Content align="end">
          <PopoverMenu>
            {[
              <LineItem
                key="upload-image"
                icon={SvgImage}
                onClick={() => fileInputRef.current?.click()}
                emphasized
              >
                {t("agentEditor.uploadImage")}
              </LineItem>,
              null,
              <div key="avatar-icons" className="grid grid-cols-4 gap-1">
                <SquareButton
                  key="default-icon"
                  data-testid="agent-icon-option"
                  icon={() => (
                    <CustomAgentAvatar
                      name={name}
                      size={30}
                      variant={variant}
                    />
                  )}
                  onClick={() => handleIconClick(null)}
                  transient={!imageSrc && value.iconName === null}
                />
                {Object.keys(agentAvatarIconMap).map((iconName) => (
                  <SquareButton
                    key={iconName}
                    data-testid="agent-icon-option"
                    onClick={() => handleIconClick(iconName)}
                    icon={() => (
                      <CustomAgentAvatar
                        iconName={iconName}
                        size={30}
                        variant={variant}
                      />
                    )}
                    transient={value.iconName === iconName}
                  />
                ))}
              </div>,
            ]}
          </PopoverMenu>
        </Popover.Content>
      </Popover>
    </>
  );
}
