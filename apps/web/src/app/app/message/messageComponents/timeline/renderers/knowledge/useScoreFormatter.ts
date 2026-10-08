import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { DEFAULT_LANGUAGE } from "@/i18n/locales";

const DEFAULT_FRACTION_DIGITS = 2;

/**
 * Score formatting in the reader's locale (0,89 in Turkish). Similarity
 * scores read well with two decimals; rank-fusion scores are tiny and need
 * more to stay distinguishable.
 */
export function useScoreFormatter(
  fractionDigits: number = DEFAULT_FRACTION_DIGITS
): (score: number) => string {
  const { i18n } = useTranslation();
  const language = i18n?.language || DEFAULT_LANGUAGE;
  return useMemo(() => {
    const format = new Intl.NumberFormat(language, {
      minimumFractionDigits: fractionDigits,
      maximumFractionDigits: fractionDigits,
    });
    return (score: number) => format.format(score);
  }, [language, fractionDigits]);
}
