"use client";

import { useTranslation } from "react-i18next";
import { useState, useEffect, useMemo } from "react";
import { FieldArray, useFormikContext, ErrorMessage } from "formik";
import { DocumentSetSummary } from "@/lib/types";
import { toast } from "@/hooks/useToast";
import {
  Label,
  SelectorFormField,
  SubLabel,
  TextArrayField,
  TextFormField,
} from "@/components/Field";
import Button from "@/refresh-components/buttons/Button";
import { MinimalPersonaSnapshot } from "@/app/admin/agents/interfaces";
import DocumentSetCard from "@/sections/cards/DocumentSetCard";
import CollapsibleSection from "@/app/admin/agents/CollapsibleSection";
import { StandardAnswerCategoryResponse } from "@/components/standardAnswers/getStandardAnswerCategoriesIfEE";
import { StandardAnswerCategoryDropdownField } from "@/components/standardAnswers/StandardAnswerCategoryDropdown";
import { RadioGroup } from "@/components/ui/radio-group";
import { RadioGroupItemField } from "@/components/ui/RadioGroupItemField";
import { AlertCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import type { Route } from "next";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { TooltipProvider } from "@radix-ui/react-tooltip";
import { SourceIcon } from "@/components/SourceIcon";
import Link from "next/link";
import AgentAvatar from "@/refresh-components/avatars/AgentAvatar";
import { Badge } from "@/components/ui/badge";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/ui/accordion";
import Separator from "@/refresh-components/Separator";
import { CheckboxField } from "@/refresh-components/form/LabeledCheckboxField";

export interface SlackChannelConfigFormFieldsProps {
  isUpdate: boolean;
  isDefault: boolean;
  documentSets: DocumentSetSummary[];
  searchEnabledAgents: MinimalPersonaSnapshot[];
  nonSearchAgents: MinimalPersonaSnapshot[];
  standardAnswerCategoryResponse: StandardAnswerCategoryResponse;
  slack_bot_id: number;
  formikProps: any;
}

export function SlackChannelConfigFormFields({
  isUpdate,
  isDefault,
  documentSets,
  searchEnabledAgents,
  nonSearchAgents,
  standardAnswerCategoryResponse,
  slack_bot_id,
  formikProps,
}: SlackChannelConfigFormFieldsProps) {
  const { t } = useTranslation();
  const router = useRouter();
  const { values, setFieldValue } = useFormikContext<any>();
  const [viewUnselectableSets, setViewUnselectableSets] = useState(false);
  const [viewSyncEnabledAgents, setViewSyncEnabledAgents] = useState(false);

  // Helper function to check if a document set contains sync connectors
  const documentSetContainsSync = (documentSet: DocumentSetSummary) => {
    return documentSet.cc_pair_summaries.some(
      (summary) => summary.access_type === "sync"
    );
  };

  // Helper function to check if a document set contains private connectors
  const documentSetContainsPrivate = (documentSet: DocumentSetSummary) => {
    return documentSet.cc_pair_summaries.some(
      (summary) => summary.access_type === "private"
    );
  };

  // Helper function to get cc_pair_summaries from DocumentSetSummary
  const getCcPairSummaries = (documentSet: DocumentSetSummary) => {
    return documentSet.cc_pair_summaries;
  };

  const [syncEnabledAgents, availableAgents] = useMemo(() => {
    const sync: MinimalPersonaSnapshot[] = [];
    const available: MinimalPersonaSnapshot[] = [];

    searchEnabledAgents.forEach((persona) => {
      const hasSyncSet = persona.document_sets.some(documentSetContainsSync);
      if (hasSyncSet) {
        sync.push(persona);
      } else {
        available.push(persona);
      }
    });

    return [sync, available];
  }, [searchEnabledAgents]);

  const unselectableSets = useMemo(() => {
    return documentSets.filter(documentSetContainsSync);
  }, [documentSets]);

  const memoizedPrivateConnectors = useMemo(() => {
    const uniqueDescriptors = new Map();
    documentSets.forEach((ds: DocumentSetSummary) => {
      const ccPairSummaries = getCcPairSummaries(ds);
      ccPairSummaries.forEach((summary: any) => {
        if (
          summary.access_type === "private" &&
          !uniqueDescriptors.has(summary.id)
        ) {
          uniqueDescriptors.set(summary.id, summary);
        }
      });
    });
    return Array.from(uniqueDescriptors.values());
  }, [documentSets]);

  const selectableSets = useMemo(() => {
    return documentSets.filter((ds) => !documentSetContainsSync(ds));
  }, [documentSets]);

  useEffect(() => {
    const invalidSelected = values.document_sets.filter((dsId: number) =>
      unselectableSets.some((us) => us.id === dsId)
    );
    if (invalidSelected.length > 0) {
      setFieldValue(
        "document_sets",
        values.document_sets.filter(
          (dsId: number) => !invalidSelected.includes(dsId)
        )
      );
      toast.warning(t("slackChannelConfigs.removedDocumentSets"));
    }
  }, [unselectableSets, values.document_sets, setFieldValue]);

  const shouldShowPrivacyAlert = useMemo(() => {
    if (values.knowledge_source === "document_sets") {
      const selectedSets = documentSets.filter((ds) =>
        values.document_sets.includes(ds.id)
      );
      return selectedSets.some((ds) => documentSetContainsPrivate(ds));
    } else if (values.knowledge_source === "assistant") {
      const chosenAgent = searchEnabledAgents.find(
        (p) => p.id == values.persona_id
      );
      return chosenAgent?.document_sets.some((ds) =>
        documentSetContainsPrivate(ds)
      );
    }
    return false;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [values.knowledge_source, values.document_sets, values.persona_id]);

  return (
    <>
      <div className="w-full">
        {isDefault && (
          <>
            <Badge variant="agent" className="bg-blue-100 text-blue-800">
              {t("slackChannelConfigs.defaultConfigBadge")}
            </Badge>
            <p className="mt-2 text-sm">
              {t("slackChannelConfigs.defaultConfigDesc")}
            </p>
            <div className="mt-4 p-4 bg-background rounded-md border border-neutral-300">
              <CheckboxField
                name="disabled"
                label={t("slackChannelConfigs.disableDefaultConfig")}
                labelClassName="text-text"
              />
              <p className="mt-2 text-sm italic">
                {t("slackChannelConfigs.disableDefaultWarning")}
              </p>
            </div>
          </>
        )}
        {!isDefault && (
          <>
            <TextFormField
              name="channel_name"
              label={t("slackChannelConfigs.slackChannelName")}
              placeholder={t("slackChannelConfigs.slackChannelPlaceholder")}
              subtext={t("slackChannelConfigs.slackChannelSubtext")}
            />
          </>
        )}
        <div className="space-y-2 mt-4">
          <Label>{t("slackChannelConfigs.knowledgeSource")}</Label>
          <RadioGroup
            className="flex flex-col gap-y-4"
            value={values.knowledge_source}
            onValueChange={(value: string) => {
              setFieldValue("knowledge_source", value);
            }}
          >
            <RadioGroupItemField
              value="all_public"
              id="all_public"
              label={t("slackChannelConfigs.allPublicKnowledge")}
              sublabel={t("slackChannelConfigs.allPublicKnowledgeDesc")}
            />
            {selectableSets.length + unselectableSets.length > 0 && (
              <RadioGroupItemField
                value="document_sets"
                id="document_sets"
                label={t("slackChannelConfigs.specificDocumentSets")}
                sublabel={t("slackChannelConfigs.specificDocumentSetsDesc")}
              />
            )}
            <RadioGroupItemField
              value="assistant"
              id="assistant"
              label={t("slackChannelConfigs.searchAgent")}
              sublabel={t("slackChannelConfigs.searchAgentDesc")}
            />
            <RadioGroupItemField
              value="non_search_agent"
              id="non_search_agent"
              label={t("slackChannelConfigs.nonSearchAgent")}
              sublabel={t("slackChannelConfigs.nonSearchAgentDesc")}
            />
          </RadioGroup>
        </div>
        {values.knowledge_source === "document_sets" &&
          documentSets.length > 0 && (
            <div className="mt-4">
              <SubLabel>
                <>
                  {t("slackChannelConfigs.selectDocSetsLabel")}
                  <br />
                  {unselectableSets.length > 0 ? (
                    <span>
                      {t("slackChannelConfigs.incompatibleDocSets", { visibility: viewUnselectableSets ? t("slackChannelConfigs.visible") : t("slackChannelConfigs.hidden") })}{" "}
                      <button
                        type="button"
                        onClick={() =>
                          setViewUnselectableSets(
                            (viewUnselectableSets) => !viewUnselectableSets
                          )
                        }
                        className="text-sm text-action-link-05"
                      >
                        {viewUnselectableSets
                          ? t("slackChannelConfigs.hideUnselectable")
                          : t("slackChannelConfigs.viewAll")}
                        {t("slackChannelConfigs.documentSetsLabel")}
                      </button>
                    </span>
                  ) : (
                    ""
                  )}
                </>
              </SubLabel>
              <FieldArray
                name="document_sets"
                render={(arrayHelpers) => (
                  <>
                    {selectableSets.length > 0 && (
                      <div className="mb-3 mt-2 flex gap-2 flex-wrap text-sm">
                        {selectableSets.map((documentSet) => {
                          const selectedIndex = values.document_sets.indexOf(
                            documentSet.id
                          );
                          const isSelected = selectedIndex !== -1;

                          return (
                            <DocumentSetCard
                              key={documentSet.id}
                              documentSet={documentSet}
                              isSelected={isSelected}
                              onSelectToggle={(selected) => {
                                if (selected) arrayHelpers.push(documentSet.id);
                                else arrayHelpers.remove(selectedIndex);
                              }}
                            />
                          );
                        })}
                      </div>
                    )}

                    {viewUnselectableSets && unselectableSets.length > 0 && (
                      <div className="mt-4">
                        <p className="text-sm text-text-dark/80">
                          {t("slackChannelConfigs.autoSyncDocs")}
                        </p>
                        <div className="mb-3 mt-2 flex gap-2 flex-wrap text-sm">
                          {unselectableSets.map((documentSet) => (
                            <DocumentSetCard
                              key={documentSet.id}
                              documentSet={documentSet}
                              disabled
                              disabledTooltip={t("slackChannelConfigs.disabledDocSetTooltip")}
                              isSelected={false}
                            />
                          ))}
                        </div>
                      </div>
                    )}
                    <ErrorMessage
                      className="text-red-500 text-sm mt-1"
                      name="document_sets"
                      component="div"
                    />
                  </>
                )}
              />
            </div>
          )}
        {values.knowledge_source === "assistant" && (
          <div className="mt-4">
            <SubLabel>
              <>
                {t("slackChannelConfigs.selectSearchAgentLabel")}
                {syncEnabledAgents.length > 0 && (
                  <>
                    <br />
                    <span className="text-sm text-text-dark/80">
                      {t("slackChannelConfigs.syncConnectorsNote")}{" "}
                      <button
                        type="button"
                        onClick={() =>
                          setViewSyncEnabledAgents(
                            (viewSyncEnabledAgents) => !viewSyncEnabledAgents
                          )
                        }
                        className="text-sm text-action-link-05"
                      >
                        {viewSyncEnabledAgents
                          ? t("slackChannelConfigs.hideUnselectable")
                          : t("slackChannelConfigs.viewAll")}
                        {t("slackChannelConfigs.agentsLabel")}
                      </button>
                    </span>
                  </>
                )}
              </>
            </SubLabel>

            <SelectorFormField
              name="persona_id"
              options={availableAgents.map((persona) => ({
                name: persona.name,
                value: persona.id,
              }))}
            />
            {viewSyncEnabledAgents && syncEnabledAgents.length > 0 && (
              <div className="mt-4">
                <p className="text-sm text-text-dark/80">
                  {t("slackChannelConfigs.unselectableAgents")}
                </p>
                <div className="mb-3 mt-2 flex gap-2 flex-wrap text-sm">
                  {syncEnabledAgents.map((persona: MinimalPersonaSnapshot) => (
                    <button
                      type="button"
                      onClick={() =>
                        router.push(`/app/agents/edit/${persona.id}` as Route)
                      }
                      key={persona.id}
                      className="p-2 bg-background-100 cursor-pointer rounded-md flex items-center gap-2"
                    >
                      <AgentAvatar agent={persona} size={16} />
                      {persona.name}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
        {values.knowledge_source === "non_search_agent" && (
          <div className="mt-4">
            <SubLabel>
              <>
                {t("slackChannelConfigs.selectNonSearchAgentLabel")}
                {syncEnabledAgents.length > 0 && (
                  <>
                    <br />
                    <span className="text-sm text-text-dark/80">
                      {t("slackChannelConfigs.syncConnectorsNote")}{" "}
                      <button
                        type="button"
                        onClick={() =>
                          setViewSyncEnabledAgents(
                            (viewSyncEnabledAgents) => !viewSyncEnabledAgents
                          )
                        }
                        className="text-sm text-action-link-05"
                      >
                        {viewSyncEnabledAgents
                          ? t("slackChannelConfigs.hideUnselectable")
                          : t("slackChannelConfigs.viewAll")}
                        {t("slackChannelConfigs.agentsLabel")}
                      </button>
                    </span>
                  </>
                )}
              </>
            </SubLabel>

            <SelectorFormField
              name="persona_id"
              options={nonSearchAgents.map((persona) => ({
                name: persona.name,
                value: persona.id,
              }))}
            />
          </div>
        )}
      </div>
      <Separator className="my-4" />
      <Accordion type="multiple" className="gap-y-2 w-full">
        {values.knowledge_source !== "non_search_agent" && (
          <AccordionItem value="search-options">
            <AccordionTrigger className="text-text">
              {t("slackChannelConfigs.searchConfig")}
            </AccordionTrigger>
            <AccordionContent>
              <div className="space-y-4 pb-3">
                <div className="w-64">
                  <SelectorFormField
                    name="response_type"
                    label={t("slackChannelConfigs.answerType")}
                    tooltip={t("slackChannelConfigs.answerTypeTooltip")}
                    options={[
                      { name: t("slackChannelConfigs.answerTypeStandard"), value: "citations" },
                      { name: t("slackChannelConfigs.answerTypeDetailed"), value: "quotes" },
                    ]}
                  />
                </div>
                <CheckboxField
                  name="answer_validity_check_enabled"
                  label={t("slackChannelConfigs.onlyRespondIfCitations")}
                  tooltip={t("slackChannelConfigs.onlyRespondIfCitationsTooltip")}
                />
              </div>
            </AccordionContent>
          </AccordionItem>
        )}

        <AccordionItem className="mt-4" value="general-options">
          <AccordionTrigger>{t("slackChannelConfigs.generalConfig")}</AccordionTrigger>
          <AccordionContent className="overflow-visible">
            <div className="space-y-4">
              <CheckboxField
                name="show_continue_in_web_ui"
                label={t("slackChannelConfigs.showContinueInWebUI")}
                tooltip={t("slackChannelConfigs.showContinueInWebUITooltip")}
              />

              <CheckboxField
                name="still_need_help_enabled"
                onChange={(checked: boolean) => {
                  setFieldValue("still_need_help_enabled", checked);
                  if (!checked) {
                    setFieldValue("follow_up_tags", []);
                  }
                }}
                label={t("slackChannelConfigs.stillNeedHelp")}
                tooltip={t("slackChannelConfigs.stillNeedHelpTooltip")}
              />
              {values.still_need_help_enabled && (
                <CollapsibleSection prompt={t("slackChannelConfigs.configureStillNeedHelp")}>
                  <TextArrayField
                    name="follow_up_tags"
                    label={t("slackChannelConfigs.optionalUsersGroupsTag")}
                    values={values}
                    subtext={
                      <div>
                        {t("slackChannelConfigs.usersGroupsTagSubtext")}
                      </div>
                    }
                    placeholder={t("slackChannelConfigs.userEmailGroupPlaceholder")}
                  />
                </CollapsibleSection>
              )}

              <CheckboxField
                name="questionmark_prefilter_enabled"
                label={t("slackChannelConfigs.onlyRespondToQuestions")}
                tooltip={t("slackChannelConfigs.onlyRespondToQuestionsTooltip")}
              />
              <CheckboxField
                name="respond_tag_only"
                label={t("slackChannelConfigs.respondTagOnly")}
                tooltip={t("slackChannelConfigs.respondTagOnlyTooltip")}
              />
              <CheckboxField
                name="respond_to_bots"
                label={t("slackChannelConfigs.respondToBots")}
                tooltip={t("slackChannelConfigs.respondToBotsTooltip")}
              />
              <CheckboxField
                name="is_ephemeral"
                label={t("slackChannelConfigs.respondEphemeral")}
                tooltip={t("slackChannelConfigs.respondEphemeralTooltip")}
              />

              <TextArrayField
                name="respond_member_group_list"
                label={t("slackChannelConfigs.optionalRespondCertainUsers")}
                subtext={t("slackChannelConfigs.respondCertainUsersSubtext")}
                values={values}
                placeholder={t("slackChannelConfigs.userEmailGroupPlaceholder")}
              />

              <StandardAnswerCategoryDropdownField
                standardAnswerCategoryResponse={standardAnswerCategoryResponse}
                categories={values.standard_answer_categories}
                setCategories={(categories: any) =>
                  setFieldValue("standard_answer_categories", categories)
                }
              />
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>

      <div className="flex mt-8 gap-x-2 w-full justify-end">
        {shouldShowPrivacyAlert && (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger asChild>
                <div className="flex hover:bg-background-150 cursor-pointer p-2 rounded-lg items-center">
                  <AlertCircle className="h-5 w-5 text-alert" />
                </div>
              </TooltipTrigger>
              <TooltipContent side="top" className="bg-background p-4 w-80">
                <Label className="text-text mb-2 font-semibold">
                  {t("slackChannelConfigs.privacyAlert")}
                </Label>
                <p className="text-sm text-text-darker mb-4">
                  {t("slackChannelConfigs.privacyAlertDesc")}
                </p>
                <div className="space-y-2">
                  <h4 className="text-sm text-text font-medium">
                    {t("slackChannelConfigs.relevantConnectors")}
                  </h4>
                  <div className="max-h-40 overflow-y-auto border-t border-text-subtle flex-col gap-y-2">
                    {memoizedPrivateConnectors.map((ccpairinfo: any) => (
                      <Link
                        key={ccpairinfo.id}
                        href={`/admin/connector/${ccpairinfo.id}`}
                        className="flex items-center p-2 rounded-md hover:bg-background-100 transition-colors"
                      >
                        <div className="mr-2">
                          <SourceIcon
                            iconSize={16}
                            sourceType={ccpairinfo.source}
                          />
                        </div>
                        <span className="text-sm text-text-darker font-medium">
                          {ccpairinfo.name}
                        </span>
                      </Link>
                    ))}
                  </div>
                </div>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        )}
        <Button type="submit">{isUpdate ? t("slackChannelConfigs.update") : t("slackChannelConfigs.create")}</Button>
        <Button secondary onClick={() => router.back()}>
          {t("slackChannelConfigs.cancel")}
        </Button>
      </div>
    </>
  );
}
