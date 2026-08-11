import type { OrganizationNode } from "@/components/organization/organizationTypes";

function searchLocale(language: string) {
  return language.toLowerCase().startsWith("tr") ? "tr-TR" : "en-US";
}

export function normalizeOrganizationSearch(value: string, language: string) {
  return value.trim().toLocaleLowerCase(searchLocale(language));
}

export function organizationMatchesSearch(
  organization: Pick<OrganizationNode, "name">,
  query: string,
  language: string
) {
  const normalizedQuery = normalizeOrganizationSearch(query, language);
  return (
    normalizedQuery.length > 0 &&
    normalizeOrganizationSearch(organization.name, language).includes(
      normalizedQuery
    )
  );
}

export function flattenOrganizations(organizations: OrganizationNode[]) {
  const flattened: OrganizationNode[] = [];

  function visit(organization: OrganizationNode) {
    flattened.push(organization);
    (organization.children ?? []).forEach(visit);
  }

  organizations.forEach(visit);
  return flattened;
}

export function getOrganizationMatches(
  organizations: OrganizationNode[],
  query: string,
  language: string
) {
  if (!normalizeOrganizationSearch(query, language)) return [];
  return flattenOrganizations(organizations).filter((organization) =>
    organizationMatchesSearch(organization, query, language)
  );
}
