import { useCallback, useEffect, useState } from "react";
import { InstalledProton, protonInstalled } from "../api";
import { restartSteam } from "../api/steamClient";
import { protonPageView } from "../presentation/proton";
import { safeAsyncOperation } from "../utils";

/** State and calls behind the Proton page; `reload` after its dialogs change the builds. */
export const useProtonPage = () => {
  const [installed, setInstalled] = useState<InstalledProton | null>(null);

  const reload = useCallback(() => {
    void safeAsyncOperation(protonInstalled, "ProtonPage -> protonInstalled").then((answer) => {
      if (answer) setInstalled(answer);
    });
  }, []);

  useEffect(reload, [reload]);

  return { view: protonPageView(installed), reload, onRestart: restartSteam };
};
