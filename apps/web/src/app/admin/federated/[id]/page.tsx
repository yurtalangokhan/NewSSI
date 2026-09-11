"use client";

import { useState, useEffect } from "react";
import { notFound } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useFederatedConnector } from "./useFederatedConnector";
import { FederatedConnectorForm } from "@/components/admin/federated/FederatedConnectorForm";
import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";
import FormSkeleton from "@/refresh-components/skeletons/FormSkeleton";

export default function EditFederatedConnectorPage(props: {
  params: Promise<{ id: string }>;
}) {
  const { t } = useTranslation("common", { keyPrefix: "admin" });
  const [params, setParams] = useState<{ id: string } | null>(null);

  useEffect(() => {
    props.params.then(setParams);
  }, [props.params]);

  const { sourceType, connectorData, credentialSchema, isLoading, error } =
    useFederatedConnector(params?.id ?? "");

  if (isLoading) {
    return (
      <div className="mx-auto w-full max-w-4xl p-6">
        <FormSkeleton fieldCount={4} />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex justify-center w-full h-full">
        <div className="mt-12 w-full max-w-4xl mx-auto">
          <div className="text-center">
            <Text as="h1" className="text-2xl font-bold text-red-600 mb-4">
              {t("federated.error")}
            </Text>
            <Text as="p" className="text-gray-600">
              {error}
            </Text>
          </div>
        </div>
      </div>
    );
  }

  if (!sourceType || !params) {
    notFound();
  }

  const connectorId = parseInt(params.id);

  return (
    <div className="flex justify-center w-full h-full">
      <div className="mt-12 w-full max-w-4xl mx-auto">
        <FederatedConnectorForm
          connector={sourceType}
          connectorId={connectorId}
          preloadedConnectorData={connectorData ?? undefined}
          preloadedCredentialSchema={credentialSchema ?? undefined}
        />
      </div>
    </div>
  );
}
