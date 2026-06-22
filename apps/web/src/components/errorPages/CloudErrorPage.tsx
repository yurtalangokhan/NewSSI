import Text from "@/refresh-components/texts/Text";
import ErrorPageLayout from "@/components/errorPages/ErrorPageLayout";
import { APP_NAME } from "@/lib/appInfo";

export default function CloudError() {
  return (
    <ErrorPageLayout>
      <Text as="p" headingH2>
        Maintenance in Progress
      </Text>

      <Text as="p" text03>
        {APP_NAME} is currently in a maintenance window. Please check back in a
        couple of minutes.
      </Text>

      <Text as="p" text03>
        We apologize for any inconvenience this may cause and appreciate your
        patience.
      </Text>
    </ErrorPageLayout>
  );
}
