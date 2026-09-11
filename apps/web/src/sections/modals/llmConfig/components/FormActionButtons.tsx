import { LoadingAnimation } from "@/components/Loading";
import Text from "@/refresh-components/texts/Text";
import Button from "@/refresh-components/buttons/Button";
import { SvgTrash } from "@opal/icons";
import { LLMProviderView } from "@/interfaces/llm";
import { LLM_PROVIDERS_ADMIN_URL } from "@/lib/llmConfig/constants";
import { deleteLlmProvider } from "@/lib/llmConfig/svc";
import { useTranslation } from "react-i18next";

interface FormActionButtonsProps {
  isTesting: boolean;
  testError: string;
  existingLlmProvider?: LLMProviderView;
  mutate: (key: string) => void;
  onClose: () => void;
  isFormValid: boolean;
}

export function FormActionButtons({
  isTesting,
  testError,
  existingLlmProvider,
  mutate,
  onClose,
  isFormValid,
}: FormActionButtonsProps) {
  const { t } = useTranslation();
  const handleDelete = async () => {
    if (!existingLlmProvider) return;

    try {
      await deleteLlmProvider(existingLlmProvider.id);
      mutate(LLM_PROVIDERS_ADMIN_URL);
      onClose();
    } catch (e) {
      const message =
        e instanceof Error ? e.message : t("llmConfig.unknownError");
      alert(t("llmConfig.deleteProviderError", { error: message }));
    }
  };

  return (
    <>
      {testError && (
        <Text as="p" className="text-error mt-2">
          {testError}
        </Text>
      )}

      <div className="flex w-full mt-4 gap-2">
        <Button type="submit" disabled={isTesting || !isFormValid}>
          {isTesting ? (
            <Text as="p" inverted>
              <LoadingAnimation text={t("llmConfig.testing")} />
            </Text>
          ) : existingLlmProvider ? (
            t("llmConfig.update")
          ) : (
            t("llmConfig.enable")
          )}
        </Button>
        {existingLlmProvider && (
          <Button danger leftIcon={SvgTrash} onClick={handleDelete}>
            {t("llmConfig.delete")}
          </Button>
        )}
      </div>
    </>
  );
}
