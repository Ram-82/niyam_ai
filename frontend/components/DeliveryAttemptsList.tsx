/**
 * Small table of past delivery_attempts for a (period, return_type)
 * scope. One row per attempt with a status chip + timestamps. Used
 * inside DeliveryPanel; separated so future places (an admin "delivery
 * log" surface, e.g.) can reuse the row rendering.
 */
"use client";

import type {
  DeliveryAttemptRow,
  DeliveryStatus,
  WhatsAppErrorKind,
} from "@/lib/types";
import { DELIVERY_STATUS_COPY, WHATSAPP_ERROR_COPY } from "@/lib/constants";
import { formatTimestampIN } from "@/lib/format-date";


export function DeliveryAttemptsList({
  attempts,
}: {
  attempts: DeliveryAttemptRow[];
}) {
  if (attempts.length === 0) {
    return (
      <p className="text-xs text-ink-muted italic p-3 text-center">
        No delivery attempts yet.
      </p>
    );
  }
  return (
    <ul
      className="border border-rule rounded-md divide-y divide-rule bg-paper-raised"
      data-testid="delivery-attempts"
    >
      {attempts.map((a) => (
        <li key={a.id} className="p-3 text-sm">
          <div className="flex items-center gap-3 flex-wrap">
            <StatusChip status={a.status} />
            <span className="font-mono text-xs text-ink-muted">
              {a.provider}
              {a.provider_message_id
                ? ` · ${a.provider_message_id.slice(0, 24)}${a.provider_message_id.length > 24 ? "…" : ""}`
                : ""}
            </span>
            <span className="ml-auto text-xs text-ink-muted font-mono">
              {formatTimestampIN(a.attempted_at)}
            </span>
          </div>
          {a.status === "failed" && (
            <p className="text-xs text-red-fg mt-2">
              {WHATSAPP_ERROR_COPY[a.error_kind ?? "other"] ??
                WHATSAPP_ERROR_COPY.other}
            </p>
          )}
          {(a.delivered_at || a.read_at) && (
            <p className="text-xs text-ink-muted mt-1 font-mono">
              {a.delivered_at && `delivered ${formatTimestampIN(a.delivered_at)}`}
              {a.delivered_at && a.read_at && " · "}
              {a.read_at && `read ${formatTimestampIN(a.read_at)}`}
            </p>
          )}
        </li>
      ))}
    </ul>
  );
}


function StatusChip({ status }: { status: DeliveryStatus }) {
  const meta = DELIVERY_STATUS_COPY[status] || {
    label: status,
    tone: "muted" as const,
  };
  const cls =
    meta.tone === "ok"
      ? "bg-green-bg text-green-fg"
      : meta.tone === "bad"
        ? "bg-red-bg text-red-fg"
        : meta.tone === "warn"
          ? "bg-amber-bg text-amber-fg"
          : "bg-paper border border-rule text-ink-muted";
  return (
    <span
      className={`text-xs font-semibold px-2 py-0.5 rounded-sm ${cls}`}
      data-testid={`delivery-status-${status}`}
    >
      {meta.label}
    </span>
  );
}
