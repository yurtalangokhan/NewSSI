"use client";

import { useState } from "react";
import FileTile from "@/refresh-components/tiles/FileTile";
import ButtonTile from "@/refresh-components/tiles/ButtonTile";
import { SvgAddLines, SvgFilter, SvgMenu, SvgPlusCircle } from "@opal/icons";
import MemoriesModal from "@/refresh-components/modals/MemoriesModal";
import LineItem from "@/refresh-components/buttons/LineItem";
import IconButton from "@/refresh-components/buttons/IconButton";
import { useCreateModal } from "@/refresh-components/contexts/ModalContext";
import { MemoryItem } from "@/lib/types";
import { useTranslation } from "react-i18next";

interface MemoriesProps {
  memories: MemoryItem[];
  onSaveMemories: (memories: MemoryItem[]) => Promise<boolean>;
  onDeleteMemory?: (id: string) => Promise<boolean>;
}

export default function Memories({ memories, onSaveMemories, onDeleteMemory }: MemoriesProps) {
  const { t } = useTranslation("common", { keyPrefix: "memories" });
  const memoriesModal = useCreateModal();
  const [targetMemoryId, setTargetMemoryId] = useState<string | null>(null);

  return (
    <>
      {memories.length === 0 ? (
        <LineItem
          skeleton
          description={t("addMemoryDescription")}
          onClick={() => {
            setTargetMemoryId(null);
            memoriesModal.toggle(true);
          }}
          rightChildren={
            <IconButton
              internal
              icon={SvgPlusCircle}
              onClick={() => {
                setTargetMemoryId(null);
                memoriesModal.toggle(true);
              }}
            />
          }
        />
      ) : (
        <div className="self-stretch flex flex-row items-center justify-between gap-2">
          <div className="flex flex-row items-center gap-2">
            {memories.slice(0, 2).map((memory, index) => (
              <FileTile
                key={memory.id}
                description={memory.content}
                onOpen={() => {
                  setTargetMemoryId(memory.id);
                  memoriesModal.toggle(true);
                }}
              />
            ))}
          </div>
          <ButtonTile
            title={t("viewAddButton")}
            description={t("allMemoriesLabel")}
            icon={SvgAddLines}
            onClick={() => {
              setTargetMemoryId(null);
              memoriesModal.toggle(true);
            }}
          />
        </div>
      )}

      <memoriesModal.Provider>
        <MemoriesModal
          memories={memories}
          onSaveMemories={onSaveMemories}
          onDeleteMemory={onDeleteMemory}
          initialTargetMemoryId={targetMemoryId}
        />
      </memoriesModal.Provider>
    </>
  );
}

