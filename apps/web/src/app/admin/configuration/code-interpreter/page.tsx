import { notFound } from "next/navigation";
"use client";

import CodeInterpreterPage from "@/refresh-pages/admin/CodeInterpreterPage";

export default function Page() {
  notFound();

  return <CodeInterpreterPage />;
}
