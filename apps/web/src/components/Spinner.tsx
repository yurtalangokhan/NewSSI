import React from "react";

export const Spinner = () => {
  return (
    <div
      className="flex items-center justify-center p-4"
      role="status"
      aria-label="Loading..."
    >
      <div className="h-6 w-6 rounded-full border-2 border-border-01 border-t-text-04 animate-spin" />
    </div>
  );
};
