import type { InstalledLibrary, InstalledVersion, PlacedLibrary } from "../api";
import { ProxyDllView, patchReady } from "./launch";
import { librariesLine } from "./libraries";
import { lines } from "./lines";
import { versionLabel } from "./releases";
import { listed, plural } from "./words";

/**
 * Patching needs an installed OptiScaler; looking at games, unpatching them and resetting
 * them to stock do not. Without it, the Patch buttons say so instead of the sections hiding.
 */
export const patchButton = (
  ready: boolean,
  readyLabel: string,
): { label: string; enabled: boolean } =>
  ready ? { label: readyLabel, enabled: true } : { label: "Patch: no OptiScaler version installed", enabled: false };

/** Whether games can be patched: some version is in the library. Null until the library has answered. */
export const libraryReady = (library: InstalledLibrary | null): boolean | null =>
  library === null ? null : library.versions.length > 0;

export type PatchChoiceView = {
  versionOptions: { data: string; label: string }[];
  versionId: string | null;
  versionHint: string | null;
  ready: boolean;
  /** The version id the patch calls send. */
  patchWith: string;
  /** Whether a game patched with it takes the user's libraries. */
  takesLibraries: boolean;
};

/**
 * What a patch will use: the picked version while it is installed, else the newest (the library
 * lists newest first). FSR 4's model is left to OptiScaler, which picks it for the GPU.
 */
export const patchChoice = (
  library: InstalledLibrary | null,
  picked: string | null,
): PatchChoiceView => {
  const versions = library?.versions ?? [];
  const byId = (id: string | null): InstalledVersion | undefined => versions.find((v) => v.id === id);
  const version = byId(picked) ?? versions[0];
  return {
    versionOptions: versions.map((v) => ({ data: v.id, label: `${versionLabel(v)} (${v.channel}${v.incomplete ? ", incomplete" : ""})` })),
    versionId: version?.id ?? null,
    versionHint: version ? null : "No OptiScaler version is downloaded. Open DeckyScaler → OptiScaler to download one.",
    ready: version !== undefined,
    patchWith: version?.id ?? "",
    takesLibraries: version?.libraries ?? false,
  };
};

/** How a game the launch wrapper patched is told apart: Unpatch alone doesn't keep it unpatched. */
export const WRAPPER_ROUTE = "Patched at each launch by the launch wrapper.";

/** Why to patch a game again that an earlier DeckyScaler set up for AMD's FSR 4 driver DLL through Proton: OptiScaler
 *  brings FSR 4 itself, and patching again takes the DLL's link and the launch option out. */
export const EARLIER_FSR4 =
  "Patched by an earlier DeckyScaler, which linked AMD's FSR 4 driver DLL from Proton: patch it again to take that out. OptiScaler brings FSR 4 itself.";

/** Why to verify a game in Steam before unpatching it: the game's own files its patch set aside lost their backup. */
export const lostBackups = (lost: string[]): string =>
  `The backup of ${lost.join(", ")} is gone: Unpatch can't put the game's own back. Verify the game's files in Steam first.`;

/** Why a game whose proxy file is there doesn't load OptiScaler: the game's own took the patch's place back. */
export const proxyTakenBack = (dll: string): string =>
  `The game's own ${dll} is back, after a verify or an update: patch it again.`;

/** What a patched game runs, and whether a later build of its channel is waiting in the library. */
export const gameVersionLine = (status: {
  patched?: boolean;
  optiscaler_version?: string | null;
  newer_version?: string | null;
  lacks_version_files?: boolean;
  version_incomplete?: boolean;
  by_wrapper?: boolean;
  changed_files?: string[];
  lost_backups?: string[];
  proxy_taken_back?: boolean;
  earlier_fsr4?: boolean;
  dll_name?: string | null;
} | null): string | null => {
  if (!status?.patched) return null;
  const notes = [
    ...(status.by_wrapper ? [WRAPPER_ROUTE] : []),
    ...(status.lost_backups?.length ? [lostBackups(status.lost_backups)] : []),
    ...(status.proxy_taken_back ? [proxyTakenBack(status.dll_name ?? "Its proxy")] : []),
    ...(status.earlier_fsr4 ? [EARLIER_FSR4] : []),
    ...(status.changed_files?.length ? ["Some of its files are gone or changed since the patch; patch again to put them back."] : []),
    ...(status.newer_version ? [`${status.newer_version} is in the library; choose it and patch again to update.`] : []),
    ...(status.version_incomplete ? ["This version is missing files; download it again from the OptiScaler page."] : []),
    ...(status.lacks_version_files ? ["This version has files the patch lacks; patch again to add them."] : []),
  ];
  return [`${status.optiscaler_version ?? "Unknown version"}${notes.length ? "." : ""}`, ...notes].join(" ");
};

/** What a game's patch uses: the proxy, the version id ("" lets the backend keep the game's version,
 *  else take the newest), and whether patching can run. */
export type PatchWith = { dllName: string; versionId: string; ready: boolean };

/** What the Quick Access panel's Patch uses: nothing to pick there, so a patched game keeps its proxy
 *  and version, and an unpatched one gets the default proxy and the newest version. */
export const quickPatchWith = (status: GameStatus | null, launch: ProxyDllView, versionReady: boolean): PatchWith => ({
  dllName: (status?.patched && status.dll_name) || launch.selected || "",
  versionId: "",
  ready: patchReady(versionReady, launch),
});

/** The FSR 4 a patched game's OptiScaler carries, as the backend reads it from its upscaler DLL; null off AMD. */
export type Fsr4 = {
  /** The upscaler DLL's version, which is FSR 4's: 4.1.2.4555. */
  version: string | null;
  models: Fsr4Model[];
};

export type Fsr4Model = "fp8" | "int8" | "int8-rdna2" | "int8-lite";

const FSR4_MODEL_NAMES: Record<Fsr4Model, string> = {
  fp8: "FP8",
  int8: "INT8",
  "int8-rdna2": "INT8 RDNA2",
  "int8-lite": "INT8 Lite",
};

/** How to tell FSR 4 rendering from FSR 3, on a line of its own: a GPU FSR 4 has no model for renders FSR 3 in its
 *  place. The setting and the in-game menu's switch turn on the watermark FSR 4 draws. FSR 4 reads it as the game
 *  starts, so the setting shows from the next launch; the in-game switch at once. */
const withWatermarkHint = (line: string) =>
  lines([
    line,
    "To see FSR 4 render rather than FSR 3: turn on Fsr4EnableWatermark in OptiScaler settings before launching, or Watermark in OptiScaler's in-game menu, and FSR 4 shows its watermark in the game.",
  ]);

/** What the panel says about FSR 4 for a patched game: the FSR 4 its OptiScaler carries, with which models (OptiScaler
 *  picks the GPU's), and how to see it render; or that it carries none. */
export const fsr4Line = (fsr4: Fsr4 | null | undefined): string | null => {
  if (!fsr4) return null;
  if (fsr4.models.length === 0) return "This game's OptiScaler has no FSR 4.";
  // The version is FSR 4's own (4.1.2.4555, shown as FSR 4.1.2): the build number tells the user nothing.
  const name = fsr4.version ? `FSR ${fsr4.version.split(".").slice(0, 3).join(".")}` : "FSR 4";
  const models = listed(fsr4.models.map((model) => FSR4_MODEL_NAMES[model]));
  return withWatermarkHint(
    `${name} comes with this game's OptiScaler, with the ${models} ${plural(fsr4.models.length, "model", "models")}: OptiScaler picks the one for this GPU.`,
  );
};

/** A Steam game's status as get_game_status reports it. */
export type GameStatus = {
  status: "success" | "error";
  message?: string;
  name?: string;
  install_found?: boolean;
  patched?: boolean;
  dll_name?: string | null;
  /** Whether the launch wrapper patched it, at a start: it patches it again at each one. */
  by_wrapper?: boolean;
  /** What its marker is: DeckyScaler's record (whole, unfinished, or damaged), or the original Decky Framegen's. */
  record?: "ok" | "incomplete" | "damaged" | "upstream" | null;
  optiscaler_version?: string | null;
  newer_version?: string | null;
  /** Its version holds files its patch didn't place: patching again adds them. */
  lacks_version_files?: boolean;
  /** Files its patch placed, other than the proxy, that are gone or not as placed. */
  changed_files?: string[];
  /** The game's own files its patch set aside whose backup is gone. */
  lost_backups?: string[];
  /** The game's own file is back where the patch linked its proxy. */
  proxy_taken_back?: boolean;
  /** An earlier DeckyScaler set it up for AMD's FSR 4 driver DLL: patching again takes that out. */
  earlier_fsr4?: boolean;
  /** Files a game gets from its version are gone from the version: downloading it again brings them back. */
  version_incomplete?: boolean;
  fsr4?: Fsr4 | null;
  /** The user's libraries its patch placed. */
  libraries?: PlacedLibrary[];
};

export type StatusTone = "neutral" | "warning" | "good";

/** The colour a status line takes for its tone; plain text for neutral. */
export const toneColor = (tone: StatusTone): string | null =>
  tone === "warning" ? "#ffd866" : tone === "good" ? "#3fb950" : null;

export type SteamGameView = {
  status: { text: string; tone: StatusTone };
  versionLine: string | null;
  fsr4Line: string | null;
  /** The user's libraries the game's patch placed. */
  librariesLine: string | null;
  patch: { label: string; enabled: boolean };
  unpatchVisible: boolean;
  unpatch: { label: string; enabled: boolean };
};

/** What the Steam game patcher shows for the picked game, and which of its actions can run. */
export const steamGameView = (s: {
  gameSelected: boolean;
  status: GameStatus | null;
  statusLoading: boolean;
  busy: "patch" | "unpatch" | null;
  dllName: string;
  ready: boolean;
}): SteamGameView => {
  const { status, busy, dllName } = s;
  const otherDll = Boolean(status?.patched && status.dll_name && status.dll_name !== dllName);
  const dllLabel = status?.dll_name || "unknown";

  const statusLine = ((): SteamGameView["status"] => {
    if (!s.gameSelected) return { text: "—", tone: "neutral" };
    if (s.statusLoading) return { text: "Loading...", tone: "neutral" };
    if (!status || status.status === "error") return { text: status?.message || "—", tone: "neutral" };
    if (!status.install_found) return { text: "Install not found", tone: "warning" };
    if (!status.patched) return { text: "Not patched", tone: "neutral" };
    if (status.record === "damaged") return { text: "Patched, but its record is damaged: repair it", tone: "warning" };
    if (status.record === "upstream") return { text: "Patched by Decky Framegen", tone: "warning" };
    if (status.earlier_fsr4) return { text: `Patched (${dllLabel}) — patch it again`, tone: "warning" };
    if (otherDll) return { text: `Patched (${dllLabel}) — switch available`, tone: "warning" };
    return { text: `Patched (${dllLabel})`, tone: "good" };
  })();

  const patchLabel = ((): string => {
    if (busy === "patch") return "Patching...";
    if (!s.gameSelected) return "Patch this game";
    if (!status?.install_found) return "Install not found";
    if (status?.record === "damaged") return `Repair (${dllName})`;
    if (otherDll) return `Switch to ${dllName}`;
    if (status?.patched) return `Reinstall (${dllName})`;
    return `Patch with ${dllName}`;
  })();
  const patch = patchButton(s.ready, patchLabel);
  const canPatch = s.gameSelected && Boolean(status?.install_found) && busy === null;

  return {
    status: statusLine,
    versionLine: gameVersionLine(s.statusLoading ? null : status),
    fsr4Line: s.statusLoading ? null : fsr4Line(status?.fsr4),
    librariesLine: s.statusLoading || !status?.patched ? null : librariesLine(status.libraries),
    patch: { label: patch.label, enabled: patch.enabled && canPatch },
    // A damaged record undoes nothing: it is repaired first.
    unpatchVisible: Boolean(status?.patched) && status?.record !== "damaged",
    unpatch: { label: busy === "unpatch" ? "Unpatching..." : "Unpatch this game", enabled: busy === null },
  };
};

/** The Steam game picker in the Quick Access panel. */
export const gamePickerView = (
  games: { appid: string; name: string; install_found?: boolean }[],
  loading: boolean,
): { placeholder: string; enabled: boolean; options: { data: string; label: string }[] } => ({
  placeholder: loading ? "Loading games..." : games.length ? "Choose a game" : "No Steam games found",
  enabled: !loading && games.length > 0,
  options: games.map((g) => ({ data: g.appid, label: g.install_found === false ? `${g.name} (not installed)` : g.name })),
});

/** A game page's title: the game's name once its status has said it. */
export const gamePageTitle = (status: GameStatus | null): string => status?.name ?? "Loading…";

/** The game the panel shows once the games are listed: the one picked last while it is still installed,
 *  else the first; "" when there are none. */
export const gameToShow = (games: { appid: string }[], lastPicked: string): string =>
  games.some((g) => g.appid === lastPicked) ? lastPicked : games[0]?.appid ?? "";
