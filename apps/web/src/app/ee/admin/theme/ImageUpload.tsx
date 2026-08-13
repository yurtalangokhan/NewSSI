import { SubLabel } from "@/components/Field";
import { toast } from "@/hooks/useToast";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Dropzone from "react-dropzone";

export function ImageUpload({
  selectedFile,
  setSelectedFile,
}: {
  selectedFile: File | null;
  setSelectedFile: (file: File) => void;
}) {
  const { t } = useTranslation("common", {
    keyPrefix: "admin.imageUpload",
  });
  const [tmpImageUrl, setTmpImageUrl] = useState<string>("");

  useEffect(() => {
    if (selectedFile) {
      setTmpImageUrl(URL.createObjectURL(selectedFile));
    } else {
      setTmpImageUrl("");
    }
  }, [selectedFile]);

  const [dragActive, setDragActive] = useState(false);

  return (
    <Dropzone
      onDrop={(acceptedFiles) => {
        if (acceptedFiles.length !== 1) {
          toast.error(t("onlyOneFile"));
          return;
        }

        const acceptedFile = acceptedFiles[0];
        if (acceptedFile === undefined) {
          toast.error(t("acceptedFileUndefined"));
          return;
        }

        setTmpImageUrl(URL.createObjectURL(acceptedFile));
        setSelectedFile(acceptedFile);
        setDragActive(false);
      }}
      onDragLeave={() => setDragActive(false)}
      onDragEnter={() => setDragActive(true)}
    >
      {({ getRootProps, getInputProps }) => (
        <section>
          <div
            {...getRootProps()}
            className={
              "flex flex-col items-center w-full px-4 py-12 rounded " +
              "shadow-lg tracking-wide border border-border cursor-pointer" +
              (dragActive ? " border-accent" : "")
            }
          >
            <input {...getInputProps()} />
            <b className="text-text-darker">{t("dragDropHint")}</b>
          </div>

          {tmpImageUrl && (
            <div className="mt-4 mb-8">
              <SubLabel>{t("uploadedImageLabel")}</SubLabel>
              <img
                alt={t("uploadedImageAlt")}
                src={tmpImageUrl}
                className="mt-4 max-w-xs max-h-64"
              />
            </div>
          )}
        </section>
      )}
    </Dropzone>
  );
}
