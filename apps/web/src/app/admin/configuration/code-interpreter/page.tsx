"use client";

import { notFound } from "next/navigation";
import CodeInterpreterPage from "@/refresh-pages/admin/CodeInterpreterPage";

export default function Page() {
  notFound();

  return <CodeInterpreterPage />;
}
