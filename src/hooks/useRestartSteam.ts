import { useState } from "react";
import { restartSteam } from "../api/steamClient";
import { RESTART_CONFIRMATION } from "../presentation/proton";

/** Restarting Steam closes a running game with it: asked first, wherever the button is. */
export const useRestartSteam = () => {
  const [asking, setAsking] = useState(false);
  return {
    onRestart: () => setAsking(true),
    confirmation: asking ? RESTART_CONFIRMATION : null,
    onConfirm: () => {
      setAsking(false);
      restartSteam();
    },
    onCancel: () => setAsking(false),
  };
};
