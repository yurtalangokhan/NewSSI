import React, { forwardRef } from "react";
import { useTranslation } from "react-i18next";
import { Formik, Form, FormikProps } from "formik";
import * as Yup from "yup";
import {
  AdvancedSearchConfiguration,
  EmbeddingPrecision,
  LLMContextualCost,
} from "../interfaces";
import { BooleanFormField, SelectorFormField } from "@/components/Field";
import NumberInput from "../../connectors/[connector]/pages/ConnectorInput/NumberInput";
import { StringOrNumberOption } from "@/components/Dropdown";
import useSWR from "swr";
import { LLM_CONTEXTUAL_COST_ADMIN_URL } from "@/lib/llmConfig/constants";
import { errorHandlingFetcher } from "@/lib/fetcher";
import { NEXT_PUBLIC_CLOUD_ENABLED } from "@/lib/constants";
// Number of tokens to show cost calculation for
const COST_CALCULATION_TOKENS = 1_000_000;

interface AdvancedEmbeddingFormPageProps {
  updateAdvancedEmbeddingDetails: (
    key: keyof AdvancedSearchConfiguration,
    value: any
  ) => void;
  advancedEmbeddingDetails: AdvancedSearchConfiguration;
  embeddingProviderType: string | null;
  onValidationChange?: (
    isValid: boolean,
    errors: Record<string, string>
  ) => void;
}

// Options for embedding precision based on EmbeddingPrecision enum
const embeddingPrecisionOptions: StringOrNumberOption[] = [
  { name: EmbeddingPrecision.BFLOAT16, value: EmbeddingPrecision.BFLOAT16 },
  { name: EmbeddingPrecision.FLOAT, value: EmbeddingPrecision.FLOAT },
];

const AdvancedEmbeddingFormPage = forwardRef<
  FormikProps<any>,
  AdvancedEmbeddingFormPageProps
>(
  (
    {
      updateAdvancedEmbeddingDetails,
      advancedEmbeddingDetails,
      embeddingProviderType,
      onValidationChange,
    },
    ref
  ) => {
    const { t } = useTranslation("common", {
      keyPrefix: "admin.embeddings.advancedForm",
    });
    // Fetch contextual costs
    const { data: contextualCosts, error: costError } = useSWR<
      LLMContextualCost[]
    >(LLM_CONTEXTUAL_COST_ADMIN_URL, errorHandlingFetcher);

    const llmOptions: StringOrNumberOption[] = React.useMemo(
      () =>
        (contextualCosts || []).map((cost) => {
          return {
            // Use model_name as display - contextual costs don't have display_name field
            name: cost.model_name,
            value: cost.model_name,
          };
        }),
      [contextualCosts]
    );

    // Helper function to format cost as USD
    const formatCost = (cost: number) => {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
      }).format(cost);
    };

    // Get cost info for selected model
    const getSelectedModelCost = (modelName: string | null) => {
      if (!contextualCosts || !modelName) return null;
      return contextualCosts.find((cost) => cost.model_name === modelName);
    };

    // Get the current value for the selector based on the parent state
    const getCurrentLLMValue = React.useMemo(() => {
      if (!advancedEmbeddingDetails.contextual_rag_llm_name) return null;
      return advancedEmbeddingDetails.contextual_rag_llm_name;
    }, [advancedEmbeddingDetails.contextual_rag_llm_name]);

    return (
      <div className="py-4 rounded-lg max-w-4xl px-4 mx-auto">
        <Formik
          innerRef={ref}
          initialValues={{
            ...advancedEmbeddingDetails,
            contextual_rag_llm: getCurrentLLMValue,
          }}
          validationSchema={Yup.object().shape({
            multilingual_expansion: Yup.array().of(Yup.string()),
            multipass_indexing: Yup.boolean(),
            enable_contextual_rag: Yup.boolean(),
            contextual_rag_llm: Yup.string()
              .nullable()
              .test(
                "required-if-contextual-rag",
                t("llmRequiredForContextualRag"),
                function (value) {
                  const enableContextualRag = this.parent.enable_contextual_rag;
                  console.log("enableContextualRag", enableContextualRag);
                  console.log("value", value);
                  return !enableContextualRag || value !== null;
                }
              ),
            embedding_precision: Yup.string().nullable(),
            reduced_dimension: Yup.number()
              .nullable()
              .test(
                "positive",
                t("reducedDimensionMinError"),
                (value) => value === null || value === undefined || value >= 256
              )
              .test("openai", t("reducedDimensionOpenAIOnlyError"), (value) => {
                return embeddingProviderType === "openai" || value === null;
              }),
          })}
          onSubmit={async (_, { setSubmitting }) => {
            setSubmitting(false);
          }}
          validate={(values) => {
            // Call updateAdvancedEmbeddingDetails for each changed field
            Object.entries(values).forEach(([key, value]) => {
              if (key === "contextual_rag_llm") {
                const selectedModel = (contextualCosts || []).find(
                  (cost) => cost.model_name === value
                );
                if (selectedModel) {
                  updateAdvancedEmbeddingDetails(
                    "contextual_rag_llm_provider",
                    selectedModel.provider
                  );
                  updateAdvancedEmbeddingDetails(
                    "contextual_rag_llm_name",
                    selectedModel.model_name
                  );
                }
              } else {
                updateAdvancedEmbeddingDetails(
                  key as keyof AdvancedSearchConfiguration,
                  value
                );
              }
            });

            // Run validation and report errors
            if (onValidationChange) {
              // We'll return an empty object here since Yup will handle the actual validation
              // But we need to check if there are any validation errors
              const errors: Record<string, string> = {};
              try {
                // Manually validate against the schema
                Yup.object()
                  .shape({
                    multilingual_expansion: Yup.array().of(Yup.string()),
                    multipass_indexing: Yup.boolean(),
                    enable_contextual_rag: Yup.boolean(),
                    contextual_rag_llm: Yup.string()
                      .nullable()
                      .test(
                        "required-if-contextual-rag",
                        t("llmRequiredForContextualRag"),
                        function (value) {
                          const enableContextualRag =
                            this.parent.enable_contextual_rag;
                          return !enableContextualRag || value !== null;
                        }
                      ),
                    embedding_precision: Yup.string().nullable(),
                    reduced_dimension: Yup.number()
                      .nullable()
                      .test(
                        "positive",
                        t("reducedDimensionMinError"),
                        (value) =>
                          value === null || value === undefined || value >= 256
                      )
                      .test(
                        "openai",
                        t("reducedDimensionOpenAIOnlyError"),
                        (value) => {
                          return (
                            embeddingProviderType === "openai" || value === null
                          );
                        }
                      ),
                  })
                  .validateSync(values, { abortEarly: false });
                onValidationChange(true, {});
              } catch (validationError) {
                if (validationError instanceof Yup.ValidationError) {
                  validationError.inner.forEach((err) => {
                    if (err.path) {
                      errors[err.path] = err.message;
                    }
                  });
                  onValidationChange(false, errors);
                }
              }
            }

            return {}; // Return empty object as Formik will handle the errors
          }}
          enableReinitialize={true}
        >
          {({ values }) => (
            <Form>
              <BooleanFormField
                subtext={t("multipassIndexingSubtext")}
                optional
                label={t("multipassIndexingLabel")}
                name="multipass_indexing"
              />
              <BooleanFormField
                subtext={
                  NEXT_PUBLIC_CLOUD_ENABLED
                    ? t("contextualRagCloudDisabled")
                    : t("contextualRagSubtext")
                }
                optional
                label={t("contextualRagLabel")}
                name="enable_contextual_rag"
                disabled={NEXT_PUBLIC_CLOUD_ENABLED}
              />
              <div>
                <SelectorFormField
                  name="contextual_rag_llm"
                  label={t("contextualRagLlmLabel")}
                  subtext={
                    costError
                      ? t("errorLoadingModels")
                      : !contextualCosts
                        ? t("loadingModels")
                        : values.enable_contextual_rag
                          ? t("selectLlmForContextualRag")
                          : t("enableContextualRagFirst")
                  }
                  options={llmOptions}
                  disabled={
                    !values.enable_contextual_rag ||
                    !contextualCosts ||
                    !!costError
                  }
                />
                {values.enable_contextual_rag &&
                  values.contextual_rag_llm &&
                  !costError && (
                    <div className="mt-2 text-sm text-text-600">
                      {contextualCosts ? (
                        <>
                          {t("estimatedCostPrefix")}{" "}
                          {COST_CALCULATION_TOKENS.toLocaleString()}{" "}
                          {t("estimatedCostSuffix")}{" "}
                          <span className="font-medium">
                            {getSelectedModelCost(values.contextual_rag_llm)
                              ? formatCost(
                                  getSelectedModelCost(
                                    values.contextual_rag_llm
                                  )!.cost
                                )
                              : t("costNotAvailable")}
                          </span>
                        </>
                      ) : (
                        t("loadingCostInfo")
                      )}
                    </div>
                  )}
              </div>
              <SelectorFormField
                name="embedding_precision"
                label={t("embeddingPrecisionLabel")}
                options={embeddingPrecisionOptions}
                subtext={t("embeddingPrecisionSubtext")}
              />

              <NumberInput
                description={t("reducedDimensionDescription")}
                optional={true}
                label={t("reducedDimensionLabel")}
                name="reduced_dimension"
              />
            </Form>
          )}
        </Formik>
      </div>
    );
  }
);
export default AdvancedEmbeddingFormPage;

AdvancedEmbeddingFormPage.displayName = "AdvancedEmbeddingFormPage";
