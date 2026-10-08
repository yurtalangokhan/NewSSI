import { render, screen, setupUser } from "@tests/setup/test-utils";
import { GraphEvidenceBody } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/GraphEvidenceBody";
import { parseKnowledgeEvidence } from "@/lib/api/domains/chat/knowledge-evidence-types";
import { graphEvidence } from "@/app/app/message/messageComponents/timeline/renderers/knowledge/__tests__/fixtures";

jest.mock(
  "react-i18next",
  () => jest.requireActual("@tests/setup/mocks/turkishI18nMock").turkishI18nMock
);
jest.mock("@/refresh-components/knowledge-graph/KnowledgeForceGraph", () =>
  jest.requireActual(
    "@/refresh-components/knowledge-graph/__fixtures__/knowledgeForceGraphStub"
  )
);

const evidence = parseKnowledgeEvidence(graphEvidence)!;

describe("GraphEvidenceBody list view", () => {
  it.each([
    [false, "340px"],
    [true, "260px"],
  ])("bounds the list like the drawing (compact=%s)", async (compact, max) => {
    const user = setupUser();
    render(<GraphEvidenceBody evidence={evidence} compact={compact} />);

    await user.click(screen.getByRole("button", { name: "Liste" }));

    const list = screen.getByRole("list", { name: "Tüm ilişkiler" });
    expect(list.parentElement).toHaveStyle({ maxHeight: max });
  });
});
