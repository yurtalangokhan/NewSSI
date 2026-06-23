import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { toast } from "@/hooks/useToast";
import {
  Table,
  TableHead,
  TableRow,
  TableBody,
  TableCell,
} from "@/components/ui/table";
import CenteredPageSelector from "@/components/admin/users/CenteredPageSelector";
import { ThreeDotsLoader } from "@/components/Loading";
import { InvitedUserSnapshot } from "@/lib/types";
import { TableHeader } from "@/components/ui/table";
import Button from "@/refresh-components/buttons/Button";
import { ErrorCallout } from "@/components/ErrorCallout";
import { FetchError } from "@/lib/fetcher";
import { ConfirmEntityModal } from "@/components/modals/ConfirmEntityModal";
import { SvgCheck } from "@opal/icons";
import Text from "@/refresh-components/texts/Text";
const USERS_PER_PAGE = 10;

interface Props {
  users: InvitedUserSnapshot[];
  mutate: () => void;
  error: FetchError | null;
  isLoading: boolean;
  q: string;
}

function PendingUsersTable({ users, mutate, error, isLoading, q }: Props) {
  const { t } = useTranslation();
  const [currentPageNum, setCurrentPageNum] = useState<number>(1);
  const [userToApprove, setUserToApprove] = useState<string | null>(null);

  useEffect(() => {
    setCurrentPageNum(1);
  }, [q]);

  const filteredUsers = useMemo(() => {
    const normalizedQuery = q.trim().toLowerCase();
    if (!normalizedQuery) return users;
    return users.filter((user) =>
      user.email.toLowerCase().includes(normalizedQuery)
    );
  }, [q, users]);

  const totalPages = Math.ceil(filteredUsers.length / USERS_PER_PAGE);
  const currentPageOfUsers = filteredUsers.slice(
    (currentPageNum - 1) * USERS_PER_PAGE,
    currentPageNum * USERS_PER_PAGE
  );

  if (!users.length) {
    return (
      <Text as="p" mainUiMuted text03>
        {t("admin.users.pendingEmptyState")}
      </Text>
    );
  }

  if (isLoading) {
    return <ThreeDotsLoader />;
  }

  if (error) {
    return (
      <ErrorCallout
        errorTitle={t("admin.users.errorLoadingPendingUsers")}
        errorMsg={error?.info?.detail}
      />
    );
  }

  const handleAcceptRequest = async (email: string) => {
    const normalizedEmail = email.toLowerCase();
    try {
      await fetch("/api/tenants/users/invite/approve", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email: normalizedEmail }),
      });
      mutate();
      setUserToApprove(null);
    } catch (error) {
      toast.error(t("admin.users.approveFailedError"));
    }
  };

  return (
    <>
      {userToApprove && (
        <ConfirmEntityModal
          entityType={t("admin.users.joinRequestEntity")}
          entityName={userToApprove}
          onClose={() => setUserToApprove(null)}
          onSubmit={() => handleAcceptRequest(userToApprove)}
          actionButtonText={t("admin.users.approveButton")}
          action={t("admin.users.approveAction")}
          additionalDetails={t("admin.users.approveDetails", {
            user: userToApprove,
          })}
          removeConfirmationText
        />
      )}
      <Table className="overflow-visible">
        <TableHeader>
          <TableRow>
            <TableHead>{t("admin.users.emailHeader")}</TableHead>
            <TableHead>
              <div className="flex justify-end">
                {t("admin.users.actionsHeader")}
              </div>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {currentPageOfUsers.length ? (
            currentPageOfUsers.map((user) => (
              <TableRow key={user.email}>
                <TableCell>
                  <Text mainUiBody>{user.email}</Text>
                </TableCell>
                <TableCell>
                  <div className="flex justify-end">
                    <Button
                      secondary
                      onClick={() => setUserToApprove(user.email.toLowerCase())}
                      leftIcon={SvgCheck}
                    >
                      {t("admin.users.acceptJoinRequest")}
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={2} className="h-24 text-center">
                <Text mainUiMuted text03>
                  {t("admin.users.noPendingUsersFoundMatching", { query: q })}
                </Text>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
      {totalPages > 1 ? (
        <CenteredPageSelector
          currentPage={currentPageNum}
          totalPages={totalPages}
          onPageChange={setCurrentPageNum}
        />
      ) : null}
    </>
  );
}

export default PendingUsersTable;
