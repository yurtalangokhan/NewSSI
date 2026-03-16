"use client";

import { type LucideIcon } from "lucide-react";
import { usePathname } from "next/navigation";

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  SidebarGroup,
  SidebarGroupLabel,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from "@/components/ui/sidebar";
import { ChevronRight } from "lucide-react";
import NextLink from "next/link";
import { cn } from "@/lib/utils";

export interface NavItem {
  title: string;
  url: string;
  icon?: LucideIcon;
  items?: { title: string; url: string }[];
}

export function NavMain({ items }: { items: NavItem[] }) {
  const pathname = usePathname();

  return (
    <SidebarGroup>
      <SidebarGroupLabel>Platform</SidebarGroupLabel>
      <SidebarMenu>
        {items.map((item, index) => {
          const hasSubItems = item.items && item.items.length > 0;
          const isActive =
            pathname === item.url ||
            (hasSubItems &&
              item.items!.some((sub) => pathname === sub.url));

          if (hasSubItems) {
            return (
              <Collapsible
                key={`${item.title}-${index}`}
                asChild
                defaultOpen={isActive}
                className="group/collapsible"
              >
                <SidebarMenuItem>
                  <CollapsibleTrigger asChild>
                    <SidebarMenuButton
                      tooltip={item.title}
                      className={cn(
                        isActive &&
                          "bg-sidebar-accent text-sidebar-accent-foreground",
                      )}
                    >
                      {item.icon && <item.icon />}
                      <span>{item.title}</span>
                      <ChevronRight className="ml-auto transition-transform duration-200 group-data-[state=open]/collapsible:rotate-90" />
                    </SidebarMenuButton>
                  </CollapsibleTrigger>
                  <CollapsibleContent>
                    <SidebarMenuSub>
                      {/* Main link */}
                      <SidebarMenuSubItem>
                        <SidebarMenuSubButton
                          asChild
                          isActive={pathname === item.url}
                        >
                          <NextLink href={item.url}>
                            <span>{item.title}</span>
                          </NextLink>
                        </SidebarMenuSubButton>
                      </SidebarMenuSubItem>
                      {/* Sub-items */}
                      {item.items!.map((sub) => (
                        <SidebarMenuSubItem key={sub.url}>
                          <SidebarMenuSubButton
                            asChild
                            isActive={pathname === sub.url}
                          >
                            <NextLink href={sub.url}>
                              <span>{sub.title}</span>
                            </NextLink>
                          </SidebarMenuSubButton>
                        </SidebarMenuSubItem>
                      ))}
                    </SidebarMenuSub>
                  </CollapsibleContent>
                </SidebarMenuItem>
              </Collapsible>
            );
          }

          return (
            <NextLink href={item.url} key={`${item.title}-${index}`}>
              <SidebarMenuItem
                className={cn(
                  pathname === item.url &&
                    "bg-sidebar-accent text-sidebar-accent-foreground",
                )}
              >
                <SidebarMenuButton tooltip={item.title}>
                  {item.icon && <item.icon />}
                  <span>{item.title}</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </NextLink>
          );
        })}
      </SidebarMenu>
    </SidebarGroup>
  );
}
