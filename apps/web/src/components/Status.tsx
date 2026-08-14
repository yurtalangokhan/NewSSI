"use client";

import { ValidStatuses } from "@/lib/types";
import { Badge } from "@/components/ui/badge";
import {
  FiAlertTriangle,
  FiCheckCircle,
  FiClock,
  FiMinus,
  FiPauseCircle,
} from "react-icons/fi";
import {
  ConnectorCredentialPairStatus,
  PermissionSyncStatusEnum,
} from "@/app/admin/connector/[ccPairId]/types";
import SimpleTooltip from "@/refresh-components/SimpleTooltip";
import { useTranslation } from "react-i18next";

export function IndexAttemptStatus({
  status,
  errorMsg,
}: {
  status: ValidStatuses | null;
  errorMsg?: string | null;
}) {
  const { t } = useTranslation("common", { keyPrefix: "admin" });
  let badge;

  if (status === "failed") {
    const icon = (
      <Badge variant="destructive" icon={FiAlertTriangle}>
        {t("status.failed")}
      </Badge>
    );
    if (errorMsg) {
      badge = (
        <SimpleTooltip tooltip={errorMsg}>
          <div className="cursor-pointer">{icon}</div>
        </SimpleTooltip>
      );
    } else {
      badge = icon;
    }
  } else if (status === "completed_with_errors") {
    badge = (
      <Badge variant="secondary" icon={FiAlertTriangle}>
        {t("status.completedWithErrors")}
      </Badge>
    );
  } else if (status === "success") {
    badge = (
      <Badge variant="success" icon={FiCheckCircle}>
        {t("status.succeeded")}
      </Badge>
    );
  } else if (status === "in_progress") {
    badge = (
      <Badge variant="in_progress" icon={FiClock}>
        {t("status.inProgress")}
      </Badge>
    );
  } else if (status === "not_started") {
    badge = (
      <Badge variant="not_started" icon={FiClock}>
        {t("status.scheduled")}
      </Badge>
    );
  } else if (status === "canceled") {
    badge = (
      <Badge variant="canceled" icon={FiClock}>
        {t("status.canceled")}
      </Badge>
    );
  } else if (status === "invalid") {
    badge = (
      <Badge variant="invalid" icon={FiAlertTriangle}>
        {t("status.invalid")}
      </Badge>
    );
  } else {
    badge = (
      <Badge variant="outline" icon={FiMinus}>
        {t("status.none")}
      </Badge>
    );
  }

  return <div>{badge}</div>;
}

export function PermissionSyncStatus({
  status,
  errorMsg,
}: {
  status: PermissionSyncStatusEnum | null;
  errorMsg?: string | null;
}) {
  const { t } = useTranslation("common", { keyPrefix: "admin" });
  let badge;

  if (status === PermissionSyncStatusEnum.FAILED) {
    const icon = (
      <Badge variant="destructive" icon={FiAlertTriangle}>
        {t("status.failed")}
      </Badge>
    );
    if (errorMsg) {
      badge = (
        <SimpleTooltip tooltip={errorMsg} side="bottom">
          <div className="cursor-pointer">{icon}</div>
        </SimpleTooltip>
      );
    } else {
      badge = icon;
    }
  } else if (status === PermissionSyncStatusEnum.COMPLETED_WITH_ERRORS) {
    badge = (
      <Badge variant="secondary" icon={FiAlertTriangle}>
        {t("status.completedWithErrors")}
      </Badge>
    );
  } else if (status === PermissionSyncStatusEnum.SUCCESS) {
    badge = (
      <Badge variant="success" icon={FiCheckCircle}>
        {t("status.succeeded")}
      </Badge>
    );
  } else if (status === PermissionSyncStatusEnum.IN_PROGRESS) {
    badge = (
      <Badge variant="in_progress" icon={FiClock}>
        {t("status.inProgress")}
      </Badge>
    );
  } else if (status === PermissionSyncStatusEnum.NOT_STARTED) {
    badge = (
      <Badge variant="not_started" icon={FiClock}>
        {t("status.scheduled")}
      </Badge>
    );
  } else {
    badge = (
      <Badge variant="secondary" icon={FiClock}>
        {t("status.notStarted")}
      </Badge>
    );
  }

  return <div>{badge}</div>;
}

export function CCPairStatus({
  ccPairStatus,
  inRepeatedErrorState,
  lastIndexAttemptStatus,
  size = "md",
}: {
  ccPairStatus: ConnectorCredentialPairStatus;
  inRepeatedErrorState: boolean;
  lastIndexAttemptStatus: ValidStatuses | undefined | null;
  size?: "xs" | "sm" | "md" | "lg";
}) {
  const { t } = useTranslation("common", { keyPrefix: "admin" });
  let badge;

  if (ccPairStatus == ConnectorCredentialPairStatus.DELETING) {
    badge = (
      <Badge variant="destructive" icon={FiAlertTriangle}>
        {t("status.deleting")}
      </Badge>
    );
  } else if (ccPairStatus == ConnectorCredentialPairStatus.PAUSED) {
    badge = (
      <Badge variant="paused" icon={FiPauseCircle}>
        {t("status.paused")}
      </Badge>
    );
  } else if (inRepeatedErrorState) {
    badge = (
      <Badge variant="destructive" icon={FiAlertTriangle}>
        {t("status.error")}
      </Badge>
    );
  } else if (ccPairStatus == ConnectorCredentialPairStatus.SCHEDULED) {
    badge = (
      <Badge variant="not_started" icon={FiClock}>
        {t("status.scheduled")}
      </Badge>
    );
  } else if (ccPairStatus == ConnectorCredentialPairStatus.INITIAL_INDEXING) {
    badge = (
      <Badge variant="in_progress" icon={FiClock}>
        {t("status.initialIndexing")}
      </Badge>
    );
  } else if (ccPairStatus == ConnectorCredentialPairStatus.INVALID) {
    badge = (
      <Badge tooltip={t("status.invalidTooltip")} circle variant="invalid">
        {t("status.invalid")}
      </Badge>
    );
  } else {
    if (lastIndexAttemptStatus && lastIndexAttemptStatus === "in_progress") {
      badge = (
        <Badge variant="in_progress" icon={FiClock}>
          {t("status.indexing")}
        </Badge>
      );
    } else if (
      lastIndexAttemptStatus &&
      lastIndexAttemptStatus === "canceled"
    ) {
      badge = (
        <Badge variant="canceled" icon={FiClock}>
          {t("status.canceled")}
        </Badge>
      );
    } else {
      badge = (
        <Badge variant="success" icon={FiCheckCircle}>
          {t("status.indexed")}
        </Badge>
      );
    }
  }

  return <div>{badge}</div>;
}
