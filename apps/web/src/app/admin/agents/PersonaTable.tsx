"use client";

import { useTranslation } from "react-i18next";
import Text from "@/refresh-components/texts/Text";
import { Persona } from "./interfaces";
import { useRouter } from "next/navigation";
import Checkbox from "@/refresh-components/inputs/Checkbox";
import { toast } from "@/hooks/useToast";
import { useState, useMemo, useEffect } from "react";
import { UniqueIdentifier } from "@dnd-kit/core";
import { DraggableTable } from "@/components/table/DraggableTable";
import {
  deletePersona,
  personaComparator,
  togglePersonaFeatured,
  togglePersonaVisibility,
} from "./lib";
import { FiEdit2 } from "react-icons/fi";
import { useUser } from "@/providers/UserProvider";
import { Button as OpalButton } from "@opal/components";
import ConfirmationModalLayout from "@/refresh-components/layouts/ConfirmationModalLayout";
import Button from "@/refresh-components/buttons/Button";
import { SvgAlertCircle, SvgTrash } from "@opal/icons";
import type { Route } from "next";
import { authenticatedFetch } from "@/lib/fetcher";

function PersonaTypeDisplay({ persona }: { persona: Persona }) {
  const { t } = useTranslation();

  if (persona.builtin_persona) {
    return <Text as="p">{t("admin.agents.typeBuiltIn")}</Text>;
  }

  if (persona.featured) {
    return <Text as="p">{t("admin.agents.typeFeatured")}</Text>;
  }

  if (persona.is_public) {
    return <Text as="p">{t("admin.agents.typePublic")}</Text>;
  }

  if (persona.groups.length > 0 || persona.users.length > 0) {
    return <Text as="p">{t("admin.agents.typeShared")}</Text>;
  }

  return (
    <Text as="p">
      {t("admin.agents.typePersonal")}{" "}
      {persona.owner && <>({persona.owner.email})</>}
    </Text>
  );
}

export function PersonasTable({
  personas,
  refreshPersonas,
  currentPage,
  pageSize,
}: {
  personas: Persona[];
  refreshPersonas: () => void;
  currentPage: number;
  pageSize: number;
}) {
  const { t } = useTranslation();
  const router = useRouter();
  const { refreshUser, isAdmin } = useUser();

  const editablePersonas = useMemo(() => {
    return personas.filter((p) => !p.builtin_persona);
  }, [personas]);

  const editablePersonaIds = useMemo(() => {
    return new Set(editablePersonas.map((p) => p.id.toString()));
  }, [editablePersonas]);

  const [finalPersonas, setFinalPersonas] = useState<Persona[]>([]);
  const [deleteModalOpen, setDeleteModalOpen] = useState(false);
  const [personaToDelete, setPersonaToDelete] = useState<Persona | null>(null);
  const [defaultModalOpen, setDefaultModalOpen] = useState(false);
  const [personaToToggleDefault, setPersonaToToggleDefault] =
    useState<Persona | null>(null);

  useEffect(() => {
    const editable = editablePersonas.sort(personaComparator);
    const nonEditable = personas
      .filter((p) => !editablePersonaIds.has(p.id.toString()))
      .sort(personaComparator);
    setFinalPersonas([...editable, ...nonEditable]);
  }, [editablePersonas, personas, editablePersonaIds]);

  const updatePersonaOrder = async (orderedPersonaIds: UniqueIdentifier[]) => {
    const reorderedPersonas = orderedPersonaIds.map(
      (id) => personas.find((persona) => persona.id.toString() === id)!
    );

    setFinalPersonas(reorderedPersonas);

    // Calculate display_priority based on current page.
    // Page 1 (items 0-9): priorities 0-9
    // Page 2 (items 10-19): priorities 10-19, etc.
    const pageStartIndex = (currentPage - 1) * pageSize;
    const displayPriorityMap = new Map<UniqueIdentifier, number>();
    orderedPersonaIds.forEach((personaId, ind) => {
      displayPriorityMap.set(personaId, pageStartIndex + ind);
    });

    const response = await authenticatedFetch(
      "/api/admin/agents/display-priorities",
      {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          display_priority_map: Object.fromEntries(displayPriorityMap),
        }),
      }
    );

    if (!response.ok) {
      toast.error(
        t("admin.agents.errorUpdateOrder", { msg: await response.text() })
      );
      setFinalPersonas(personas);
      await refreshPersonas();
      return;
    }

    await refreshPersonas();
    await refreshUser();
  };

  const openDeleteModal = (persona: Persona) => {
    setPersonaToDelete(persona);
    setDeleteModalOpen(true);
  };

  const closeDeleteModal = () => {
    setDeleteModalOpen(false);
    setPersonaToDelete(null);
  };

  const handleDeletePersona = async () => {
    if (personaToDelete) {
      const response = await deletePersona(personaToDelete.id);
      if (response.ok) {
        refreshPersonas();
        closeDeleteModal();
      } else {
        toast.error(
          t("admin.agents.errorDeletePersona", { msg: await response.text() })
        );
      }
    }
  };

  const openDefaultModal = (persona: Persona) => {
    setPersonaToToggleDefault(persona);
    setDefaultModalOpen(true);
  };

  const closeDefaultModal = () => {
    setDefaultModalOpen(false);
    setPersonaToToggleDefault(null);
  };

  const handleToggleDefault = async () => {
    if (personaToToggleDefault) {
      const response = await togglePersonaFeatured(
        personaToToggleDefault.id,
        personaToToggleDefault.featured
      );
      if (response.ok) {
        refreshPersonas();
        closeDefaultModal();
      } else {
        toast.error(`Failed to update persona - ${await response.text()}`);
      }
    }
  };

  return (
    <div>
      {deleteModalOpen && personaToDelete && (
        <ConfirmationModalLayout
          icon={SvgAlertCircle}
          title={t("admin.agents.deleteModalTitle")}
          onClose={closeDeleteModal}
          submit={
            <Button onClick={handleDeletePersona}>
              {t("admin.agents.deleteModalConfirm")}
            </Button>
          }
        >
          {t("admin.agents.deleteModalBody", { name: personaToDelete.name })}
        </ConfirmationModalLayout>
      )}
      {defaultModalOpen &&
        personaToToggleDefault &&
        (() => {
          const isDefault = personaToToggleDefault.featured;

          const title = isDefault
            ? t("admin.agents.removeFeaturedTitle")
            : t("admin.agents.setFeaturedTitle");
          const buttonText = isDefault
            ? t("admin.agents.removeFeaturedButton")
            : t("admin.agents.setFeaturedButton");
          const text = isDefault
            ? t("admin.agents.removeFeaturedBody", {
                name: personaToToggleDefault.name,
              })
            : t("admin.agents.setFeaturedBody", {
                name: personaToToggleDefault.name,
              });
          const additionalText = isDefault
            ? t("admin.agents.removeFeaturedDescription", {
                name: personaToToggleDefault.name,
              })
            : t("admin.agents.setFeaturedDescription", {
                name: personaToToggleDefault.name,
              });

          return (
            <ConfirmationModalLayout
              icon={SvgAlertCircle}
              title={title}
              onClose={closeDefaultModal}
              submit={
                <Button onClick={handleToggleDefault}>{buttonText}</Button>
              }
            >
              <div className="flex flex-col gap-2">
                <Text as="p">{text}</Text>
                <Text as="p" text03>
                  {additionalText}
                </Text>
              </div>
            </ConfirmationModalLayout>
          );
        })()}

      <DraggableTable
        headers={[
          t("admin.agents.tableName"),
          t("admin.agents.tableDescription"),
          t("admin.agents.tableType"),
          t("admin.agents.tableFeatured"),
          t("admin.agents.tableVisible"),
          t("admin.agents.tableDelete"),
        ]}
        isAdmin={isAdmin}
        rows={finalPersonas.map((persona) => {
          const isEditable = editablePersonas.includes(persona);
          return {
            id: persona.id.toString(),
            cells: [
              <div key="name" className="flex">
                {!persona.builtin_persona && (
                  <FiEdit2
                    className="mr-1 my-auto cursor-pointer"
                    onClick={() =>
                      router.push(
                        `/app/agents/edit/${
                          persona.id
                        }?u=${Date.now()}` as Route
                      )
                    }
                  />
                )}
                <Text
                  as="p"
                  className="text font-medium whitespace-normal break-none"
                >
                  {persona.name}
                </Text>
              </div>,
              <Text
                as="p"
                key="description"
                className="whitespace-normal break-all max-w-2xl"
              >
                {persona.description}
              </Text>,
              <PersonaTypeDisplay key={persona.id} persona={persona} />,
              <div
                key="featured"
                onClick={() => {
                  openDefaultModal(persona);
                }}
                className={`
                  px-1 py-0.5 rounded flex hover:bg-accent-background-hovered cursor-pointer select-none w-fit items-center gap-2
                  `}
              >
                <div className="my-auto flex-none w-22">
                  {!persona.featured ? (
                    <div className="text-error">
                      {t("admin.agents.notFeatured")}
                    </div>
                  ) : (
                    t("admin.agents.featured")
                  )}
                </div>
                <Checkbox checked={persona.featured} />
              </div>,
              <div
                key="is_visible"
                onClick={async () => {
                  const response = await togglePersonaVisibility(
                    persona.id,
                    persona.is_visible
                  );
                  if (response.ok) {
                    refreshPersonas();
                  } else {
                    toast.error(
                      `Failed to update persona - ${await response.text()}`
                    );
                  }
                }}
                className={`
                  px-1 py-0.5 rounded flex hover:bg-accent-background-hovered cursor-pointer select-none w-fit items-center gap-2
                  `}
              >
                <div className="my-auto w-fit">
                  {!persona.is_visible ? (
                    <div className="text-error">{t("admin.agents.hidden")}</div>
                  ) : (
                    t("admin.agents.visible")
                  )}
                </div>
                <Checkbox checked={persona.is_visible} />
              </div>,
              <div key="edit" className="flex">
                <div className="mr-auto my-auto">
                  {!persona.builtin_persona && isEditable ? (
                    <OpalButton
                      icon={SvgTrash}
                      prominence="tertiary"
                      onClick={() => openDeleteModal(persona)}
                    />
                  ) : (
                    <Text as="p">-</Text>
                  )}
                </div>
              </div>,
            ],
            staticModifiers: [[1, "lg:w-[250px] xl:w-[400px] 2xl:w-[550px]"]],
          };
        })}
        setRows={updatePersonaOrder}
      />
    </div>
  );
}
