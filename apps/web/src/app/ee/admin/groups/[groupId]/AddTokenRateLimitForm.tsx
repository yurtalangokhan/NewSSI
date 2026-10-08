import { systemEndpoints } from "@/lib/api/domains/system/endpoints";

import { toast } from "@/hooks/useToast";
import CreateRateLimitModal from "../../../../admin/token-rate-limits/CreateRateLimitModal";
import { Scope } from "@/lib/api/domains/system/token-rate-limit-types";
import { insertGroupTokenRateLimit } from "@/lib/api/domains/system/api";
import { mutate } from "swr";
import { useTranslation } from "react-i18next";

interface AddMemberFormProps {
  isOpen: boolean;
  setIsOpen: (isOpen: boolean) => void;
  userGroupId: number;
}

const handleCreateGroupTokenRateLimit = async (
  period_hours: number,
  token_budget: number,
  group_id: number = -1
) => {
  const tokenRateLimitArgs = {
    enabled: true,
    token_budget: token_budget,
    period_hours: period_hours,
  };
  return await insertGroupTokenRateLimit(tokenRateLimitArgs, group_id);
};

export const AddTokenRateLimitForm: React.FC<AddMemberFormProps> = ({
  isOpen,
  setIsOpen,
  userGroupId,
}) => {
  const { t } = useTranslation();
  const handleSubmit = (
    _: Scope,
    period_hours: number,
    token_budget: number,
    group_id: number = -1
  ) => {
    handleCreateGroupTokenRateLimit(period_hours, token_budget, group_id)
      .then(() => {
        setIsOpen(false);
        toast.success(t("admin.tokenRateLimits.createdSuccess"));
        mutate(systemEndpoints.groupTokenRateLimits(userGroupId).browserPath);
      })
      .catch((error) => {
        toast.error(error.message);
      });
  };

  return (
    <CreateRateLimitModal
      isOpen={isOpen}
      setIsOpen={setIsOpen}
      onSubmit={handleSubmit}
      forSpecificScope={Scope.USER_GROUP}
      forSpecificUserGroup={userGroupId}
    />
  );
};
