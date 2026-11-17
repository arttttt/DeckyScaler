import type {
  InstalledProton,
  InstalledProtonTool,
  ProtonBuildOption,
  ProtonGame,
  ProtonListing,
  ProtonProblem,
  ProtonRemoval,
} from "../api";
import { ReleaseDownload, ReleaseRowView, actionOutcome, byteSize, downloadRows, listingMessage } from "./releases";

/**
 * The Proton page and its two dialogs, shaped like the OptiScaler versions block: a summary, a dialog to
 * download builds and one to manage the installed ones; and, only when needed, a row to restart Steam.
 */

const PROBLEMS: Record<ProtonProblem, string> = {
  "no-steam": "Steam hasn't been run on this device yet. Start it once, then come back.",
  "several-steams": "Found more than one Steam install on this device. Start Steam so DeckyScaler knows which one to use.",
};

/** Why there is no Steam install to put builds in. */
export const problemText = (problem: ProtonProblem): string => PROBLEMS[problem];

/** How an action that needed a Steam install went: the backend's words, or why there was no install to use. */
export const protonOutcome = (
  answer: { status: string; message?: string; problem?: ProtonProblem } | null,
  done: string,
): string => (answer?.problem ? problemText(answer.problem) : actionOutcome(answer, done));

// ── The page ─────────────────────────────────────────────────────────────────

export const CHOOSING_HINT = "A game's Proton is chosen in Steam: its Properties → Compatibility.";
export const RESTART_TEXT = "Steam needs a restart to see changes to its Proton builds.";

export type ProtonPageView = {
  summary: string;
  /** The row that restarts Steam, shown only when builds came or went since it started. */
  restart: boolean;
  /** The dialogs open only when there is a Steam install to work with. */
  dialogsEnabled: boolean;
  hint: string;
};

const count = (n: number, one: string, many: string): string => `${n} ${n === 1 ? one : many}`;

export const protonPageView = (installed: InstalledProton | null): ProtonPageView => {
  const base = { hint: CHOOSING_HINT };
  if (installed === null) return { ...base, summary: "Loading…", restart: false, dialogsEnabled: false };
  if (installed.problem) return { ...base, summary: problemText(installed.problem), restart: false, dialogsEnabled: false };
  const tools = installed.tools.length;
  return {
    ...base,
    summary: tools ? `${count(tools, "build", "builds")} installed.` : "No Proton build is installed yet.",
    restart: installed.restart_needed,
    dialogsEnabled: true,
  };
};

// ── Download dialog ──────────────────────────────────────────────────────────

export const UNPACKING = "Unpacking… this takes a minute or two";

export type ProtonDownloadState = {
  options: ProtonBuildOption[];
  build: string | null;
  listing: ProtonListing | null;
  checking: boolean;
  /** The build being installed. */
  busy: string | null;
  download: ReleaseDownload | null;
  /** What the last install came to; cleared by the next action. */
  message: string | null;
};

export type ProtonDownloadView = {
  buildOptions: { data: string; label: string }[];
  build: string | null;
  /** The build stays put during an install: its end reloads the build's listing. */
  buildEnabled: boolean;
  /** What to know before picking the build. */
  buildNote: string | null;
  checkLabel: string;
  checkEnabled: boolean;
  rows: ReleaseRowView[];
  message: string | null;
};

const listingProblem = (listing: ProtonListing | null): string | null =>
  listing?.status === "success" && listing.problem ? problemText(listing.problem) : null;

export const protonDownloadView = (state: ProtonDownloadState): ProtonDownloadView => {
  const { listing, checking, busy } = state;
  const option = state.options.find((o) => o.id === state.build);
  const label = option?.label ?? "this build";
  const blocked = listingProblem(listing);
  const idle = busy === null;
  const rows = listing?.status === "success" ? downloadRows(listing.versions, busy, state.download, UNPACKING) : [];
  return {
    buildOptions: state.options.map((o) => ({ data: o.id, label: o.label })),
    build: state.build,
    buildEnabled: idle,
    buildNote: option?.note ?? null,
    checkLabel: checking ? "Checking…" : "Check for new builds",
    checkEnabled: !checking && idle,
    // Without a Steam install to put it in, nothing is downloaded.
    rows: blocked ? rows.map((row) => ({ ...row, action: row.action && { ...row.action, enabled: false } })) : rows,
    message: state.message ?? blocked ?? listingMessage(listing, label, `No ${label} releases are published.`),
  };
};

/** What the dialog says when an install succeeded and the backend gave no words of its own. */
export const installDone = (tool: string): string => `${tool} is installed. Restart Steam to use it.`;

// ── Manage dialog ────────────────────────────────────────────────────────────

export type ProtonManageState = {
  installed: InstalledProton | null;
  /** The build being removed. */
  busy: string | null;
  /** What the last removal came to; cleared by the next one. */
  message: string | null;
};

export type ProtonManageView = {
  rows: ReleaseRowView[];
  usage: string | null;
  message: string | null;
};

export type ProtonMenuItem = { action: "remove"; label: string; destructive: boolean };

/** What can be done with an installed build. */
export const PROTON_MENU: ProtonMenuItem[] = [{ action: "remove", label: "Remove", destructive: true }];

const usedBy = (tool: InstalledProtonTool): string => {
  const games = tool.games.length ? `used by ${count(tool.games.length, "game", "games")}` : "no games";
  return tool.global_default ? `${games} · the default for all games` : games;
};

const describeTool = (tool: InstalledProtonTool): string => {
  if (tool.system) return "Installed system-wide · can't be removed here";
  return [tool.build_label ?? "Not installed by DeckyScaler", byteSize(tool.size), usedBy(tool)].join(" · ");
};

export const protonManageView = (state: ProtonManageState): ProtonManageView => {
  const { installed, busy } = state;
  const tools = installed?.tools ?? [];
  const idle = busy === null;
  const nothing = installed?.problem ? problemText(installed.problem) : installed && tools.length === 0 ? "No Proton build is installed yet." : null;
  return {
    rows: tools.map((tool) => ({
      id: tool.id,
      label: tool.id,
      description: busy === tool.id ? "Removing…" : describeTool(tool),
      action: tool.system ? null : { label: "Manage", enabled: idle },
    })),
    usage: installed && installed.installed_bytes > 0 ? `Installed builds take ${byteSize(installed.installed_bytes)}.` : null,
    message: state.message ?? nothing,
  };
};

/** What the dialog says when a removal succeeded and the backend gave no words of its own. */
export const removeDone = (tool: string): string => `${tool} is removed.`;

/** A game as the removal warning names it; one nothing names any more says so instead of a bare number. */
export const gameName = (game: ProtonGame): string => game.name ?? `app ${game.appid} · not installed`;

/** The removal question: a warning naming the games whose user chose the build, or why it can't be asked. */
export type ProtonRemoveConfirmation = { title: string; lines: string[]; okLabel: string; removes: boolean; alert: boolean };

const cantRemove = (tool: string, reason: string): ProtonRemoveConfirmation => ({
  title: `Can't remove ${tool}`,
  lines: [reason],
  okLabel: "OK",
  removes: false,
  alert: true,
});

export const protonRemoveConfirmation = (tool: string, removal: ProtonRemoval | null): ProtonRemoveConfirmation => {
  if (removal === null) return cantRemove(tool, "The plugin backend did not answer.");
  if (removal.status === "error") return cantRemove(tool, protonOutcome(removal, ""));
  if (removal.games.length === 0 && !removal.global_default) {
    return { title: `Remove ${tool}?`, lines: ["No game uses it."], okLabel: "Remove", removes: true, alert: false };
  }
  const names = removal.games.map(gameName).sort((a, b) => a.localeCompare(b));
  const games = names.length
    ? ["These games are set to use it:", ...names, "Steam will run them with its default Proton until you pick another one in their Properties."]
    : [];
  const everyGame = removal.global_default
    ? ["It is the Proton Steam uses for every game you didn't pick one for; Steam goes back to its own until you pick another."]
    : [];
  return { title: `Remove ${tool}?`, lines: [...games, ...everyGame], okLabel: "Remove anyway", removes: true, alert: false };
};
