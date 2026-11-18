import { useCallback, useEffect, useState } from "react";
import { userLibraryInstall, userLibrarySources, userLibraryVersions } from "../api";
import { LibraryDownloadState, downloadOutcome, firstSource, libraryDownloadView } from "../presentation/libraries";
import { safeAsyncOperation } from "../utils";
import { useDownloadEvents } from "./useDownloadEvents";

const NO_ANSWER = { status: "error" as const, message: "The plugin backend did not answer." };

/** State and calls behind the dialog that downloads libraries; `onChanged` runs after one is added. */
export const useDownloadLibraries = (onChanged: () => void) => {
  const [state, setState] = useState<LibraryDownloadState>({
    sources: [], source: null, listing: null, checking: false, busy: null, download: null, message: null,
  });

  useDownloadEvents("user_library_download", (id, received, total) =>
    setState((s) => (s.busy === id ? { ...s, download: { received, total } } : s)),
  );

  const check = useCallback((source: string, message: string | null = null) => {
    setState((s) => ({ ...s, source, checking: true, message }));
    void safeAsyncOperation(() => userLibraryVersions(source), "DownloadLibraries -> versions").then((listing) =>
      setState((s) => (s.source === source ? { ...s, checking: false, listing: listing ?? NO_ANSWER } : s)),
    );
  }, []);

  useEffect(() => {
    void safeAsyncOperation(userLibrarySources, "DownloadLibraries -> sources").then((sources) => {
      setState((s) => ({ ...s, sources: sources ?? [] }));
      const first = firstSource(sources ?? null);
      if (first !== null) check(first);
    });
  }, [check]);

  const onDownload = async (id: string) => {
    const source = state.source;
    if (source === null) return;
    setState((s) => ({ ...s, busy: id, download: null, message: null }));
    const answer = await safeAsyncOperation(() => userLibraryInstall(source, id), "DownloadLibraries -> install");
    setState((s) => ({ ...s, busy: null, download: null }));
    if (answer?.status === "success") onChanged();
    check(source, downloadOutcome(answer ?? null, id));
  };

  return {
    view: libraryDownloadView(state),
    onSource: (source: string) => check(source),
    onCheck: () => state.source !== null && check(state.source),
    onDownload: (id: string) => void onDownload(id),
  };
};
