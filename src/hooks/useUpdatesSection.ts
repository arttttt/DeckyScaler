import { useState } from "react";
import { notify } from "../utils/notify";
import { stableInstallRequest } from "../api";
import { canInstallThroughDecky } from "../api/deckyInstaller";
import { DeveloperModeChange, updatesView } from "../presentation/updates";
import { developerModeFlow } from "./developerModeFlow";
import { useDeckyInstall } from "./useDeckyInstall";
import { usePluginUpdates } from "./usePluginUpdates";

/** The Updates section: checking for and installing the newest release, and Developer mode, which asks
 *  first before it turns on. */
export const useUpdatesSection = () => {
  const { check, onCheck, onDeveloperMode } = usePluginUpdates();
  const { install, start, clearError } = useDeckyInstall();
  const [change, setChange] = useState<DeveloperModeChange | null>(null);
  const developerMode = developerModeFlow({ setChange, save: onDeveloperMode, notify });

  return {
    view: updatesView({ ...check, install, deckyInstallerAvailable: canInstallThroughDecky(), developerModeChange: change }),
    onCheck: () => {
      clearError();
      onCheck();
    },
    onInstall: () => start(stableInstallRequest, "Updates -> stableInstallRequest"),
    onDeveloperMode: (on: boolean) => void developerMode.onToggle(on),
    onConfirm: () => void developerMode.onConfirm(change),
    onCancel: developerMode.onCancel,
  };
};
