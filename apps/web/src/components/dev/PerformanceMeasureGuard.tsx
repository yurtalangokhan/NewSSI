"use client";

import { useEffect } from "react";

export default function PerformanceMeasureGuard() {
  useEffect(() => {
    if (process.env.NODE_ENV !== "development") {
      return;
    }

    if (typeof window === "undefined" || !window.performance) {
      return;
    }

    const perf = window.performance as Performance & {
      __measureGuardPatched?: boolean;
    };

    if (perf.__measureGuardPatched) {
      return;
    }

    const originalMeasure = perf.measure.bind(perf);

    perf.measure = ((...args: Parameters<Performance["measure"]>) => {
      try {
        return originalMeasure(...args);
      } catch (error) {
        const message = error instanceof Error ? error.message : "";
        if (/negative time stamp/i.test(message)) {
          return;
        }
        throw error;
      }
    }) as Performance["measure"];

    perf.__measureGuardPatched = true;
  }, []);

  return null;
}
