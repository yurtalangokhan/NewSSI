import { useTranslation } from "react-i18next";
import { useFormContext } from "@/components/context/FormContext";
import Button from "@/refresh-components/buttons/Button";
import { SvgArrowLeft, SvgArrowRight, SvgPlusCircle } from "@opal/icons";

const NavigationRow = ({
  noAdvanced,
  noCredentials,
  activatedCredential,
  onSubmit,
  isValid,
}: {
  isValid: boolean;
  onSubmit: () => void;
  noAdvanced: boolean;
  noCredentials: boolean;
  activatedCredential: boolean;
}) => {
  const { t } = useTranslation("common", {
    keyPrefix: "admin.connectorNavigationRow",
  });
  const { formStep, prevFormStep, nextFormStep } = useFormContext();

  return (
    <div className="mt-4 w-full grid grid-cols-3">
      <div>
        {((formStep > 0 && !noCredentials) ||
          (formStep > 1 && !noAdvanced)) && (
          <Button secondary onClick={prevFormStep} leftIcon={SvgArrowLeft}>
            {t("previousButton")}
          </Button>
        )}
      </div>
      <div className="flex justify-center">
        {(formStep > 0 || noCredentials) && (
          <Button
            disabled={!isValid}
            rightIcon={SvgPlusCircle}
            onClick={onSubmit}
          >
            {t("createConnectorButton")}
          </Button>
        )}
      </div>
      <div className="flex justify-end">
        {formStep === 0 && (
          <Button
            action
            disabled={!activatedCredential}
            rightIcon={SvgArrowRight}
            onClick={() => nextFormStep()}
          >
            {t("continueButton")}
          </Button>
        )}
        {!noAdvanced && formStep === 1 && (
          <Button
            secondary
            disabled={!isValid}
            rightIcon={SvgArrowRight}
            onClick={() => nextFormStep()}
          >
            {t("advancedButton")}
          </Button>
        )}
      </div>
    </div>
  );
};
export default NavigationRow;
