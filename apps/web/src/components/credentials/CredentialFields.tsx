import { JSX } from "react";
import Text from "@/refresh-components/texts/Text";

export default function CredentialSubText({
  children,
}: {
  children: JSX.Element | string;
}) {
  return (
    <Text as="p" className="text-sm mb-2 whitespace-break-spaces text-text-500">
      {children}
    </Text>
  );
}
