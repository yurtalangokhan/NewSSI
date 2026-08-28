import { ValidSources } from "@/lib/types";
import { getSourceDocLink } from "@/lib/sources";
import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";

export default function ConnectorDocsLink({
  sourceType,
  className,
}: {
  sourceType: ValidSources;
  className?: string;
}) {
  const { t } = useTranslation("common", { keyPrefix: "admin" });
  const docsLink = getSourceDocLink(sourceType);

  if (!docsLink) {
    return null;
  }

  const paragraphClass = ["text-sm", className].filter(Boolean).join(" ");

  return (
    <Text as="p" className={paragraphClass}>
      {t("connectorDocsLink.checkOut")}
      <a
        className="text-blue-600 hover:underline"
        target="_blank"
        rel="noopener"
        href={docsLink}
      >
        {" "}
        {t("connectorDocsLink.ourDocs")}{" "}
      </a>
      {t("connectorDocsLink.forMoreInfo")}
    </Text>
  );
}
