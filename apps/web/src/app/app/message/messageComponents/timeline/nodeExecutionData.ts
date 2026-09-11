import { Packet, PacketType } from "@/app/app/services/streamingModels";
import type {
  CanvasEdge,
  CanvasNode,
} from "@/components/flow-canvas/types/flow";
import type {
  NodeExecutionData,
  NodeToolExecution,
  ToolInvocationDetail,
  NodeIterationData,
} from "@/components/flow-canvas/types/execution";
import {
  StageDefinition,
  getToolNameToNodeId,
  getToolNodeIdToAgentNodeId,
  isConfigNode,
  prettifyNodeId,
  getStringValue,
  MIN_STAGE_DURATION_MS,
} from "./graphStageParsing";

export type {
  NodeExecutionData,
  NodeToolExecution,
  ToolInvocationDetail,
  NodeIterationData,
};

interface InternalStageIteration {
  iteration: number;
  stageKey: string;
  nodeId: string;
  label: string;
  status: "running" | "done" | "error";
  startedAt: number | null;
  endedAt: number | null;
  durationMs: number | null;
  thinking: string;
  thinkingStartedAt: number | null;
  thinkingEndedAt: number | null;
  output: string;
  toolsMap: Map<string, NodeToolExecution>;
}

/**
 * Extracts per-node execution details (thinking, tool calls with arguments & outputs,
 * and stage output) from raw streaming/persisted packets for display in GraphStageCanvas.
 */
export function buildNodeExecutionData(
  packets: Packet[],
  stageDefinitions: StageDefinition[],
  flowNodes: CanvasNode[] = [],
  flowEdges: CanvasEdge[] = []
): Record<string, NodeExecutionData> {
  if (!packets || packets.length === 0) return {};

  const toolNameToNodeId = getToolNameToNodeId(flowNodes);
  const toolNodeIdToAgentNodeId = getToolNodeIdToAgentNodeId(
    flowEdges,
    flowNodes
  );

  // Normalize lookup keys: map lowercase identifiers to canvas node IDs
  const nodeIdByName = new Map<string, string>();
  for (const node of flowNodes) {
    nodeIdByName.set(node.id.toLowerCase(), node.id);
    const nodeType = (node.data?.type || node.type || "").toLowerCase();
    if (nodeType) nodeIdByName.set(nodeType, node.id);

    const stageVal =
      (node.data?.values?.stage_name as string) ||
      (node.data?.values?.name as string) ||
      (node.data?.values?.title as string);
    if (typeof stageVal === "string" && stageVal.trim()) {
      nodeIdByName.set(stageVal.trim().toLowerCase(), node.id);
    }
  }

  // Also index stage definitions
  for (const def of stageDefinitions) {
    if (def.matchName) {
      const existing = nodeIdByName.get(def.matchName.toLowerCase());
      if (existing) {
        nodeIdByName.set(def.label.toLowerCase(), existing);
      }
    }
  }

  // Find canvas nodeId for any stage identifier
  const resolveCanvasNodeId = (rawName: string | undefined): string | null => {
    if (!rawName) return null;
    const clean = rawName.trim().toLowerCase();
    if (nodeIdByName.has(clean)) return nodeIdByName.get(clean)!;

    // Check without prefix
    const prettified = prettifyNodeId(rawName).toLowerCase();
    if (nodeIdByName.has(prettified)) return nodeIdByName.get(prettified)!;

    // Fallback: direct match
    const foundNode = flowNodes.find(
      (n) =>
        n.id.toLowerCase() === clean ||
        (n.data?.type || "").toLowerCase() === clean ||
        prettifyNodeId(n.id).toLowerCase() === clean
    );
    return foundNode ? foundNode.id : rawName;
  };

  // Iterations tracked per canvas node
  const nodeIterationsMap = new Map<string, InternalStageIteration[]>();
  // Active stage tracking for non-placement packets
  let activeNodeId: string | null = null;
  let activeIteration: InternalStageIteration | null = null;

  const getOrCreateIteration = (
    nodeId: string,
    iterationNum: number,
    stageKey: string,
    label?: string
  ): InternalStageIteration => {
    let list = nodeIterationsMap.get(nodeId);
    if (!list) {
      list = [];
      nodeIterationsMap.set(nodeId, list);
    }
    let iter = list.find((i) => i.iteration === iterationNum);
    if (!iter) {
      iter = {
        iteration: iterationNum,
        stageKey,
        nodeId,
        label: label || prettifyNodeId(nodeId),
        status: "running",
        startedAt: null,
        endedAt: null,
        durationMs: null,
        thinking: "",
        thinkingStartedAt: null,
        thinkingEndedAt: null,
        output: "",
        toolsMap: new Map<string, NodeToolExecution>(),
      };
      list.push(iter);
    }
    return iter;
  };

  for (const packet of packets) {
    const obj = packet?.obj as unknown as Record<string, unknown> | undefined;
    if (!obj) continue;
    const type = obj.type as PacketType | string;
    const ts = typeof obj.timestamp === "number" ? obj.timestamp : Date.now();

    // 1. FLOW_STAGE_START
    if (type === PacketType.FLOW_STAGE_START) {
      const stageKey =
        getStringValue(obj.stage_key) ||
        (packet.placement?.stage_key as string) ||
        "";
      const rawNodeId =
        getStringValue(obj.node_id) ||
        (stageKey ? stageKey.split("#")[0] : null) ||
        "";
      const nodeId = resolveCanvasNodeId(rawNodeId) || rawNodeId;
      const iterationNum =
        typeof obj.iteration === "number"
          ? obj.iteration
          : packet.placement?.iteration ?? 1;
      const label = getStringValue(obj.label) || undefined;

      const iter = getOrCreateIteration(nodeId, iterationNum, stageKey, label);
      if (iter.startedAt === null) iter.startedAt = ts;
      iter.status = "running";

      activeNodeId = nodeId;
      activeIteration = iter;
      continue;
    }

    // 2. FLOW_STAGE_OUTPUT_DELTA & MESSAGE_DELTA / TOKEN (Direct / final stage tokens)
    if (
      type === PacketType.FLOW_STAGE_OUTPUT_DELTA ||
      type === PacketType.MESSAGE_DELTA ||
      type === "message_delta" ||
      type === "token"
    ) {
      const stageKey =
        getStringValue(obj.stage_key) ||
        (packet.placement?.stage_key as string);
      const content = typeof obj.content === "string" ? obj.content : "";
      if (content) {
        let targetIter: InternalStageIteration | null = null;
        if (stageKey) {
          for (const list of Array.from(nodeIterationsMap.values())) {
            const found = list.find((i) => i.stageKey === stageKey);
            if (found) {
              targetIter = found;
              break;
            }
          }
        }
        if (!targetIter) {
          targetIter = activeIteration;
        }
        if (targetIter) {
          targetIter.output += content;
        }
      }
      continue;
    }

    // 3. FLOW_STAGE_END
    if (type === PacketType.FLOW_STAGE_END) {
      const stageKey =
        getStringValue(obj.stage_key) ||
        (packet.placement?.stage_key as string);
      const st = String(obj.status ?? "done");
      const durationMs =
        typeof obj.duration_ms === "number" ? obj.duration_ms : null;

      let targetIter: InternalStageIteration | null = activeIteration;
      if (stageKey) {
        for (const list of Array.from(nodeIterationsMap.values())) {
          const found = list.find((i) => i.stageKey === stageKey);
          if (found) {
            targetIter = found;
            break;
          }
        }
      }

      if (targetIter) {
        targetIter.status = st === "error" ? "error" : "done";
        targetIter.endedAt = ts;
        if (durationMs !== null) {
          targetIter.durationMs = durationMs;
        } else if (targetIter.startedAt !== null) {
          targetIter.durationMs = Math.max(
            MIN_STAGE_DURATION_MS,
            ts - targetIter.startedAt
          );
        }
      }

      if (activeIteration === targetIter) {
        activeNodeId = null;
        activeIteration = null;
      }
      continue;
    }

    // 4. GRAPH_STAGE_START / GRAPH_STAGE_END
    if (type === PacketType.GRAPH_STAGE_START) {
      const stageName = getStringValue(obj.stage_name);
      if (stageName) {
        const nodeId = resolveCanvasNodeId(stageName) || stageName;
        const iter = getOrCreateIteration(nodeId, 1, `${nodeId}#1`, stageName);
        if (iter.startedAt === null) iter.startedAt = ts;
        iter.status = "running";
        activeNodeId = nodeId;
        activeIteration = iter;
      }
      continue;
    }

    if (type === PacketType.GRAPH_STAGE_END) {
      const stageName = getStringValue(obj.stage_name);
      if (stageName) {
        const nodeId = resolveCanvasNodeId(stageName) || stageName;
        const list = nodeIterationsMap.get(nodeId);
        const iter = list ? list[list.length - 1] : null;
        if (iter) {
          iter.status = "done";
          iter.endedAt = ts;
          if (iter.startedAt !== null) {
            iter.durationMs = Math.max(
              MIN_STAGE_DURATION_MS,
              ts - iter.startedAt
            );
          }
        }
        if (activeNodeId === nodeId) {
          activeNodeId = null;
          activeIteration = null;
        }
      }
      continue;
    }

    // Determine target iteration for inline packets (thinking, tools)
    const stageKey = packet.placement?.stage_key || (obj.stage_key as string);
    let currentIter: InternalStageIteration | null = null;
    if (stageKey) {
      for (const list of Array.from(nodeIterationsMap.values())) {
        const found = list.find((i) => i.stageKey === stageKey);
        if (found) {
          currentIter = found;
          break;
        }
      }
    }
    if (!currentIter && typeof obj.stage_node_id === "string") {
      const resolved = resolveCanvasNodeId(obj.stage_node_id);
      if (resolved && nodeIterationsMap.has(resolved)) {
        const list = nodeIterationsMap.get(resolved)!;
        currentIter = list[list.length - 1] || null;
      }
    }
    if (!currentIter) {
      currentIter = activeIteration;
    }

    // 5. REASONING (Thinking)
    if (type === PacketType.REASONING_START) {
      const content =
        typeof obj.reasoning === "string"
          ? obj.reasoning
          : typeof obj.content === "string"
            ? obj.content
            : "";
      if (currentIter) {
        if (currentIter.thinkingStartedAt === null)
          currentIter.thinkingStartedAt = ts;
        if (content && !currentIter.thinking.includes(content)) {
          currentIter.thinking += content;
        }
      }
      continue;
    }

    if (type === PacketType.REASONING_DELTA) {
      const content = typeof obj.reasoning === "string" ? obj.reasoning : "";
      if (content && currentIter) {
        if (currentIter.thinkingStartedAt === null)
          currentIter.thinkingStartedAt = ts;
        if (!currentIter.thinking.endsWith(content)) {
          currentIter.thinking += content;
        }
        currentIter.thinkingEndedAt = ts;
      }
      continue;
    }

    // Helper: Add or update tool call on target iteration
    const recordToolInvocation = (
      target: InternalStageIteration | null,
      toolName: string,
      callId: string | null | undefined,
      inputArgs?: unknown,
      outputResult?: unknown,
      durationMs?: number | null,
      toolStatus: "running" | "done" | "error" = "done"
    ) => {
      if (!target) return;
      let toolExec = target.toolsMap.get(toolName);
      if (!toolExec) {
        toolExec = {
          toolName,
          label: prettifyNodeId(toolName),
          callCount: 0,
          durationMs: null,
          status: toolStatus,
          invocations: [],
        };
        target.toolsMap.set(toolName, toolExec);
      }

      // Check if invocation exists by callId
      let inv = callId
        ? toolExec.invocations.find((i) => i.callId === callId)
        : null;
      if (!inv && !callId && toolExec.invocations.length > 0) {
        // Fallback for deltas without callId: update the last running invocation
        inv =
          [...toolExec.invocations]
            .reverse()
            .find((i) => i.status === "running") || null;
      }
      if (!inv) {
        inv = {
          index: toolExec.invocations.length + 1,
          callId: callId || null,
          status: toolStatus,
          durationMs: durationMs ?? null,
          input: inputArgs,
          output: outputResult,
        };
        toolExec.invocations.push(inv);
        toolExec.callCount = toolExec.invocations.length;
      } else {
        if (inputArgs !== undefined) inv.input = inputArgs;
        if (outputResult !== undefined) inv.output = outputResult;
        if (durationMs !== undefined && durationMs !== null)
          inv.durationMs = durationMs;
        inv.status = toolStatus;
        if (callId && !inv.callId) inv.callId = callId;
      }

      toolExec.status = toolExec.invocations.some((i) => i.status === "running")
        ? "running"
        : toolExec.invocations.some((i) => i.status === "error")
          ? "error"
          : "done";

      const totalKnown = toolExec.invocations.reduce(
        (acc, i) => acc + (i.durationMs || 0),
        0
      );
      toolExec.durationMs = totalKnown > 0 ? totalKnown : durationMs ?? null;

      // If target is a resource node, update target.status based on tools
      const isResourceNode = Array.from(toolNameToNodeId.values()).includes(
        target.nodeId
      );
      if (isResourceNode) {
        const allTools = Array.from(target.toolsMap.values());
        target.status = allTools.some((t) => t.status === "running")
          ? "running"
          : allTools.some((t) => t.status === "error")
            ? "error"
            : "done";
      }
    };

    // 6. CUSTOM_TOOL
    if (type === PacketType.CUSTOM_TOOL_START) {
      const toolName = getStringValue(obj.tool_name) || "custom_tool";
      const callId =
        getStringValue(obj.call_id) || getStringValue(obj.tool_call_id);
      const args =
        obj.args !== undefined
          ? obj.args
          : obj.input !== undefined
            ? obj.input
            : undefined;

      recordToolInvocation(
        currentIter,
        toolName,
        callId,
        args,
        undefined,
        null,
        "running"
      );

      // Also record on tool resource node if present in canvas
      const resourceNodeId = toolNameToNodeId.get(toolName);
      if (resourceNodeId && resourceNodeId !== currentIter?.nodeId) {
        const resourceIter = getOrCreateIteration(
          resourceNodeId,
          1,
          `${resourceNodeId}#1`,
          toolName
        );
        recordToolInvocation(
          resourceIter,
          toolName,
          callId,
          args,
          undefined,
          null,
          "running"
        );
      }
      continue;
    }

    if (type === PacketType.CUSTOM_TOOL_DELTA) {
      const callId =
        getStringValue(obj.call_id) || getStringValue(obj.tool_call_id);
      let toolName = getStringValue(obj.tool_name);
      if (!toolName && callId && currentIter) {
        for (const [name, tExec] of Array.from(
          currentIter.toolsMap.entries()
        )) {
          if (
            tExec.invocations.some(
              (inv: ToolInvocationDetail) => inv.callId === callId
            )
          ) {
            toolName = name;
            break;
          }
        }
      }
      if (!toolName && callId) {
        for (const list of Array.from(nodeIterationsMap.values())) {
          for (const it of list) {
            for (const [name, tExec] of Array.from(it.toolsMap.entries())) {
              if (
                tExec.invocations.some(
                  (inv: ToolInvocationDetail) => inv.callId === callId
                )
              ) {
                toolName = name;
                break;
              }
            }
            if (toolName) break;
          }
          if (toolName) break;
        }
      }
      if (!toolName && currentIter && currentIter.toolsMap.size > 0) {
        const names = Array.from(currentIter.toolsMap.keys());
        toolName = names[names.length - 1] || null;
      }
      if (!toolName) toolName = "custom_tool";

      const result =
        obj.data !== undefined
          ? obj.data
          : obj.output !== undefined
            ? obj.output
            : obj;
      const isError = obj.response_type === "error";

      recordToolInvocation(
        currentIter,
        toolName,
        callId,
        undefined,
        result,
        null,
        isError ? "error" : "done"
      );

      const resourceNodeId = toolNameToNodeId.get(toolName);
      if (resourceNodeId && resourceNodeId !== currentIter?.nodeId) {
        const resourceIter = getOrCreateIteration(
          resourceNodeId,
          1,
          `${resourceNodeId}#1`,
          toolName
        );
        recordToolInvocation(
          resourceIter,
          toolName,
          callId,
          undefined,
          result,
          null,
          isError ? "error" : "done"
        );
      }
      continue;
    }

    // 7. SEARCH_TOOL
    if (type === PacketType.SEARCH_TOOL_START) {
      const callId =
        getStringValue(obj.call_id) || getStringValue(obj.tool_call_id);
      recordToolInvocation(
        currentIter,
        "web_search",
        callId,
        undefined,
        undefined,
        null,
        "running"
      );
      const resNode = toolNameToNodeId.get("web_search");
      if (resNode && resNode !== currentIter?.nodeId) {
        recordToolInvocation(
          getOrCreateIteration(resNode, 1, `${resNode}#1`, "WebTools"),
          "web_search",
          callId,
          undefined,
          undefined,
          null,
          "running"
        );
      }
      continue;
    }

    if (type === PacketType.SEARCH_TOOL_QUERIES_DELTA) {
      const callId =
        getStringValue(obj.call_id) || getStringValue(obj.tool_call_id);
      const queries = obj.queries;
      recordToolInvocation(
        currentIter,
        "web_search",
        callId,
        { queries },
        undefined,
        null,
        "running"
      );
      const resNode = toolNameToNodeId.get("web_search");
      if (resNode && resNode !== currentIter?.nodeId) {
        recordToolInvocation(
          getOrCreateIteration(resNode, 1, `${resNode}#1`, "WebTools"),
          "web_search",
          callId,
          { queries },
          undefined,
          null,
          "running"
        );
      }
      continue;
    }

    if (type === PacketType.SEARCH_TOOL_DOCUMENTS_DELTA) {
      const callId =
        getStringValue(obj.call_id) || getStringValue(obj.tool_call_id);
      const docs = Array.isArray(obj.documents) ? obj.documents : [];
      const resultSummary = `${docs.length} kaynak bulundu`;
      recordToolInvocation(
        currentIter,
        "web_search",
        callId,
        undefined,
        resultSummary,
        null,
        "done"
      );
      const resNode = toolNameToNodeId.get("web_search");
      if (resNode && resNode !== currentIter?.nodeId) {
        recordToolInvocation(
          getOrCreateIteration(resNode, 1, `${resNode}#1`, "WebTools"),
          "web_search",
          callId,
          undefined,
          resultSummary,
          null,
          "done"
        );
      }
      continue;
    }

    // 8. PYTHON_TOOL
    if (type === PacketType.PYTHON_TOOL_START) {
      const callId = getStringValue(obj.call_id);
      const code = typeof obj.code === "string" ? obj.code : "";
      recordToolInvocation(
        currentIter,
        "run_python",
        callId,
        { code },
        undefined,
        null,
        "running"
      );
      const resNode = toolNameToNodeId.get("run_python");
      if (resNode && resNode !== currentIter?.nodeId) {
        recordToolInvocation(
          getOrCreateIteration(resNode, 1, `${resNode}#1`, "CodeTools"),
          "run_python",
          callId,
          { code },
          undefined,
          null,
          "running"
        );
      }
      continue;
    }

    if (type === PacketType.PYTHON_TOOL_DELTA) {
      const callId = getStringValue(obj.call_id);
      const stdout = typeof obj.stdout === "string" ? obj.stdout : "";
      const stderr = typeof obj.stderr === "string" ? obj.stderr : "";
      const outText = (stdout + (stderr ? `\nHata: ${stderr}` : "")).trim();
      recordToolInvocation(
        currentIter,
        "run_python",
        callId,
        undefined,
        outText,
        null,
        stderr ? "error" : "done"
      );
      const resNode = toolNameToNodeId.get("run_python");
      if (resNode && resNode !== currentIter?.nodeId) {
        recordToolInvocation(
          getOrCreateIteration(resNode, 1, `${resNode}#1`, "CodeTools"),
          "run_python",
          callId,
          undefined,
          outText,
          null,
          stderr ? "error" : "done"
        );
      }
      continue;
    }
  }

  // Final sanity check: If flow reached completion, close lingering tools and resource node statuses
  const hasFinished = packets.some((p) => {
    const obj = p.obj as unknown as Record<string, unknown> | undefined;
    if (!obj) return false;
    const t = obj.type;
    return (
      t === PacketType.STOP ||
      t === "stop" ||
      (t === PacketType.FLOW_STAGE_END && Boolean(obj.is_final_stage)) ||
      (t === PacketType.GRAPH_STAGE_END &&
        typeof obj.stage_name === "string" &&
        obj.stage_name.toLowerCase().includes("output"))
    );
  });

  if (hasFinished) {
    for (const iterList of Array.from(nodeIterationsMap.values())) {
      for (const it of iterList) {
        for (const toolExec of Array.from(it.toolsMap.values())) {
          if (toolExec.status === "running") {
            toolExec.status = "done";
            for (const inv of toolExec.invocations) {
              if (inv.status === "running") inv.status = "done";
            }
          }
        }
        const isResourceNode = Array.from(toolNameToNodeId.values()).includes(
          it.nodeId
        );
        if (it.status === "running" && isResourceNode) {
          it.status = "done";
        }
      }
    }
  }

  // Construct final NodeExecutionData record
  const result: Record<string, NodeExecutionData> = {};

  Array.from(nodeIterationsMap.entries()).forEach(([nodeId, iterList]) => {
    if (!iterList || iterList.length === 0) return;

    // Sort iterations ascending
    iterList.sort((a, b) => a.iteration - b.iteration);

    const latest = iterList[iterList.length - 1]!;
    const iterationsData: NodeIterationData[] = iterList.map((it) => {
      const tools = Array.from(it.toolsMap.values());
      const thinkDuration =
        it.thinkingStartedAt && it.thinkingEndedAt
          ? Math.max(
              MIN_STAGE_DURATION_MS,
              it.thinkingEndedAt - it.thinkingStartedAt
            )
          : null;

      return {
        iteration: it.iteration,
        thinking: it.thinking.trim() || undefined,
        thinkingDurationMs: thinkDuration,
        tools: tools.length > 0 ? tools : undefined,
        output: it.output.trim() || undefined,
        status: it.status,
        durationMs: it.durationMs,
      };
    });

    // Aggregate tools across iterations
    const combinedToolsMap = new Map<string, NodeToolExecution>();
    for (const it of iterList) {
      for (const [toolName, exec] of Array.from(it.toolsMap.entries())) {
        const existing = combinedToolsMap.get(toolName);
        if (!existing) {
          combinedToolsMap.set(toolName, {
            ...exec,
            invocations: [...exec.invocations],
          });
        } else {
          existing.callCount += exec.callCount;
          existing.invocations.push(...exec.invocations);
          if (exec.durationMs) {
            existing.durationMs = (existing.durationMs || 0) + exec.durationMs;
          }
          if (exec.status === "running") existing.status = "running";
        }
      }
    }

    const aggregatedThinking = iterList
      .map((it) => it.thinking.trim())
      .filter(Boolean)
      .join("\n\n--- [Sonraki Tur] ---\n\n");

    const aggregatedOutput = iterList
      .map((it) => it.output.trim())
      .filter(Boolean)
      .join("\n\n");

    const totalDuration = iterList.reduce(
      (sum, it) => sum + (it.durationMs || 0),
      0
    );
    const isResourceNode = Array.from(toolNameToNodeId.values()).includes(
      nodeId
    );
    let resolvedDuration =
      totalDuration > 0 ? totalDuration : latest.durationMs;
    if (isResourceNode && (!resolvedDuration || resolvedDuration === 0)) {
      const toolsDuration = Array.from(combinedToolsMap.values()).reduce(
        (sum, t) => sum + (t.durationMs || 0),
        0
      );
      if (toolsDuration > 0) resolvedDuration = toolsDuration;
    }

    result[nodeId] = {
      nodeId,
      stageKey: latest.stageKey,
      label: latest.label,
      status: iterList.some((it) => it.status === "running")
        ? "running"
        : iterList.some((it) => it.status === "error")
          ? "error"
          : "done",
      durationMs: resolvedDuration ?? null,
      thinking: aggregatedThinking || undefined,
      thinkingDurationMs:
        latest.thinkingStartedAt && latest.thinkingEndedAt
          ? latest.thinkingEndedAt - latest.thinkingStartedAt
          : null,
      tools: Array.from(combinedToolsMap.values()),
      output: aggregatedOutput || undefined,
      iterations: iterList.length > 1 ? iterationsData : undefined,
    };
  });

  return result;
}
