import {
  CloudEmbeddingModel,
  EmbeddingProvider,
  getFormattedProviderName,
} from "./interfaces";
import { Formik, Form } from "formik";
import * as Yup from "yup";
import { TextFormField, BooleanFormField } from "@/components/Field";
import { Dispatch, SetStateAction } from "react";
import Text from "@/components/ui/text";
import Button from "@/refresh-components/buttons/Button";
import { EmbeddingDetails } from "@/app/admin/embeddings/EmbeddingModelSelectionForm";
import { useTranslation } from "react-i18next";

export function CustomEmbeddingModelForm({
  setShowTentativeModel,
  currentValues,
  provider,
  embeddingType,
}: {
  setShowTentativeModel: Dispatch<SetStateAction<CloudEmbeddingModel | null>>;
  currentValues: CloudEmbeddingModel | null;
  provider: EmbeddingDetails;
  embeddingType: EmbeddingProvider;
}) {
  const { t } = useTranslation("common", { keyPrefix: "admin" });

  return (
    <div>
      <Formik
        initialValues={
          currentValues || {
            model_name: "",
            model_dim: 768,
            normalize: false,
            query_prefix: "",
            passage_prefix: "",
            provider_type: embeddingType,
            api_key: "",
            enabled: true,
            api_url: provider.api_url,
            description: "",
            index_name: "",
          }
        }
        validationSchema={Yup.object().shape({
          model_name: Yup.string().required(t("customEmbedding.modelNameRequired")),
          model_dim: Yup.number().required(t("customEmbedding.modelDimRequired")),
          normalize: Yup.boolean().required(),
          query_prefix: Yup.string(),
          passage_prefix: Yup.string(),
          provider_type: Yup.string().required(
            t("customEmbedding.providerTypeRequired")
          ),
          api_key: Yup.string().optional(),
          enabled: Yup.boolean(),
          api_url: Yup.string().required(t("customEmbedding.apiUrlRequired")),
          description: Yup.string(),
          index_name: Yup.string().nullable(),
        })}
        onSubmit={async (values) => {
          setShowTentativeModel(values as CloudEmbeddingModel);
        }}
      >
        {({ isSubmitting, submitForm, errors }) => (
          <Form>
            <Text className="text-xl text-text-900 font-bold mb-4">
              {t("customEmbedding.specifyDetails", {
                provider: getFormattedProviderName(embeddingType),
              })}
            </Text>
            <TextFormField
              name="model_name"
              label={t("customEmbedding.modelName")}
              subtext={t("customEmbedding.modelNameSubtext", {
                provider: getFormattedProviderName(embeddingType),
              })}
              placeholder={t("customEmbedding.modelNamePlaceholder")}
            />

            <TextFormField
              name="model_dim"
              label={t("customEmbedding.modelDimension")}
              subtext={t("customEmbedding.modelDimensionSubtext")}
              placeholder={t("customEmbedding.modelDimensionPlaceholder")}
              type="number"
            />

            <BooleanFormField
              removeIndent
              name="normalize"
              label={t("customEmbedding.normalize")}
              subtext={t("customEmbedding.normalizeSubtext")}
            />

            <TextFormField
              name="query_prefix"
              label={t("customEmbedding.queryPrefix")}
              subtext={t("customEmbedding.queryPrefixSubtext")}
            />

            <TextFormField
              name="passage_prefix"
              label={t("customEmbedding.passagePrefix")}
              subtext={t("customEmbedding.passagePrefixSubtext")}
            />

            <Button
              type="submit"
              disabled={isSubmitting}
              className="w-64 mx-auto"
            >
              {t("customEmbedding.configureButton", {
                provider: getFormattedProviderName(embeddingType),
              })}
            </Button>
          </Form>
        )}
      </Formik>
    </div>
  );
}
