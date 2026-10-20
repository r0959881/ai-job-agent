import * as React from "react";
import { subscribe } from "@/lib/local/runner";
import type { RunEvent } from "@/lib/types";

/** A run's events: live while this tab runs it, otherwise the stored log. */
export function useRunEvents(runId: number | null) {
  const [events, setEvents] = React.useState<RunEvent[]>([]);
  const [ended, setEnded] = React.useState(false);

  React.useEffect(() => {
    if (runId == null) return;
    setEvents([]);
    setEnded(false);
    let frame = 0;
    const unsubscribe = subscribe(runId, (next, done) => {
      if (frame) window.cancelAnimationFrame(frame);
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        setEvents([...next]);
        setEnded(done);
      });
    });
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      unsubscribe();
    };
  }, [runId]);

  return { events, ended, connected: !ended };
}
