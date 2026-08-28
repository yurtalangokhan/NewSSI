import React from "react";
import Text from "@/refresh-components/texts/Text";

interface InfoItemProps {
  title: string;
  value: string;
}

export function InfoItem({ title, value }: InfoItemProps) {
  return (
    <div className="bg-muted p-4 rounded-lg">
      <Text as="p" className="text-sm font-medium text-muted-foreground mb-1">
        {title}
      </Text>
      <Text
        as="p"
        className="text-lg font-semibold text-foreground dark:text-neutral-100"
      >
        {value}
      </Text>
    </div>
  );
}
