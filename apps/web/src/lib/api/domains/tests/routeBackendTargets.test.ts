import { accessEndpoints } from "@/lib/api/domains/access/endpoints";
import { datasourcesEndpoints } from "@/lib/api/domains/datasources/endpoints";
import { chatEndpoints } from "@/lib/api/domains/chat/endpoints";
import { sessionEndpoints } from "@/lib/api/domains/session/endpoints";
import { projectsEndpoints } from "@/lib/api/domains/projects/endpoints";

describe("static route backend targets", () => {
  it("keeps authentication routes on the user service", () => {
    expect(sessionEndpoints.login.backend).toEqual({
      service: "user",
      path: "/api/v1/auth/login",
    });
    expect(sessionEndpoints.externalLogin.backend).toEqual({
      service: "user",
      path: "/api/v1/auth/external/login",
    });
    expect(sessionEndpoints.refresh.backend).toEqual({
      service: "user",
      path: "/api/v1/auth/refresh",
    });
    expect(sessionEndpoints.register.backend).toEqual({
      service: "user",
      path: "/api/v1/auth/register",
    });
    expect(sessionEndpoints.getCurrentUser.backend).toEqual({
      service: "user",
      path: "/api/v1/auth/me",
    });

    expect(sessionEndpoints.authType.backend).toEqual({
      service: "user",
      path: "/api/v1/auth/type",
    });
    expect(accessEndpoints.getCurrentUserPermissions.backend).toEqual({
      service: "user",
      path: "/api/v1/users/me/permissions",
    });
    expect(sessionEndpoints.logout.backend).toEqual({
      service: "user",
      path: "/api/v1/auth/logout",
    });
    expect(sessionEndpoints.samlLogout.backend).toEqual({
      service: "user",
      path: "/api/v1/auth/saml/logout",
    });
    expect(sessionEndpoints.samlAuthorize.backend).toEqual({
      service: "agent",
      path: "/api/v1/auth/saml/authorize",
    });
  });

  it("preserves route-specific chat parameter encoding", () => {
    expect(chatEndpoints.deleteSession("a/b").backend).toEqual({
      service: "agent",
      path: "/api/v1/chat/sessions/a/b",
    });
    expect(chatEndpoints.getSession("a/b").backend).toEqual({
      service: "agent",
      path: "/api/v1/chat/sessions/a/b",
    });
    expect(chatEndpoints.file("a/b").backend).toEqual({
      service: "agent",
      path: "/api/v1/chat/file/a%2Fb",
    });
    expect(chatEndpoints.fileText("a/b").backend).toEqual({
      service: "agent",
      path: "/api/v1/chat/file/a%2Fb/text",
    });
  });

  it("keeps datasource and project targets on their original services", () => {
    expect(datasourcesEndpoints.getKnowledgeSelector().backend).toEqual({
      service: "rag",
      path: "/api/v1/datasources/knowledge-selector",
    });
    expect(projectsEndpoints.listProjects.backend).toEqual({
      service: "agent",
      path: "/api/v1/user/projects",
    });
    expect(projectsEndpoints.getSessionFiles("a/b").backend).toEqual({
      service: "agent",
      path: "/api/v1/user/projects/session/a%2Fb/files",
    });
    expect(projectsEndpoints.getSessionTokenCount("a/b").backend).toEqual({
      service: "agent",
      path: "/api/v1/user/projects/session/a%2Fb/token-count",
    });
    expect(projectsEndpoints.recentFiles.backend).toEqual({
      service: "agent",
      path: "/api/v1/user/files/recent",
    });
  });
});
