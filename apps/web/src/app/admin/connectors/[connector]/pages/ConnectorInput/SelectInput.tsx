import { useTranslation } from "react-i18next";
import CredentialSubText from "@/components/credentials/CredentialFields";
import { StringWithDescription } from "@/lib/connectors/connectors";
import { Field } from "formik";

export default function SelectInput({
  name,
  optional,
  description,
  options,
  label,
}: {
  name: string;
  optional?: boolean;
  description?: string;
  options: StringWithDescription[];
  label?: string;
}) {
  const { t } = useTranslation();
  return (
    <>
      <label
        htmlFor={name}
        className="block text-sm font-medium text-text-700 mb-1"
      >
        {label}
        {optional && (
          <span className="text-text-500 ml-1">
            {t("admin.fieldRendering.optionalSuffix")}
          </span>
        )}
      </label>
      {description && <CredentialSubText>{description}</CredentialSubText>}

      <Field
        as="select"
        name={name}
        className="w-full p-2 border border-border-03 rounded-08 bg-transparent text-text-04 focus:ring-2 focus:ring-lighter-agent focus:border-lighter-agent focus:outline-none"
      >
        <option value="">{t("common.selectAnOption")}</option>
        {options?.map((option: any) => (
          <option key={option.name} value={option.name}>
            {option.name}
          </option>
        ))}
      </Field>
    </>
  );
}
