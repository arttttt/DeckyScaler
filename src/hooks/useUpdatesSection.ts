import { useState } from "react";
import { notify } from "../utils/notify";
import { stableInstallRequest } from "../api";
import { canInstallThroughDecky } from "../api/deckyInstaller";
import { DeveloperModeChange, confirmedDeveloperModeChange, developerModeChange, updatesView } from "../presentation/updates";
import { useDeckyInstall } from "./useDeckyInstall";
import { usePluginUpdates } from "./usePluginUpdates";

/** The Updates section: checking for and installing the newest release, and Developer mode, which asks
 *  first before it turns on. */
export const useUpdatesSection = () => {
  const { check, onCheck, onDeveloperMode } = usePluginUpdates();
  const { install, start, clearError } = useDeckyInstall();
  const [change, setChange] = useState<DeveloperModeChange | null>(null);

  const save = async (saving: DeveloperModeChange) => {
    setChange(saving);
    const failure = await onDeveloperMode(saving.on);
    setChange(null);
    if (failure) notify(failure);
  };

  return {
    view: updatesView({ ...check, install, deckyInstallerAvailable: canInstallThroughDecky(), developerModeChange: change }),
    onCheck: () => {
      clearError();
      onCheck();
    },
    onInstall: () => start(stableInstallRequest, "Updates -> stableInstallRequest"),
    onDeveloperMode: (on: boolean) => {
      const next = developerModeChange(on);
      if (next.stage === "confirming") setChange(next);
      else void save(next);
    },
    onConfirm: () => {
      if (change) void save(confirmedDeveloperModeChange(change));
    },
    onCancel: () => setChange(null),
  };
};
