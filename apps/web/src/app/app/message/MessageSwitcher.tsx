import { Button } from "@opal/components";
import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";
import { SvgChevronLeft, SvgChevronRight } from "@opal/icons";

interface MessageSwitcherProps {
  currentPage: number;
  totalPages: number;
  handlePrevious: () => void;
  handleNext: () => void;
  disableForStreaming?: boolean;
}

export default function MessageSwitcher({
  currentPage,
  totalPages,
  handlePrevious,
  handleNext,
  disableForStreaming,
}: MessageSwitcherProps) {
  const { t } = useTranslation();
  const handle = (num: number, callback: () => void) =>
    disableForStreaming
      ? undefined
      : currentPage === num
        ? undefined
        : callback;
  const previous = handle(1, handlePrevious);
  const next = handle(totalPages, handleNext);

  return (
    <div
      className="flex flex-row items-center gap-1"
      data-testid="MessageSwitcher/container"
    >
      <Button
        icon={SvgChevronLeft}
        onClick={previous}
        prominence="tertiary"
        disabled={disableForStreaming}
        tooltip={
          disableForStreaming
            ? t("messageSwitcher.waitForCompletion")
            : t("messageSwitcher.previous")
        }
      />

      <div className="flex flex-row items-center justify-center">
        <Text as="p" text03 mainUiAction>
          {currentPage}
        </Text>
        <Text as="p" text03 mainUiAction>
          /
        </Text>
        <Text as="p" text03 mainUiAction>
          {totalPages}
        </Text>
      </div>

      <Button
        icon={SvgChevronRight}
        onClick={next}
        prominence="tertiary"
        disabled={disableForStreaming}
        tooltip={
          disableForStreaming
            ? t("messageSwitcher.waitForCompletion")
            : t("messageSwitcher.next")
        }
      />
    </div>
  );
}
