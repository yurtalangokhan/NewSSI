"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { DeleteButton } from "@/components/DeleteButton";
import Button from "@/refresh-components/buttons/Button";
import Switch from "@/refresh-components/inputs/Switch";
import { SvgEdit, SvgServer } from "@opal/icons";
import EmptyMessage from "@/refresh-components/EmptyMessage";
import { DiscordGuildConfig } from "@/app/admin/discord-bot/types";
import {
  deleteGuildConfig,
  updateGuildConfig,
} from "@/app/admin/discord-bot/lib";
import { toast } from "@/hooks/useToast";
import { ConfirmEntityModal } from "@/components/modals/ConfirmEntityModal";
import { useTranslation } from "react-i18next";

interface Props {
  guilds: DiscordGuildConfig[];
  onRefresh: () => void;
}

export function DiscordGuildsTable({ guilds, onRefresh }: Props) {
  const { t } = useTranslation();
  const router = useRouter();
  const [guildToDelete, setGuildToDelete] = useState<DiscordGuildConfig | null>(
    null
  );
  const [updatingGuildIds, setUpdatingGuildIds] = useState<Set<number>>(
    new Set()
  );

  const handleDelete = async (guildId: number) => {
    try {
      await deleteGuildConfig(guildId);
      onRefresh();
      toast.success(t("admin.discord.serverConfigDeleted"));
    } catch (err) {
      toast.error(
        err instanceof Error
          ? err.message
          : t("admin.discord.deleteServerConfigFailed")
      );
    } finally {
      setGuildToDelete(null);
    }
  };

  const handleToggleEnabled = async (guild: DiscordGuildConfig) => {
    if (!guild.guild_id) {
      toast.error(t("admin.discord.enableBeforeRegistrationError"));
      return;
    }

    setUpdatingGuildIds((prev) => new Set(prev).add(guild.id));
    try {
      await updateGuildConfig(guild.id, {
        enabled: !guild.enabled,
        default_persona_id: guild.default_persona_id,
      });
      onRefresh();
      toast.success(`Server ${!guild.enabled ? "enabled" : "disabled"}`);
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Failed to update server"
      );
    } finally {
      setUpdatingGuildIds((prev) => {
        const next = new Set(prev);
        next.delete(guild.id);
        return next;
      });
    }
  };

  if (guilds.length === 0) {
    return (
      <EmptyMessage
        icon={SvgServer}
        title={t("admin.discord.emptyTitle")}
        description={t("admin.discord.emptyDescription")}
      />
    );
  }

  return (
    <>
      {guildToDelete && (
        <ConfirmEntityModal
          danger
          entityType={t("admin.discord.serverEntityType")}
          entityName={
            guildToDelete.guild_name ||
            t("admin.discord.serverFallbackName", { id: guildToDelete.id })
          }
          onClose={() => setGuildToDelete(null)}
          onSubmit={() => handleDelete(guildToDelete.id)}
          additionalDetails={t("admin.discord.deleteServerAdditionalDetails")}
        />
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{t("admin.discord.tableServer")}</TableHead>
            <TableHead>{t("admin.discord.tableStatus")}</TableHead>
            <TableHead>{t("admin.discord.tableRegistered")}</TableHead>
            <TableHead>{t("admin.discord.tableEnabled")}</TableHead>
            <TableHead>{t("admin.discord.tableActions")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {guilds.map((guild) => (
            <TableRow key={guild.id}>
              <TableCell>
                <Button
                  internal
                  disabled={!guild.guild_id}
                  onClick={() => router.push(`/admin/discord-bot/${guild.id}`)}
                  leftIcon={SvgEdit}
                >
                  {guild.guild_name || `Server #${guild.id}`}
                </Button>
              </TableCell>
              <TableCell>
                {guild.guild_id ? (
                  <Badge variant="success">
                    {t("admin.discord.statusRegistered")}
                  </Badge>
                ) : (
                  <Badge variant="secondary">
                    {t("admin.discord.statusPending")}
                  </Badge>
                )}
              </TableCell>
              <TableCell>
                {guild.registered_at
                  ? new Date(guild.registered_at).toLocaleDateString()
                  : "-"}
              </TableCell>
              <TableCell>
                {!guild.guild_id ? (
                  "-"
                ) : (
                  <Switch
                    checked={guild.enabled}
                    onCheckedChange={() => handleToggleEnabled(guild)}
                    disabled={updatingGuildIds.has(guild.id)}
                  />
                )}
              </TableCell>
              <TableCell>
                <DeleteButton onClick={() => setGuildToDelete(guild)} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </>
  );
}
