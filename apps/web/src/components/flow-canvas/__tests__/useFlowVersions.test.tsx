/**
 * Tests for useFlowVersions — version list, publish, rollback. Mocks
 * `global.fetch` directly (unlike useFlowDraft's DI-based tests) since
 * this hook's own error-shape mapping (409/400 → distinct result kinds)
 * is exactly what's under test, and that mapping only exists at the
 * fetch-response level.
 *
 * Brief: .tmp/flow-canvas-task-28-brief.md
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { envelopeResponse } from "@tests/setup/responseModel";
import { useFlowVersions, type FlowVersion } from "../hooks/useFlowVersions";

// SWR keeps a module-level cache shared across every renderHook call in
// this file — reusing one definition id across tests would let an
// earlier test's cached response leak into a later one (a real gotcha,
// found by an actual failure, not anticipated). Each test gets its own
// id so its SWR key never collides with another test's cache entry.
let definitionIdCounter = 0;
function nextDefinitionId(): string {
  definitionIdCounter += 1;
  return `11111111-1111-1111-1111-${String(definitionIdCounter).padStart(
    12,
    "0"
  )}`;
}

function version(
  definitionId: string,
  overrides: Partial<FlowVersion> = {}
): FlowVersion {
  return {
    id: "v1",
    definition_id: definitionId,
    version_no: 1,
    status: "draft",
    created_by: "user-1",
    published_by: null,
    created_at: "2026-08-01T00:00:00Z",
    published_at: null,
    notes: null,
    ...overrides,
  };
}

/** A ResponseModel reply, as agent-service answers every flow endpoint. */
function jsonResponse(status: number, data: unknown) {
  return envelopeResponse(data, { status });
}

function failureResponse(
  status: number,
  code: string,
  message: string,
  details: Record<string, unknown> = {}
) {
  return new Response(
    JSON.stringify({
      statusCode: status,
      message,
      data: null,
      error: { code, message, details },
    }),
    { status, headers: { "Content-Type": "application/json" } }
  );
}

beforeEach(() => {
  global.fetch = jest.fn() as unknown as typeof fetch;
});

describe("useFlowVersions — 28.11, no published version shows draft state", () => {
  it("publishedVersion is null when nothing is published yet", async () => {
    const definitionId = nextDefinitionId();
    (global.fetch as jest.Mock).mockResolvedValue(
      jsonResponse(200, [version(definitionId, { status: "draft" })])
    );

    const { result } = renderHook(() => useFlowVersions(definitionId));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.publishedVersion).toBeNull();
    expect(result.current.versions).toHaveLength(1);
  });

  it("exposes the published version when one exists", async () => {
    const definitionId = nextDefinitionId();
    (global.fetch as jest.Mock).mockResolvedValue(
      jsonResponse(200, [
        version(definitionId, { status: "published", version_no: 3 }),
      ])
    );

    const { result } = renderHook(() => useFlowVersions(definitionId));

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.publishedVersion?.version_no).toBe(3);
  });
});

describe("useFlowVersions — 28.6, publish 409 offers reload, preserves the draft", () => {
  it("sends an idempotency key with the publish request", async () => {
    const definitionId = nextDefinitionId();
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce(jsonResponse(200, []))
      .mockResolvedValueOnce(jsonResponse(200, version(definitionId)));

    const { result } = renderHook(() => useFlowVersions(definitionId));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.publish();
    });

    const publishCall = (global.fetch as jest.Mock).mock.calls.find((call) =>
      String(call[0]).endsWith("/flow/publish")
    );
    expect(publishCall).toBeDefined();
    expect(
      new Headers(publishCall?.[1]?.headers).get("Idempotency-Key")
    ).toBeTruthy();
  });

  it("returns a conflict result instead of throwing or silently retrying", async () => {
    const definitionId = nextDefinitionId();
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce(jsonResponse(200, [])) // initial versions GET
      .mockResolvedValueOnce(
        failureResponse(
          409,
          "flow.version_conflict",
          "Version 4 was already published."
        )
      );

    const { result } = renderHook(() => useFlowVersions(definitionId));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let publishResult:
      | Awaited<ReturnType<typeof result.current.publish>>
      | undefined;
    await act(async () => {
      publishResult = await result.current.publish(3);
    });

    expect(publishResult).toEqual({
      kind: "conflict",
      message: "Version 4 was already published.",
    });
    // Exactly one publish attempt — no automatic retry.
    expect(
      (global.fetch as jest.Mock).mock.calls.filter((c) =>
        String(c[0]).includes("/flow/publish")
      )
    ).toHaveLength(1);
  });
});

describe("useFlowVersions — 28.7, publish 400 maps issues with their node_id", () => {
  it("returns the raw issues, each still carrying its node_id", async () => {
    const definitionId = nextDefinitionId();
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce(jsonResponse(200, []))
      .mockResolvedValueOnce(
        failureResponse(400, "flow.validation_failed", "Flow is invalid", {
          errors: [
            {
              code: "FLOW_UNKNOWN_COMPONENT",
              message: "Unknown component",
              node_id: "n1",
              edge_id: null,
            },
          ],
        })
      );

    const { result } = renderHook(() => useFlowVersions(definitionId));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    let publishResult:
      | Awaited<ReturnType<typeof result.current.publish>>
      | undefined;
    await act(async () => {
      publishResult = await result.current.publish();
    });

    expect(publishResult).toEqual({
      kind: "invalid",
      errors: [
        {
          code: "FLOW_UNKNOWN_COMPONENT",
          message: "Unknown component",
          node_id: "n1",
          edge_id: null,
        },
      ],
    });
  });
});

describe("useFlowVersions — 28.10, rollback refreshes the version list", () => {
  it("sends an idempotency key with the rollback request", async () => {
    const definitionId = nextDefinitionId();
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce(
        jsonResponse(200, [version(definitionId, { status: "published" })])
      )
      .mockResolvedValueOnce(
        jsonResponse(200, version(definitionId, { status: "published" }))
      )
      .mockResolvedValueOnce(
        jsonResponse(200, [version(definitionId, { status: "published" })])
      );

    const { result } = renderHook(() => useFlowVersions(definitionId));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.rollback(1);
    });

    const rollbackCall = (global.fetch as jest.Mock).mock.calls.find((call) =>
      String(call[0]).endsWith("/flow/rollback")
    );
    expect(rollbackCall).toBeDefined();
    expect(
      new Headers(rollbackCall?.[1]?.headers).get("Idempotency-Key")
    ).toBeTruthy();
  });

  it("re-fetches versions after a successful rollback", async () => {
    const definitionId = nextDefinitionId();
    (global.fetch as jest.Mock)
      .mockResolvedValueOnce(
        jsonResponse(200, [
          version(definitionId, { status: "published", version_no: 2 }),
        ])
      )
      .mockResolvedValueOnce(
        jsonResponse(
          200,
          version(definitionId, { status: "published", version_no: 3 })
        )
      )
      .mockResolvedValueOnce(
        jsonResponse(200, [
          version(definitionId, { status: "published", version_no: 3 }),
        ])
      );

    const { result } = renderHook(() => useFlowVersions(definitionId));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.publishedVersion?.version_no).toBe(2);

    await act(async () => {
      await result.current.rollback(1);
    });

    await waitFor(() =>
      expect(result.current.publishedVersion?.version_no).toBe(3)
    );
  });
});
