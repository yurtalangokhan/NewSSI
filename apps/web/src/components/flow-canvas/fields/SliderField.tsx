"use client";

import * as SliderPrimitive from "@radix-ui/react-slider";
import Text from "@/refresh-components/texts/Text";
import type { FieldRendererProps } from "./types";

/**
 * Slider field supporting both integer ranges and fine-grained float ranges
 * (e.g. LLM temperature 0.0 - 2.0 with step 0.01).
 */
export function SliderField({
  value,
  onChange,
  disabled,
  field,
}: FieldRendererProps) {
  const min = field.min ?? 0;
  const max = field.max ?? (min <= 1 ? 1 : 100);
  const range = max - min;
  const step = field.step ?? (range <= 10 ? 0.1 : 1);
  const current = typeof value === "number" ? value : min;

  // Decimal places to display
  const decimals = step < 0.1 ? 2 : step < 1 ? 1 : 0;

  return (
    <div className="flex w-full items-center gap-3">
      <SliderPrimitive.Root
        className="relative flex h-4 w-full touch-none select-none items-center"
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        value={[current]}
        onValueChange={([v]) => {
          if (v !== undefined) {
            const rounded = Number(v.toFixed(decimals));
            onChange(rounded);
          }
        }}
      >
        <SliderPrimitive.Track className="relative h-1 w-full grow overflow-hidden rounded-full bg-muted">
          <SliderPrimitive.Range className="absolute h-full bg-theme-primary-05" />
        </SliderPrimitive.Track>
        <SliderPrimitive.Thumb
          className="block h-3.5 w-3.5 rounded-full border border-canvas-border bg-canvas-panel focus:outline-none disabled:opacity-50"
          aria-label={field.display_name}
        />
      </SliderPrimitive.Root>
      <Text mainUiMuted className="w-10 shrink-0 text-right font-mono text-xs">
        {current.toFixed(decimals)}
      </Text>
    </div>
  );
}
