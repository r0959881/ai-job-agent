import * as React from "react";
import type { RunEvent } from "@/lib/types";

/** Subscribe to /api/runs/:id/events. Replays past events, then streams until the run ends. */
export function useRunEvents(runId: number | null) {
  const [events, setEvents] = React.useState<RunEvent[]>([]);
  const [ended, setEnded] = React.useState(false);
  const [connected, setConnected] = React.useState(false);

  React.useEffect(() => {
    if (runId == null) return;
    setEvents([]);
    setEnded(false);
    const source = new EventSource(`/api/runs/${runId}/events`);
    let buffer: RunEvent[] = [];
    let frame = 0;
    const flush = () => {
      frame = 0;
      const batch = buffer;
      buffer = [];
      setEvents((current) => {
        const last = current.at(-1)?.seq ?? 0;
        return [...current, ...batch.filter((event) => event.seq > last)];
      });
    };
    source.onopen = () => setConnected(true);
    source.onmessage = (message) => {
      try {
        buffer.push(JSON.parse(message.data) as RunEvent);
        if (!frame) frame = window.requestAnimationFrame(flush);
      } catch {
        /* ignore malformed lines */
      }
    };
    source.addEventListener("end", () => {
      flush();
      setEnded(true);
      setConnected(false);
      source.close();
    });
    source.onerror = () => setConnected(false); // EventSource reconnects with Last-Event-ID.
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      source.close();
    };
  }, [runId]);

  return { events, ended, connected };
}
