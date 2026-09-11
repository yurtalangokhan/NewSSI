"use client";

import React, { useState, useEffect } from "react";
import "./loading.css";
import { cn } from "@/lib/utils";
import { useTranslation } from "react-i18next";

interface LoadingAnimationProps {
  text?: string;
  size?: "text-sm" | "text-md";
}

export const LoadingAnimation: React.FC<LoadingAnimationProps> = ({
  text,
  size,
}) => {
  const { t } = useTranslation("common", { keyPrefix: "app" });
  const [dots, setDots] = useState("...");

  useEffect(() => {
    const interval = setInterval(() => {
      setDots((prevDots) => {
        switch (prevDots) {
          case ".":
            return "..";
          case "..":
            return "...";
          case "...":
            return ".";
          default:
            return "...";
        }
      });
    }, 500);

    return () => clearInterval(interval);
  }, []);

  return (
    <span className="loading-animation inline-flex">
      <span className={cn("mx-auto inline-flex", size)}>
        {text === undefined ? t("loading.thinking") : text}
        <span className="dots">{dots}</span>
      </span>
    </span>
  );
};

export const ThreeDotsLoader = () => {
  return (
    <div
      className="flex my-auto items-center justify-center py-4"
      role="status"
      aria-label="Loading..."
    >
      <div className="flex items-center gap-1.5">
        <div className="h-2.5 w-2.5 rounded-full bg-background-tint-04 animate-pulse" />
        <div className="h-2.5 w-2.5 rounded-full bg-background-tint-04 animate-pulse [animation-delay:200ms]" />
        <div className="h-2.5 w-2.5 rounded-full bg-background-tint-04 animate-pulse [animation-delay:400ms]" />
      </div>
    </div>
  );
};
