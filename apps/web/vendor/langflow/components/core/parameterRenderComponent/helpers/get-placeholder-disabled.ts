import i18n from "../../../../i18n";

export const getPlaceholder = (
  disabled: boolean,
  returnMessage: string = localization.t("input.placeholder"),
) => {
  if (disabled) return localization.t("component.receivingInput");

  return returnMessage || localization.t("input.placeholder");
};
