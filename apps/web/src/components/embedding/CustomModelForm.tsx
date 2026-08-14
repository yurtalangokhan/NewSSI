"use client";

import { BooleanFormField, TextFormField } from "@/components/Field";
import Button from "@/refresh-components/buttons/Button";
import { Form, Formik } from "formik";
import * as Yup from "yup";
import { HostedEmbeddingModel } from "./interfaces";
import { useTranslation } from "react-i18next";

export function CustomModelForm({
  onSubmit,
}: {
  onSubmit: (model: HostedEmbeddingModel) => void;
}) {
  const { t } = useTranslation();
  return (
    <div>
      <Formik
        initialValues={{
          model_name: "",
          model_dim: "",
          query_prefix: "",
          passage_prefix: "",
          description: "",
          normalize: true,
        }}
        validationSchema={Yup.object().shape({
          model_name: Yup.string().required(
            t("admin.embeddings.customModelForm.nameSubtext")
          ),
          model_dim: Yup.number().required(
            t("admin.embeddings.customModelForm.dimSubtext")
          ),
          query_prefix: Yup.string(),
          passage_prefix: Yup.string(),
          normalize: Yup.boolean().required(),
        })}
        onSubmit={async (values, formikHelpers) => {
          onSubmit({
            ...values,
            model_dim: parseInt(values.model_dim),
            api_key: null,
            provider_type: null,
            index_name: null,
            api_url: null,
          });
        }}
      >
        {({ isSubmitting }) => (
          <Form>
            <TextFormField
              name="model_name"
              label={t("admin.embeddings.customModelForm.nameLabel")}
              subtext={t("admin.embeddings.customModelForm.nameSubtext")}
              placeholder={t(
                "admin.embeddings.customModelForm.namePlaceholder"
              )}
            />

            <TextFormField
              name="model_dim"
              label={t("admin.embeddings.customModelForm.dimLabel")}
              subtext={t("admin.embeddings.customModelForm.dimSubtext")}
              placeholder={t("admin.embeddings.customModelForm.dimPlaceholder")}
              type="number"
            />
            <TextFormField
              min={-1}
              name="description"
              label={t("admin.embeddings.customModelForm.descriptionLabel")}
              subtext={t("admin.embeddings.customModelForm.descriptionSubtext")}
              placeholder=""
            />

            <TextFormField
              name="query_prefix"
              label={t("admin.embeddings.customModelForm.queryPrefixLabel")}
              subtext={t("admin.embeddings.customModelForm.queryPrefixSubtext")}
              placeholder={t(
                "admin.embeddings.customModelForm.queryPrefixPlaceholder"
              )}
            />
            <TextFormField
              name="passage_prefix"
              label={t("admin.embeddings.customModelForm.passagePrefixLabel")}
              subtext={t(
                "admin.embeddings.customModelForm.passagePrefixSubtext"
              )}
              placeholder={t(
                "admin.embeddings.customModelForm.passagePrefixPlaceholder"
              )}
            />

            <BooleanFormField
              removeIndent
              name="normalize"
              label={t("admin.embeddings.customModelForm.normalizeLabel")}
              subtext={t("admin.embeddings.customModelForm.normalizeSubtext")}
            />

            <Button
              type="submit"
              disabled={isSubmitting}
              className="w-64 mx-auto"
            >
              {t("admin.embeddings.customModelForm.chooseButton")}
            </Button>
          </Form>
        )}
      </Formik>
    </div>
  );
}
