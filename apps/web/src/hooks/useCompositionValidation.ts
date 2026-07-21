/**
 * Hook for real-time composition validation.
 * Validates agent composition before saving.
 */

import { useEffect, useState, useCallback, useRef } from "react";

interface CompositionValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  depth: number;
}

interface UseCompositionValidationOptions {
  debounceMs?: number;
  enabled?: boolean;
}

export function useCompositionValidation(
  options: UseCompositionValidationOptions = {}
) {
  const { debounceMs = 500, enabled = true } = options;

  const [result, setResult] = useState<CompositionValidationResult>({
    valid: true,
    errors: [],
    warnings: [],
    depth: 0,
  });
  const [isValidating, setIsValidating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  const validate = useCallback(
    async (
      agentId: string | null,
      graphSchema: string,
      subAgentIds: string[]
    ) => {
      if (!enabled) return;

      // Clear existing timer
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }

      // Set new timer for debounced validation
      debounceTimerRef.current = setTimeout(async () => {
        try {
          setIsValidating(true);
          setError(null);

          const response = await fetch("/api/agent-definitions/validate-composition", {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              agent_id: agentId,
              graph_schema: graphSchema,
              sub_agent_ids: subAgentIds,
            }),
          });

          if (!response.ok) {
            throw new Error(`Validation failed: ${response.statusText}`);
          }

          const data = await response.json();
          setResult(data);
        } catch (err) {
          const errorMsg = err instanceof Error ? err.message : "Validation error";
          setError(errorMsg);
          setResult({
            valid: false,
            errors: [errorMsg],
            warnings: [],
            depth: 0,
          });
        } finally {
          setIsValidating(false);
        }
      }, debounceMs);
    },
    [debounceMs, enabled]
  );

  // Cleanup timer on unmount
  useEffect(() => {
    return () => {
      if (debounceTimerRef.current) {
        clearTimeout(debounceTimerRef.current);
      }
    };
  }, []);

  return {
    validate,
    result,
    isValidating,
    error,
    isValid: result.valid,
    depth: result.depth,
    errors: result.errors,
    warnings: result.warnings,
  };
}
