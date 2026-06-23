import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
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
import { InviteUserButton } from "@/components/admin/users/buttons/InviteUserButton";
import { ErrorCallout } from "@/components/ErrorCallout";
import { FetchError } from "@/lib/fetcher";
import Text from "@/refresh-components/texts/Text";

const USERS_PER_PAGE = 10;

interface Props {
  users: InvitedUserSnapshot[];
  mutate: () => void;
  error: FetchError | null;
  isLoading: boolean;
  q: string;
}

function InvitedUserTable({ users, mutate, error, isLoading, q }: Props) {
  const { t } = useTranslation();
  const [currentPageNum, setCurrentPageNum] = useState<number>(1);

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
        {t("admin.users.invitedEmptyState")}
      </Text>
    );
  }

  if (isLoading) {
    return <ThreeDotsLoader />;
  }

  if (error) {
    return (
      <ErrorCallout
        errorTitle={t("admin.users.errorLoadingUsers")}
        errorMsg={error?.info?.detail}
      />
    );
  }

  return (
    <>
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
                    <InviteUserButton
                      user={user}
                      invited={true}
                      mutate={mutate}
                    />
                  </div>
                </TableCell>
              </TableRow>
            ))
          ) : (
            <TableRow>
              <TableCell colSpan={2} className="h-24 text-center">
                <Text mainUiMuted text03>
                  {t("admin.users.noUsersFoundMatching", { query: q })}
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

export default InvitedUserTable;
