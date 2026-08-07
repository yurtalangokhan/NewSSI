"use client";

import { useTranslation } from "react-i18next";
import { toast } from "@/hooks/useToast";
import { StandardAnswerCategory, StandardAnswer } from "@/lib/types";
import CardSection from "@/components/admin/CardSection";
import Button from "@/refresh-components/buttons/Button";
import { Form, Formik } from "formik";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import * as Yup from "yup";
import {
  createStandardAnswer,
  createStandardAnswerCategory,
  StandardAnswerCreationRequest,
  updateStandardAnswer,
} from "./lib";
import {
  TextFormField,
  MarkdownFormField,
  BooleanFormField,
  SelectorFormField,
} from "@/components/Field";
import MultiSelectDropdown from "@/components/MultiSelectDropdown";

function mapKeywordSelectToMatchAny(keywordSelect: "any" | "all"): boolean {
  return keywordSelect == "any";
}

function mapMatchAnyToKeywordSelect(matchAny: boolean): "any" | "all" {
  return matchAny ? "any" : "all";
}

export const StandardAnswerCreationForm = ({
  standardAnswerCategories,
  existingStandardAnswer,
}: {
  standardAnswerCategories: StandardAnswerCategory[];
  existingStandardAnswer?: StandardAnswer;
}) => {
  const { t } = useTranslation("common", {
    keyPrefix: "admin.standardAnswerForm",
  });
  const isUpdate = existingStandardAnswer !== undefined;
  const router = useRouter();

  return (
    <div>
      <CardSection>
        <Formik
          initialValues={{
            keyword: existingStandardAnswer
              ? existingStandardAnswer.keyword
              : "",
            answer: existingStandardAnswer ? existingStandardAnswer.answer : "",
            categories: existingStandardAnswer
              ? existingStandardAnswer.categories
              : [],
            matchRegex: existingStandardAnswer
              ? existingStandardAnswer.match_regex
              : false,
            matchAnyKeywords: existingStandardAnswer
              ? mapMatchAnyToKeywordSelect(
                  existingStandardAnswer.match_any_keywords
                )
              : "all",
          }}
          validationSchema={Yup.object().shape({
            keyword: Yup.string()
              .required(t("keywordRequired"))
              .max(255)
              .min(1),
            answer: Yup.string().required(t("answerRequired")).min(1),
            categories: Yup.array()
              .required()
              .min(1, t("atLeastOneCategoryRequired")),
          })}
          onSubmit={async (values, formikHelpers) => {
            formikHelpers.setSubmitting(true);

            const cleanedValues: StandardAnswerCreationRequest = {
              ...values,
              matchAnyKeywords: mapKeywordSelectToMatchAny(
                values.matchAnyKeywords
              ),
              categories: values.categories.map((category) => category.id),
            };

            let response;
            if (isUpdate) {
              response = await updateStandardAnswer(
                existingStandardAnswer.id,
                cleanedValues
              );
            } else {
              response = await createStandardAnswer(cleanedValues);
            }
            formikHelpers.setSubmitting(false);
            if (response.ok) {
              router.push(`/ee/admin/standard-answer?u=${Date.now()}` as Route);
            } else {
              const responseJson = await response.json();
              const errorMsg = responseJson.detail || responseJson.message;
              toast.error(
                isUpdate
                  ? t("updateErrorToast", { error: errorMsg })
                  : t("createErrorToast", { error: errorMsg })
              );
            }
          }}
        >
          {({ isSubmitting, values, setFieldValue }) => (
            <Form>
              {values.matchRegex ? (
                <TextFormField
                  name="keyword"
                  label={t("regexPatternLabel")}
                  isCode
                  tooltip={t("regexPatternTooltip")}
                  placeholder="(?:it|support)\s*ticket"
                />
              ) : values.matchAnyKeywords == "any" ? (
                <TextFormField
                  name="keyword"
                  label={t("anyKeywordsLabel")}
                  tooltip={t("keywordsTooltip")}
                  placeholder={t("anyKeywordsPlaceholder")}
                />
              ) : (
                <TextFormField
                  name="keyword"
                  label={t("allKeywordsLabel")}
                  tooltip={t("keywordsTooltip")}
                  placeholder={t("allKeywordsPlaceholder")}
                />
              )}
              <BooleanFormField
                subtext={t("matchRegexSubtext")}
                optional
                label={t("matchRegexLabel")}
                name="matchRegex"
              />
              {values.matchRegex ? null : (
                <SelectorFormField
                  defaultValue={`all`}
                  label={t("strategyLabel")}
                  subtext={t("strategySubtext")}
                  name="matchAnyKeywords"
                  options={[
                    {
                      name: t("allKeywordsOption"),
                      value: "all",
                    },
                    {
                      name: t("anyKeywordsOption"),
                      value: "any",
                    },
                  ]}
                  onSelect={(selected) => {
                    setFieldValue("matchAnyKeywords", selected);
                  }}
                />
              )}
              <div className="w-full">
                <MarkdownFormField
                  name="answer"
                  label={t("answerLabel")}
                  placeholder={t("answerPlaceholder")}
                />
              </div>
              <div className="w-4/12">
                <MultiSelectDropdown
                  name="categories"
                  label={t("categoriesLabel")}
                  onChange={(selected_options) => {
                    const selected_categories = selected_options.map(
                      (option) => {
                        return { id: Number(option.value), name: option.label };
                      }
                    );
                    setFieldValue("categories", selected_categories);
                  }}
                  creatable={true}
                  onCreate={async (created_name) => {
                    const response = await createStandardAnswerCategory({
                      name: created_name,
                    });
                    const newCategory = await response.json();
                    return {
                      label: newCategory.name,
                      value: newCategory.id.toString(),
                    };
                  }}
                  options={standardAnswerCategories.map((category) => ({
                    label: category.name,
                    value: category.id.toString(),
                  }))}
                  initialSelectedOptions={values.categories.map((category) => ({
                    label: category.name,
                    value: category.id.toString(),
                  }))}
                />
              </div>
              <div className="py-4 flex">
                <Button
                  type="submit"
                  disabled={isSubmitting}
                  className="mx-auto w-64"
                >
                  {isUpdate ? t("updateButton") : t("createButton")}
                </Button>
              </div>
            </Form>
          )}
        </Formik>
      </CardSection>
    </div>
  );
};
