import { callable } from "@decky/api";

export const listInstalledGames = callable<
  [],
  { status: string; message?: string; games: { appid: string; name: string; install_found?: boolean }[] }
>("list_installed_games");

export const logError = callable<[string], void>("log_error");

/** Where the pickers start (Patcher.path_defaults): home; the first Steam library's games; Downloads, or home
 *  when there is none. The backend always answers all three. */
export type PathDefaults = { home: string; steam_common: string; downloads: string };

export const getPathDefaults = callable<[], PathDefaults>("get_path_defaults");

export const runManualPatch = callable<
  [directory: string, dll_name: string, version_id: string],
  {
    status: string;
    message?: string;
    output?: string;
    optiscaler_version?: string | null;
  }
>("manual_patch_directory");

export const runManualUnpatch = callable<[directory: string, confirmed_reset: boolean], UnpatchResult>(
  "manual_unpatch_directory"
);

export const getGameStatus = callable<
  [appid: string],
  {
    status: string;
    message?: string;
    appid?: string;
    name?: string;
    install_found?: boolean;
    patched?: boolean;
    dll_name?: string | null;
    target_dir?: string | null;
    patched_at?: string | null;
    optiscaler_version?: string | null;
    /** A later build of the game's version channel that is in the library. */
    newer_version?: string | null;
    /** Its version holds files its patch didn't place (they came back since): patching again adds them. */
    lacks_version_files?: boolean;
    /** Files a game gets from its version are gone from the version: downloading it again brings them back. */
    version_incomplete?: boolean;
  }
>("get_game_status");

/** What the panel offers for starting a game; the backend builds every launch string. */
export type LaunchSetup = {
  default: string;
  proxies: { name: string; hint: string; launch_options: string }[];
  wrapper: { patch: string; unpatch: string };
};
export const launchSetup = callable<[], LaunchSetup>("launch_setup");

export const patchGame = callable<
  /** current_launch_options is null when Steam didn't say what they are. */
  [appid: string, dll_name: string, current_launch_options: string | null, version_id: string],
  {
    status: string;
    message?: string;
    appid?: string;
    name?: string;
    dll_name?: string;
    target_dir?: string;
    launch_options?: string;
    original_launch_options?: string;
    optiscaler_version?: string | null;
  }
>("patch_game");

export const unpatchGame = callable<
  [appid: string, current_launch_options: string, confirmed_reset: boolean],
  UnpatchResult
>("unpatch_game");

// ── OptiScaler library ───────────────────────────────────────────────────────

export type LibraryChannel = "stable" | "nightly";

/** An installed version as patching offers it. */
export type InstalledVersion = {
  id: string;
  version: string;
  channel: LibraryChannel;
  date: string;
  /** Bytes on disk. */
  size: number;
  /** Whether a game patched with it takes the user's libraries (OptiScaler 10 does). */
  libraries: boolean;
  /** Files it was unpacked with are gone from it: Download again brings them back. */
  incomplete: boolean;
};

/** What is left of a version that isn't whole, by its directory's name: no game can be patched with it, and it can
 *  only be removed (Download versions brings it back). */
export type DamagedVersion = { id: string; size: number };

/** The downloaded versions, newest first, what is left of damaged ones, and what all of it takes on disk. */
export type InstalledLibrary = { versions: InstalledVersion[]; damaged: DamagedVersion[]; installed_bytes: number };

/** Why a release can't be downloaded (the backend's kinds; presentation/releases.ts words them). */
export type ReleaseReason =
  | "uploading"
  | "no-checksum"
  | "elsewhere"
  | "no-archive"
  | "several-archives"
  | "unknown-family";

/** A published release as a download dialog lists it: an OptiScaler version or a Proton build. */
export type ReleaseVersion = {
  id: string;
  version: string;
  /** YYYYMMDD; empty when unknown (an installed build no longer listed). */
  date: string;
  state: "installed" | "available" | "unsupported";
  /** Why an unsupported release can't be downloaded. */
  reason: ReleaseReason | null;
  /** Bytes on disk when installed, the download's size otherwise. */
  size: number;
};

export type LibraryVersion = ReleaseVersion & { family: string | null };

export type LibraryListing =
  | { status: "success"; versions: LibraryVersion[]; listing_error: string | null }
  | { status: "error"; message: string };

type LibraryResult = { status: "success"; message?: string } | { status: "error"; message: string };

export const libraryInstalled = callable<[], InstalledLibrary>("library_installed");
export const libraryVersions = callable<[channel: LibraryChannel], LibraryListing>("library_versions");
/** Download progress arrives as "library_download" events: version id, bytes received, total bytes or null. */
export const libraryInstall = callable<[channel: LibraryChannel, version_id: string], LibraryResult>("library_install");
export const libraryReinstall = callable<[version_id: string], LibraryResult>("library_reinstall");
export const libraryRemove = callable<[version_id: string], LibraryResult>("library_remove");
/** What removing a version would come to: why it can't be removed, or null when it can. */
export type LibraryRemoval = { status: "success"; refused: string | null };
export const libraryRemoval = callable<[version_id: string], LibraryRemoval>("library_removal");

// ── Proton builds ────────────────────────────────────────────────────────────

/** A build the download dialog offers (GE-Proton, Proton-CachyOS and its x86_64_v3 variant). */
export type ProtonBuildOption = { id: string; label: string; note: string | null };

/** Why there is no Steam install to work with: none has run here, or several have and none is running. */
export type ProtonProblem = "no-steam" | "several-steams";

/** A game whose user chose a build; `name` is null when nothing on the device names it any more. */
export type ProtonGame = { appid: string; name: string | null; kind: "steam" | "shortcut" | "unknown" };

/** A compatibility tool Steam would find, whoever installed it. */
export type InstalledProtonTool = {
  id: string;
  /** The build it is (GE-Proton, Proton-CachyOS…), or null for any other tool. */
  build: string | null;
  build_label: string | null;
  /** Installed for every user of the device: listed, never removed here. */
  system: boolean;
  /** A link to a build kept elsewhere (an SD card): listed as a build, never removed here. */
  linked: boolean;
  /** Bytes on disk, when asked for (sizing walks thousands of files). */
  size: number | null;
  games: ProtonGame[];
  /** The tool Steam uses for every game the user didn't pick one for. */
  global_default: boolean;
};

/** A folder in compatibilitytools.d that isn't a build: what it takes, and the games Steam still maps to its name. */
export type ProtonOther = Pick<InstalledProtonTool, "id" | "size" | "games" | "global_default">;

/** Games an update left on older builds of a build, to move to the newer one now that Steam lists it. */
export type ProtonMove = { build: string; target: string; sources: string[]; games: ProtonGame[] };

export type InstalledProton = {
  status: "success";
  problem: ProtonProblem | null;
  /** The device's own newest first, then the system's. */
  tools: InstalledProtonTool[];
  /** The device's own folders in compatibilitytools.d that aren't builds Steam would list (no manifest declaring
   *  one), listed to remove; sized only when asked, as builds are. */
  others: ProtonOther[];
  installed_bytes: number | null;
  /** Builds came or went since Steam started: it lists them only after a restart. */
  restart_needed: boolean;
  moves: ProtonMove[];
};

export type ProtonListing =
  | { status: "success"; problem: ProtonProblem | null; versions: ReleaseVersion[]; listing_error: string | null }
  | { status: "error"; message: string };

type ProtonResult =
  | { status: "success"; message?: string }
  | { status: "error"; message?: string; problem?: ProtonProblem };

export type ProtonRemoval =
  | { status: "success"; games: ProtonGame[]; global_default: boolean }
  | { status: "error"; message?: string; problem?: ProtonProblem };

// ── The user's libraries ──────────────────────────────────────────────────────

/** What a library serves in a game (the backend's slots, in its order). */
export type LibrarySlot = "upscaler" | "frame-generation";

export type UserLibrary = {
  id: string;
  label: string;
  origin: "downloaded" | "file";
  slots: LibrarySlot[];
  /** The slots picking it switches on by itself; in the others it is only pointed at. */
  turns_on: LibrarySlot[];
  /** Whether it goes into every patched game, picked or not, for OptiScaler's own menu to offer (a provider). */
  in_menu: boolean;
  /** Bytes on the device. */
  size: number;
  /** The games whose patch placed it, picked or offered. */
  games: string[];
};

/** What is left of a library whose files or entry went missing: it no longer goes into games, and can only be removed. */
export type DamagedLibrary = { id: string; label: string; size: number };

export type UserLibraries = {
  libraries: UserLibrary[];
  damaged: DamagedLibrary[];
  slots: LibrarySlot[];
  /** The library picked for every game, per slot. */
  global: Partial<Record<LibrarySlot, string>>;
  /** The slots whose global pick can't go into games: an earlier slot's library names one of its providers. */
  left_out: LibrarySlot[];
  /** The slots whose global pick names a library that isn't on the device (damaged, or gone): nothing goes in. */
  missing: LibrarySlot[];
  /** The patched games a patch now would give other libraries. */
  to_apply: string[];
  /** What the libraries and the damaged ones take on the device. */
  installed_bytes: number;
};

/** A library a game's patch placed, as its status says: picked for a slot, or (slot null) only there to pick in
 *  OptiScaler's menu. */
export type PlacedLibrary = { slot: LibrarySlot | null; id: string; label: string };

/** Where libraries are downloaded from: what its library serves, and the GitHub repository it comes from. */
export type LibrarySource = { id: string; label: string; slots: LibrarySlot[]; repository: string };

/** Why what the user picked isn't added (the backend's kinds; presentation/libraries.ts words them). */
export type LibraryRefusal = "nothing-known" | "reserved-name" | "already-added";

export type UserLibraryResult =
  | { status: "success"; id?: string; message?: string; in_menu?: boolean }
  | { status: "error"; message?: string; reason?: LibraryRefusal };

export type UserLibraryListing =
  | { status: "success"; versions: ReleaseVersion[]; listing_error: string | null }
  | { status: "error"; message: string };

export type UserLibraryRemoval =
  | { status: "success"; games: string[]; global: boolean }
  | { status: "error"; message: string };

export type LibrariesApplied = {
  status: "success";
  /** A Steam game's launch options are Steam's to set: the frontend sets them. */
  applied: { name: string; appid: string; launch_options: string | null }[];
  skipped: string[];
  failed: { name: string; message: string }[];
  /** Patched games on a drive that isn't mounted: whether they need the libraries can't be read. */
  away: string[];
};

/** A game's own choice per slot (a library, "none", or absent: it follows the global choice), what that comes to,
 *  and whether the game, patched, has other libraries than that. */
export type GameLibraryChoice = {
  status: "success";
  own: Partial<Record<LibrarySlot, string>>;
  resolved: Partial<Record<LibrarySlot, string>>;
  /** The slots whose resolved pick can't go into the game: an earlier slot's library names one of its providers. */
  left_out: LibrarySlot[];
  /** The slots whose resolved pick names a library that isn't on the device (damaged, or gone): nothing goes in. */
  missing: LibrarySlot[];
  pending: boolean;
};

export const userLibrarySources = callable<[], LibrarySource[]>("user_library_sources");
export const userLibrariesInstalled = callable<[], UserLibraries>("user_libraries_installed");
export const userLibraryGameChoice = callable<[appid: string], GameLibraryChoice>("user_library_game_choice");
export const userLibraryVersions = callable<[source: string], UserLibraryListing>("user_library_versions");
/** Download progress arrives as "user_library_download" events: release id, bytes received, total bytes or null. */
export const userLibraryInstall = callable<[source: string, release_id: string], UserLibraryResult>("user_library_install");
export const userLibraryAdd = callable<[path: string], UserLibraryResult>("user_library_add");
export const userLibraryRemoval = callable<[library_id: string], UserLibraryRemoval>("user_library_removal");
export const userLibraryRemove = callable<[library_id: string], { status: string; message?: string }>("user_library_remove");
/** `scope` is "global" or a game's appid; `value` a library, "none", or null (a game follows the global choice).
 *  A saved choice names the patched games it reaches that don't have their libraries yet. */
export const userLibraryChoose = callable<
  [scope: string, slot: LibrarySlot, value: string | null],
  { status: string; message?: string; to_apply?: string[] }
>("user_library_choose");
export const userLibrariesApply = callable<[], LibrariesApplied>("user_libraries_apply");

export const protonBuildOptions = callable<[], ProtonBuildOption[]>("proton_build_options");
export const protonInstalled = callable<[with_sizes?: boolean], InstalledProton>("proton_installed");
export const protonVersions = callable<[build: string], ProtonListing>("proton_versions");
/** Download progress arrives as "proton_download" events: tool name, bytes received, total bytes or null. */
export const protonInstall = callable<[build: string, tool: string], ProtonResult>("proton_install");
export const protonRemoval = callable<[tool: string], ProtonRemoval>("proton_removal");
export const protonRemove = callable<[tool: string], ProtonResult>("proton_remove");
/** These games were moved to `target`: offered no more. */
export const protonMoved = callable<[target: string, appids: string[]], { status: "success" }>("proton_moved");
/** The games stay where they are: the move to `target` is offered no more. */
export const protonKeep = callable<[target: string], { status: "success" }>("proton_keep");
/** The games whose user chose a tool now, as Steam's config says. */
export const protonGames = callable<
  [tool: string],
  { status: "success"; games: ProtonGame[] } | { status: "error"; problem?: ProtonProblem; message?: string }
>("proton_games");

// ── Development builds ───────────────────────────────────────────────────────

/** The arguments of Decky Loader's `utilities/install_plugin`, prepared by the backend. */
export type DeckyInstallRequest = [artifact: string, name: string, version: string, hash: string, installType: number];

/** The running build: known when its package says where it came from, so it can update itself. */
export type PluginBuild =
  | { known: false; version: string; message: string }
  | {
      known: true;
      channel: string;
      commit: string;
      short_commit: string;
      title: string;
      version: string;
      is_dev_build: boolean;
      /** Development builds are offered; always on in a development build. */
      developer_mode: boolean;
    };

/** The newest release and what it means for the running build: an update, a switch from a development
 *  build, or nothing. */
export type LatestStable =
  | {
      status: "success";
      release: { version: string; title: string; published_at: string } | null;
      offer: "update" | "switch" | "none";
    }
  | { status: "error"; message: string };

export type InstallRequestAnswer =
  | { status: "success"; install_request: DeckyInstallRequest }
  | { status: "error"; message: string };

export const pluginBuild = callable<[], PluginBuild>("plugin_build");

export const setDeveloperMode = callable<[on: boolean], { status: "success"; developer_mode: boolean } | { status: "error"; message: string }>(
  "set_developer_mode",
);

export const latestStable = callable<[], LatestStable>("latest_stable");

/** Asked at install time, in case a newer release came out since the check. */
export const stableInstallRequest = callable<[], InstallRequestAnswer>("stable_install_request");

export type AvailableDevBuild = {
  channel: string;
  commit: string;
  short_commit: string;
  title: string;
  published_at: string;
  state: "installed" | "available";
};

export type DevBuildList =
  | { status: "success"; builds: AvailableDevBuild[] }
  | { status: "error"; message: string };

export const listDevBuilds = callable<[], DevBuildList>("list_dev_builds");

/** Asked at install time: a channel's build is replaced on every push and the old download is gone. */
export const devInstallRequest = callable<[channel: string], InstallRequestAnswer>("dev_install_request");

/** The backend's event for a build's download: channel, bytes received, total bytes if known. */
export const PLUGIN_DOWNLOAD_EVENT = "plugin_download";

// ── Unpatching ───────────────────────────────────────────────────────────────

/** What Unpatch will do: undo the patch record (nothing to confirm), or, for a Decky Framegen
 *  version's patch, a reset the user confirms after seeing what it changes. */
export type UnpatchPreview =
  | { status: "success"; mode: "record"; target_dir: string; name?: string }
  | {
      status: "success";
      mode: "reset";
      target_dir: string;
      evidence: "marker" | "backups" | "leftovers";
      remove: string[];
      restore: string[];
      unrecoverable: string[];
      /** The launch options to set afterwards; null leaves them as they are. */
      launch_options: string | null;
      name?: string;
    }
  | { status: "error"; message: string };

export type UnpatchResult =
  | { status: "success"; message?: string; launch_options?: string | null }
  | { status: "error"; message: string };

export const previewUnpatchGame = callable<[appid: string, current_launch_options: string], UnpatchPreview>(
  "preview_unpatch_game"
);
export const previewUnpatchDirectory = callable<[directory: string], UnpatchPreview>("preview_unpatch_directory");

// ── OptiScaler settings ──────────────────────────────────────────────────────

/** Where a setting's value comes from: OptiScaler's default ("auto"), the global settings or the game's own. */
export type SettingSource = "default" | "global" | "game" | "library";

/** A setting as a version's OptiScaler.ini describes it, with its value for the page asked for. */
export type SettingInfo = {
  key: string;
  kind: "bool" | "enum" | "number" | "text";
  description: string;
  help: string;
  /** OptiScaler's default as an ini value; null when its comment states it only in prose. */
  default: string | null;
  choices: { value: string; label: string }[];
  minimum: number | null;
  maximum: number | null;
  integer: boolean;
  value: string;
  source: SettingSource;
  /** The library that sets it, for a value whose source is "library". */
  library: string | null;
  /** The value without the page's own: global for a game's page, auto for the global page. */
  inherited: { value: string; source: SettingSource };
};

export type SettingsSection = { name: string; settings: SettingInfo[] };

export type SettingsAnswer = {
  status: string;
  message?: string;
  version?: string;
  sections?: SettingsSection[];
  /** "Section.Key" the layer sets that this version doesn't have or doesn't take the value of. */
  unsupported?: string[];
  /** Only for a game. */
  name?: string;
  patched?: boolean;
  running?: boolean;
};

export const globalSettings = callable<[], SettingsAnswer>("global_settings");

export const gameSettings = callable<[appid: string], SettingsAnswer>("game_settings");

/** scope is "global" or an appid; a null value clears it, so the layer below shows through. */
export const setSetting = callable<
  [scope: string, section: string, key: string, value: string | null],
  { status: string; message?: string; skipped?: string[]; away?: string[] }
>("set_setting");

export const resetGameSettings = callable<[appid: string], { status: string; message?: string }>("reset_game_settings");

/** Writes a game's settings once it has closed; applied is false when it isn't patched or still runs. */
export const gameClosed = callable<[appid: string], { status: string; applied?: boolean }>("game_closed");

// ── Patched games ────────────────────────────────────────────────────────────

/** A game or directory the plugin patched; appid is "" for a directory patched by path. */
export type PatchedGame = {
  directory: string;
  name: string;
  appid: string;
  dll_name: string;
  dll_present: boolean;
  version_id: string | null;
  /** A later build of the game's version channel that is in the library. */
  newer_version: string | null;
  /** Its version holds files its patch didn't place (they came back since): patching again adds them. */
  lacks_version_files: boolean;
  /** Files a game gets from its version are gone from the version: downloading it again brings them back. */
  version_incomplete: boolean;
  patched_at: string | null;
  /** Its marker's record: whole, stopped before the last file, or damaged (patching again repairs it). */
  record: "ok" | "incomplete" | "damaged";
  own_settings: boolean;
};

/** A patched game on a drive that isn't mounted: its patch can't be read until the drive is back. */
export type AwayGame = { directory: string; name: string };

export type PatchedGames = { status: string; message?: string; games?: PatchedGame[]; away?: AwayGame[] };

export const patchedGames = callable<[], PatchedGames>("patched_games");
/** Drops a game on a drive that won't be back from the patched games, so its version can be removed. */
export const forgetPatched = callable<[directory: string], { status: string; message?: string }>("forget_patched");
