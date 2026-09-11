"use client";

import {
  Table,
  TableHead,
  TableRow,
  TableBody,
  TableCell,
} from "@/components/ui/table";
import Title from "@/components/ui/title";
import { DeleteButton } from "@/components/DeleteButton";
import { deleteTokenRateLimit, updateTokenRateLimit } from "./lib";
import TableSkeleton from "@/refresh-components/skeletons/TableSkeleton";
import { TokenRateLimitDisplay } from "./types";
import { errorHandlingFetcher } from "@/lib/fetcher";
import useSWR, { mutate } from "swr";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import { TableHeader } from "@/components/ui/table";
import Text from "@/refresh-components/texts/Text";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

type TokenRateLimitTableArgs = {
  tokenRateLimits: TokenRateLimitDisplay[];
  title?: string;
  description?: string;
  fetchUrl: string;
  hideHeading?: boolean;
  isAdmin: boolean;
};

export const TokenRateLimitTable = ({
  tokenRateLimits,
  title,
  description,
  fetchUrl,
  hideHeading,
  isAdmin,
}: TokenRateLimitTableArgs) => {
  const { t } = useTranslation();
  const shouldRenderGroupName = () =>
    tokenRateLimits.length > 0 &&
    tokenRateLimits[0] !== undefined &&
    tokenRateLimits[0].group_name !== undefined;

  const handleEnabledChange = (id: number) => {
    const tokenRateLimit = tokenRateLimits.find(
      (tokenRateLimit) => tokenRateLimit.token_id === id
    );

    if (!tokenRateLimit) {
      return;
    }

    updateTokenRateLimit(id, {
      token_budget: tokenRateLimit.token_budget,
      period_hours: tokenRateLimit.period_hours,
      enabled: !tokenRateLimit.enabled,
    }).then(() => {
      mutate(fetchUrl);
    });
  };

  const handleDelete = (id: number) =>
    deleteTokenRateLimit(id).then(() => {
      mutate(fetchUrl);
    });

  if (tokenRateLimits.length === 0) {
    return (
      <div className="w-full">
        {!hideHeading && title && <Title>{title}</Title>}
        {!hideHeading && description && (
          <Text as="p" className="text-sm my-2">
            {description}
          </Text>
        )}
        <Text as="p" className={cn("text-sm", `${!hideHeading && "my-8"}`)}>
          {t("admin.tokenRateLimits.noLimitsSet")}
        </Text>
      </div>
    );
  }

  return (
    <div className="w-full">
      {!hideHeading && title && <Title>{title}</Title>}
      {!hideHeading && description && (
        <Text as="p" className="text-sm my-2">
          {description}
        </Text>
      )}
      <Table
        className={`overflow-visible ${
          !hideHeading && "my-8"
        } [&_td]:text-center [&_th]:text-center`}
      >
        <TableHeader>
          <TableRow>
            <TableHead>{t("admin.tokenRateLimits.enabledHeader")}</TableHead>
            {shouldRenderGroupName() && (
              <TableHead>
                {t("admin.tokenRateLimits.groupNameHeader")}
              </TableHead>
            )}
            <TableHead>{t("admin.tokenRateLimits.timeWindowLabel")}</TableHead>
            <TableHead>{t("admin.tokenRateLimits.tokenBudgetLabel")}</TableHead>
            {isAdmin && (
              <TableHead>{t("admin.tokenRateLimits.deleteHeader")}</TableHead>
            )}
          </TableRow>
        </TableHeader>
        <TableBody>
          {tokenRateLimits.map((tokenRateLimit) => {
            return (
              <TableRow key={tokenRateLimit.token_id}>
                <TableCell>
                  <div className="flex justify-center">
                    <div
                      onClick={
                        isAdmin
                          ? () => handleEnabledChange(tokenRateLimit.token_id)
                          : undefined
                      }
                      className={`px-1 py-0.5 rounded select-none w-24 ${
                        isAdmin
                          ? "hover:bg-accent-background cursor-pointer"
                          : "opacity-50"
                      }`}
                    >
                      <div className="flex items-center justify-center">
                        <Checkbox
                          checked={tokenRateLimit.enabled}
                          onCheckedChange={
                            isAdmin
                              ? () =>
                                  handleEnabledChange(tokenRateLimit.token_id)
                              : undefined
                          }
                        />
                        <Text as="p" className="ml-2">
                          {tokenRateLimit.enabled
                            ? t("admin.tokenRateLimits.enabledStatus")
                            : t("admin.tokenRateLimits.disabledStatus")}
                        </Text>
                      </div>
                    </div>
                  </div>
                </TableCell>
                {shouldRenderGroupName() && (
                  <TableCell className="font-bold text-text-darker">
                    {tokenRateLimit.group_name}
                  </TableCell>
                )}
                <TableCell>
                  {t("admin.tokenRateLimits.periodHours", {
                    count: tokenRateLimit.period_hours,
                  })}
                </TableCell>
                <TableCell>
                  {t("admin.tokenRateLimits.thousandTokens", {
                    count: tokenRateLimit.token_budget,
                  })}
                </TableCell>
                {isAdmin && (
                  <TableCell>
                    <div className="flex justify-center">
                      <DeleteButton
                        onClick={() => handleDelete(tokenRateLimit.token_id)}
                      />
                    </div>
                  </TableCell>
                )}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
};

export const GenericTokenRateLimitTable = ({
  fetchUrl,
  title,
  description,
  hideHeading,
  responseMapper,
  isAdmin = true,
}: {
  fetchUrl: string;
  title?: string;
  description?: string;
  hideHeading?: boolean;
  responseMapper?: (data: any) => TokenRateLimitDisplay[];
  isAdmin?: boolean;
}) => {
  const { t } = useTranslation();
  const { data, isLoading, error } = useSWR<TokenRateLimitDisplay[]>(
    fetchUrl,
    errorHandlingFetcher
  );

  if (isLoading) {
    return (
      <TableSkeleton
        rowCount={4}
        columns={[
          { type: "checkbox", width: "w-8", headerWidth: "w-16" },
          { type: "text", width: "w-32", headerWidth: "w-24" },
          { type: "text", width: "w-24", headerWidth: "w-20" },
          { type: "badge", width: "w-20", headerWidth: "w-20" },
          { type: "actions", width: "w-12", headerWidth: "w-12" },
        ]}
      />
    );
  }

  if (!isLoading && error) {
    return (
      <Text as="p" className="text-sm">
        {t("admin.tokenRateLimits.failedToLoad")}
      </Text>
    );
  }

  let processedData = data;
  if (responseMapper) {
    processedData = responseMapper(data);
  }

  return (
    <TokenRateLimitTable
      tokenRateLimits={processedData ?? []}
      fetchUrl={fetchUrl}
      title={title}
      description={description}
      hideHeading={hideHeading}
      isAdmin={isAdmin}
    />
  );
};
