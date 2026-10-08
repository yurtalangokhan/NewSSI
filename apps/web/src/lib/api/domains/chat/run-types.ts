export type RunTerminalStatus =
  | "completed"
  | "failed"
  | "cancelled"
  | "interrupted";

export type RunStatus = "running" | RunTerminalStatus;

/** A chat's live run, as `GET /chat/sessions/{id}/active-run` reports it. */
export interface ActiveRunInfo {
  run_id: string;
  status: RunStatus;
  started_at: number;
  input_preview: string;
  client_request_id: string | null;
}

export type RunMetaPacket =
  | { type: "run_started"; run_id: string; thread_id: string }
  | { type: "run_end"; status: RunTerminalStatus; error_code: string | null }
  | { type: "resync"; first_available_seq: number }
  // Replay is over: every packet after it is the live tail of the run.
  | { type: "caught_up" };

export function isRunMetaPacket(value: unknown): value is RunMetaPacket {
  return (
    typeof value === "object" &&
    value !== null &&
    ["run_started", "run_end", "resync", "caught_up"].includes(
      (value as { type?: unknown }).type as string
    )
  );
}
