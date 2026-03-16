"use client";

import * as React from "react";
import { Wrench, Bot, MessageCircle, Brain } from "lucide-react";

import { NavMain, type NavItem } from "./nav-main";
import { NavUser } from "./nav-user";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarRail,
} from "@/components/ui/sidebar";
import { SiteHeader } from "./sidebar-header";

const data: { navMain: NavItem[] } = {
  navMain: [
    {
      title: "Chat",
      url: "/",
      icon: MessageCircle,
    },
    {
      title: "Agents",
      url: "/agents",
      icon: Bot,
    },
    {
      title: "Tools",
      url: "/tools",
      icon: Wrench,
    },
    {
      title: "RAG",
      url: "/rag",
      icon: Brain,
      items: [
        {
          title: "Graph RAG",
          url: "/rag/graph",
        },
      ],
    },
  ],
};

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  return (
    <Sidebar
      collapsible="icon"
      {...props}
    >
      <SiteHeader />
      <SidebarContent>
        <NavMain items={data.navMain} />
      </SidebarContent>
      <SidebarFooter>
        <NavUser />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  );
}
