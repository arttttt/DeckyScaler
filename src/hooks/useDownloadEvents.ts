import { useEffect, useRef } from "react";
import { addEventListener, removeEventListener } from "@decky/api";

/** The backend's downloads report as events: what is downloading, bytes received, total bytes or null. */
export type DownloadEvent = "library_download" | "proton_download";

/** Progress of a download the backend is running, from the event it reports it as. */
export const useDownloadEvents = (
  event: DownloadEvent,
  onProgress: (id: string, received: number, total: number | null) => void,
) => {
  const handler = useRef(onProgress);
  handler.current = onProgress;
  useEffect(() => {
    const listener = addEventListener<[string, number, number | null]>(event, (id, received, total) =>
      handler.current(id, received, total),
    );
    return () => removeEventListener(event, listener);
  }, [event]);
};
