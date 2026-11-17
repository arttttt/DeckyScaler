import { useCallback, useEffect, useState } from "react";
import { protonBuildOptions, protonInstall, protonVersions } from "../api";
import { ProtonDownloadState, installDone, protonDownloadView, protonOutcome } from "../presentation/proton";
import { restartSteam } from "../api/steamClient";
import { safeAsyncOperation } from "../utils";
import { useDownloadEvents } from "./useDownloadEvents";

const NO_ANSWER = { status: "error" as const, message: "The plugin backend did not answer." };

/** State and calls behind the dialog that downloads Proton builds; `onChanged` runs after a build is installed. */
export const useDownloadBuilds = (onChanged: () => void) => {
  const [state, setState] = useState<ProtonDownloadState>({
    options: [],
    installedOne: false,
    build: null,
    listing: null,
    checking: false,
    busy: null,
    download: null,
    message: null,
  });

  useDownloadEvents("proton_download", (id, received, total) =>
    setState((s) => (s.busy === id ? { ...s, download: { received, total } } : s)),
  );

  const check = useCallback((build: string, message: string | null = null) => {
    setState((s) => ({ ...s, build, checking: true, message }));
    void safeAsyncOperation(() => protonVersions(build), "DownloadBuilds -> protonVersions").then((listing) =>
      setState((s) => (s.build === build ? { ...s, checking: false, listing: listing ?? NO_ANSWER } : s)),
    );
  }, []);

  useEffect(() => {
    void safeAsyncOperation(protonBuildOptions, "DownloadBuilds -> protonBuildOptions").then((options) => {
      if (!options?.length) return setState((s) => ({ ...s, listing: NO_ANSWER }));
      setState((s) => ({ ...s, options }));
      check(options[0].id);
    });
  }, [check]);

  const onDownload = async (id: string) => {
    const build = state.build;
    if (build === null) return;
    setState((s) => ({ ...s, busy: id, download: null, message: null }));
    const answer = await safeAsyncOperation(() => protonInstall(build, id), "DownloadBuilds -> protonInstall");
    const installed = answer?.status === "success";
    setState((s) => ({ ...s, busy: null, download: null, installedOne: s.installedOne || installed }));
    if (installed) onChanged();
    check(build, protonOutcome(answer ?? null, installDone(id)));
  };

  return {
    view: protonDownloadView(state),
    onBuild: (build: string) => check(build),
    onCheck: () => state.build !== null && check(state.build),
    onDownload: (id: string) => void onDownload(id),
    onRestart: restartSteam,
  };
};
