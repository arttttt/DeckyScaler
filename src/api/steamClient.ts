import type { LifetimeNotification } from "@decky/ui";
import type { InstalledProton, ProtonGame } from "./index";

/** Steam's own client API, for the launch options of a game. */

/** The game's launch options; rejects when Steam doesn't say, which is not the same as having none. */
export const getAppLaunchOptions = (appId: number): Promise<string> =>
  new Promise((resolve, reject) => {
    if (typeof SteamClient === "undefined" || !SteamClient?.Apps?.RegisterForAppDetails) {
      reject(new Error("Steam's client API is not available."));
      return;
    }
    let settled = false;
    let unregister = () => {};
    const timeout = window.setTimeout(() => {
      if (settled) return;
      settled = true;
      unregister();
      reject(new Error("Timed out reading launch options."));
    }, 5000);
    const registration = SteamClient.Apps.RegisterForAppDetails(
      appId,
      (details: { strLaunchOptions?: string }) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timeout);
        unregister();
        resolve(details?.strLaunchOptions ?? "");
      }
    );
    unregister = registration.unregister;
  });

export const setAppLaunchOptions = (appId: number, options: string): void => {
  if (typeof SteamClient !== "undefined" && SteamClient?.Apps?.SetAppLaunchOptions) {
    SteamClient.Apps.SetAppLaunchOptions(appId, options);
  }
};

/** Steam reports a stopped non-Steam shortcut with appid 0, which names no game. */
const NO_APPID = 0;
/** After Steam says a game stopped, a straggling Proton process may still hold its files for a moment. */
const STOPPED_GRACE_MS = 2000;

/** Calls back with a game's appid shortly after Steam says it stopped running; returns the unsubscribe.
 *  A no-op where Steam's client API doesn't offer it. */
export const onGameStopped = (callback: (appid: number) => void): (() => void) => {
  try {
    const registration = SteamClient?.GameSessions?.RegisterForAppLifetimeNotifications?.(
      (notification: LifetimeNotification) => {
        if (notification.bRunning || notification.unAppID === NO_APPID) return;
        window.setTimeout(() => callback(notification.unAppID), STOPPED_GRACE_MS);
      },
    );
    return () => registration?.unregister?.();
  } catch {
    return () => {};
  }
};

/** Restarts Steam, which then lists the Proton builds as they are now; a no-op where Steam's client API doesn't offer it. */
export const restartSteam = (): void => {
  if (typeof SteamClient !== "undefined" && SteamClient?.User?.StartRestart) {
    SteamClient.User.StartRestart(false);
  }
};

/** Sets the Proton a game runs with, as its Properties → Compatibility does; only for a build Steam lists. */
export const specifyCompatTool = (appId: number, toolName: string): void => {
  if (typeof SteamClient !== "undefined" && SteamClient?.Apps?.SpecifyCompatTool) {
    SteamClient.Apps.SpecifyCompatTool(appId, toolName);
  }
};

/** What Steam's library calls an app, installed or not; null when Steam doesn't know it. */
const steamAppName = (appid: string): string | null => {
  try {
    return window.appStore?.GetAppOverviewByAppID?.(Number(appid))?.display_name || null;
  } catch {
    return null;
  }
};

/** Games the backend couldn't name (no longer installed here), named as Steam's library calls them. */
export const withSteamNames = (games: ProtonGame[]): ProtonGame[] =>
  games.map((game) => (game.name ? game : { ...game, name: steamAppName(game.appid) }));

/** The installed builds, with every game Steam's library can name named. */
export const installedWithSteamNames = (installed: InstalledProton): InstalledProton => ({
  ...installed,
  tools: installed.tools.map((tool) => ({ ...tool, games: withSteamNames(tool.games) })),
  moves: installed.moves.map((move) => ({ ...move, games: withSteamNames(move.games) })),
});
