import type {
  InstalledProton,
  InstalledProtonTool,
  ProtonBuildOption,
  ProtonGame,
  ProtonListing,
  ProtonMove,
  ProtonProblem,
  ProtonRemoval,
} from "../api";
import { ReleaseDownload, ReleaseRowView, actionOutcome, byteSize, downloadRows, listingMessage } from "./releases";
import { count, plural } from "./words";

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

/** A move under way, or how the last one went. */
export type MoveState = { target: string; busy: boolean; message: string | null } | null;

/** The rows offering to move an update's games to the newer build. */
export type MoveOfferView = {
  move: ProtonMove;
  text: string;
  moveLabel: string;
  keepLabel: string;
  enabled: boolean;
};

export type ProtonPageView = {
  summary: string;
  /** The row that restarts Steam, shown only when builds came or went since it started. */
  restart: boolean;
  moves: MoveOfferView[];
  /** How the last move went. */
  moveMessage: string | null;
  /** The dialogs open only when there is a Steam install to work with. */
  dialogsEnabled: boolean;
  hint: string;
};

/** The games to show: those with a name. One nothing names (not installed, and unknown to Steam's library) is left
 *  out; its appid alone says nothing. */
export const shownGames = (games: ProtonGame[]): ProtonGame[] => games.filter((game) => game.name);

const sortedNames = (games: ProtonGame[]): string[] => games.map((game) => game.name ?? "").sort((a, b) => a.localeCompare(b));

const moveOffer = (offer: ProtonMove, state: MoveState): MoveOfferView => {
  // Only the games the offer can name are moved and spoken of.
  const move = { ...offer, games: shownGames(offer.games) };
  const names = sortedNames(move.games).join(", ");
  const from = move.sources.join(", ");
  const busy = state?.busy === true;
  return {
    move,
    text: busy && state?.target === move.target
      ? `Moving ${count(move.games.length, "game", "games")} to ${move.target}…`
      : `${count(move.games.length, "game", "games")} still ${plural(move.games.length, "uses", "use")} ${from}: ${names}.`,
    moveLabel: `Move ${plural(move.games.length, "it", "them")} to ${move.target}`,
    keepLabel: move.sources.length === 1 ? `Keep ${plural(move.games.length, "it", "them")} on ${from}` : "Keep them where they are",
    enabled: !busy,
  };
};

export const protonPageView = (installed: InstalledProton | null, move: MoveState = null): ProtonPageView => {
  const base = { hint: CHOOSING_HINT, moves: [], moveMessage: move?.message ?? null };
  if (installed === null) return { ...base, summary: "Loading…", restart: false, dialogsEnabled: false };
  if (installed.problem) return { ...base, summary: problemText(installed.problem), restart: false, dialogsEnabled: false };
  // The device's own builds come newest first; the system's are Steam's to keep.
  const own = installed.tools.filter((tool) => !tool.system);
  return {
    ...base,
    summary: own.length
      ? `${count(own.length, "build", "builds")} installed. Newest: ${own[0].id}.`
      : "No Proton build is installed yet.",
    restart: installed.restart_needed,
    moves: installed.moves.map((offer) => moveOffer(offer, move)).filter((offer) => offer.move.games.length > 0),
    dialogsEnabled: true,
  };
};

/** How long Steam has to write a move into its config before the plugin says it didn't (Steam writes it after
 *  the call returns), and how often it looks meanwhile. */
export const MOVE_CONFIRM_MS = 10_000;
export const MOVE_POLL_MS = 1_000;

/** The games Steam's config doesn't show on the new build yet. */
export const unconfirmed = (appids: string[], onTarget: ProtonGame[]): string[] =>
  appids.filter((appid) => !onTarget.some((game) => game.appid === appid));

/** How a move went: all the games are on the new build, or which ones Steam didn't confirm. */
export const moveOutcome = (move: ProtonMove, pending: string[]): string => {
  if (pending.length === 0) return `Moved ${count(move.games.length, "game", "games")} to ${move.target}.`;
  const names = move.games.filter((game) => pending.includes(game.appid)).map((game) => game.name).join(", ");
  return `Steam hasn't confirmed the move of ${names}. Moving again is harmless.`;
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
  const shown = shownGames(tool.games).length;
  const games = shown ? `used by ${count(shown, "game", "games")}` : "no games";
  return tool.global_default ? `${games} · the default for all games` : games;
};

const describeTool = (tool: InstalledProtonTool): string => {
  if (tool.system) return "Installed system-wide · can't be removed here";
  const size = tool.size === null ? [] : [byteSize(tool.size)];
  return [tool.build_label ?? "Not installed by DeckyScaler", ...size, usedBy(tool)].join(" · ");
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
    usage: installed?.installed_bytes ? `Installed builds take ${byteSize(installed.installed_bytes)}.` : null,
    message: state.message ?? nothing,
  };
};

/** What the dialog says when a removal succeeded and the backend gave no words of its own. */
export const removeDone = (tool: string): string => `${tool} is removed.`;

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
  const shown = shownGames(removal.games);
  if (shown.length === 0 && !removal.global_default) {
    return { title: `Remove ${tool}?`, lines: ["No game uses it."], okLabel: "Remove", removes: true, alert: false };
  }
  const installed = sortedNames(shown.filter((game) => game.kind !== "unknown"));
  const elsewhere = sortedNames(shown.filter((game) => game.kind === "unknown"));
  const games = installed.length
    ? ["These games are set to use it:", ...installed, "Steam will run them with its default Proton until you pick another one in their Properties."]
    : [];
  const notInstalled = elsewhere.length
    ? [`Steam also keeps it as the choice for games that aren't installed: ${elsewhere.join(", ")}.`]
    : [];
  const everyGame = removal.global_default
    ? ["It is the Proton Steam uses for every game you didn't pick one for; Steam goes back to its own until you pick another."]
    : [];
  return { title: `Remove ${tool}?`, lines: [...games, ...notInstalled, ...everyGame], okLabel: "Remove anyway", removes: true, alert: false };
};
