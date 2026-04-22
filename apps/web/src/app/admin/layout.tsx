import Layout from "@/components/admin/Layout";
import { ProjectsProvider } from "@/providers/ProjectsContext";

export interface AdminLayoutProps {
  children: React.ReactNode;
}

export default async function AdminLayout({ children }: AdminLayoutProps) {
  return <ProjectsProvider>{await Layout({ children })}</ProjectsProvider>;
}
