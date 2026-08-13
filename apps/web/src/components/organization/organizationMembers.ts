import type { OrganizationMember } from "@/components/organization/organizationTypes";

export function organizationMemberName(member: OrganizationMember): string {
  const name = [member.user?.first_name, member.user?.last_name]
    .filter(Boolean)
    .join(" ");
  return name || member.user?.username || member.user?.email || member.user_id;
}

export function organizationMemberDetail(member: OrganizationMember): string {
  return member.user?.email || member.user?.username || member.role_in_org;
}

export function organizationMemberInitials(member: OrganizationMember): string {
  return organizationMemberName(member)
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toLocaleUpperCase();
}
