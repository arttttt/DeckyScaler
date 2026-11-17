import type {
  GameLibraryChoice,
  LibraryRefusal,
  LibrarySlot,
  LibrarySource,
  LibrariesApplied,
  PlacedLibrary,
  UserLibraries,
  UserLibrary,
  UserLibraryListing,
  UserLibraryRemoval,
  UserLibraryResult,
} from "../api";
import { ReleaseDownload, ReleaseRowView, byteSize, downloadRows, listingMessage } from "./releases";
import { count, plural } from "./words";

/**
 * The user's libraries, shaped like the OptiScaler versions block: a summary, a choice per slot for every game,
 * dialogs to download, add and manage them, and an offer to apply a new choice to the games already patched.
 * The slots and what each library serves come from the backend; this file only words them.
 */

/** A slot's choice of no library (for every game: OptiScaler's settings decide). */
export const NONE = "none";
/** A game's choice that follows the global one. */
export const FOLLOW = "\u0000global";

const SLOT_LABELS: Record<LibrarySlot, string> = {
  upscaler: "Upscaler",
  "frame-generation": "Frame generation",
};

/** A slot's name; a slot this frontend doesn't know yet as it came. */
export const slotLabel = (slot: LibrarySlot): string => SLOT_LABELS[slot] ?? slot;

const NOT_SET = "From OptiScaler settings";

/** The picks a library can be for a slot: those it serves. */
const serving = (libraries: UserLibrary[], slot: LibrarySlot): { data: string; label: string }[] =>
  libraries.filter((library) => library.slots.includes(slot)).map((library) => ({ data: library.id, label: library.label }));

const labelOf = (libraries: UserLibrary[], id: string | undefined): string =>
  libraries.find((library) => library.id === id)?.label ?? NOT_SET;

/** What to know of a library picked for a slot it doesn't switch on by itself: OptiScaler's own settings do. */
const ONLY_POINTED: Partial<Record<LibrarySlot, string>> = {
  "frame-generation": "Uses its files. Frame generation itself is turned on in OptiScaler settings: FGInput and FGOutput.",
};

const hintFor = (libraries: UserLibrary[], slot: LibrarySlot, id: string | undefined): string | null => {
  const library = libraries.find((item) => item.id === id);
  return library && !library.turns_on.includes(slot) ? ONLY_POINTED[slot] ?? null : null;
};

// ── The block on the OptiScaler page ─────────────────────────────────────────

export type SlotPicker = {
  slot: LibrarySlot;
  label: string;
  options: { data: string; label: string }[];
  selected: string;
  enabled: boolean;
  hint: string | null;
};

export type LibrariesBlockView = {
  summary: string;
  /** Every game's choice, per slot; none until the libraries have answered. */
  pickers: SlotPicker[];
  /** Patched games a patch now would change, and the button that does it. */
  apply: { text: string; label: string; enabled: boolean } | null;
  message: string | null;
};

export type LibrariesBlockState = {
  installed: UserLibraries | null;
  /** Applying the choice to patched games, or saving a choice. */
  busy: boolean;
  /** What the last action came to; cleared by the next one. */
  message: string | null;
};

export const librariesSummary = (installed: UserLibraries | null): string => {
  if (installed === null) return "Loading…";
  if (installed.libraries.length === 0) return "No library is added yet.";
  return `${count(installed.libraries.length, "library", "libraries")} added. Games on OptiScaler 10 get the ones picked here unless they have their own.`;
};

export const librariesBlockView = (state: LibrariesBlockState): LibrariesBlockView => {
  const { installed, busy } = state;
  const libraries = installed?.libraries ?? [];
  const pending = installed?.to_apply ?? [];
  return {
    summary: librariesSummary(installed),
    pickers: (installed?.slots ?? []).map((slot) => ({
      slot,
      label: slotLabel(slot),
      options: [{ data: NONE, label: NOT_SET }, ...serving(libraries, slot)],
      selected: installed?.global[slot] ?? NONE,
      enabled: !busy,
      hint: hintFor(libraries, slot, installed?.global[slot]),
    })),
    apply: pending.length
      ? {
          text: `${count(pending.length, "patched game", "patched games")} ${plural(pending.length, "doesn't", "don't")} have the libraries picked for it yet: ${pending.join(", ")}.`,
          label: busy ? "Applying…" : `Apply to ${plural(pending.length, "it", "them")}`,
          enabled: !busy,
        }
      : null,
    message: state.message,
  };
};

/** What saving a choice came to: nothing to say once saved, else why it wasn't. */
export const chooseOutcome = (answer: { status: string; message?: string } | null): string | null =>
  answer?.status === "success" ? null : answer?.message ?? "The plugin backend did not answer.";

/** The Steam games applying patched again, with the launch options Steam is to set for them. */
export const launchOptionsToSet = (answer: LibrariesApplied | null): { appid: number; options: string }[] =>
  (answer?.applied ?? []).flatMap((game) =>
    game.appid && game.launch_options !== null ? [{ appid: Number(game.appid), options: game.launch_options }] : [],
  );

/** What applying the choice came to: the games patched again, those left alone while running, those that failed. */
export const applyOutcome = (answer: LibrariesApplied | null): string => {
  if (answer === null) return "The plugin backend did not answer.";
  const lines = [
    ...(answer.applied.length ? [`Applied to ${answer.applied.map((game) => game.name).join(", ")}.`] : []),
    ...(answer.skipped.length
      ? [`Skipped ${answer.skipped.join(", ")}: ${plural(answer.skipped.length, "it's", "they're")} running. Apply again once closed.`]
      : []),
    ...answer.failed.map((game) => `Couldn't apply to ${game.name}: ${game.message}`),
  ];
  return lines.length ? lines.join(" ") : "Nothing to apply.";
};

// ── Download dialog ──────────────────────────────────────────────────────────

export type LibraryDownloadState = {
  sources: LibrarySource[];
  source: string | null;
  listing: UserLibraryListing | null;
  checking: boolean;
  busy: string | null;
  download: ReleaseDownload | null;
  message: string | null;
};

export type LibraryDownloadView = {
  sourceOptions: { data: string; label: string }[];
  source: string | null;
  /** One source is a line to read, more a list to pick from. */
  sourceChoosable: boolean;
  sourceLabel: string;
  sourceEnabled: boolean;
  checkLabel: string;
  checkEnabled: boolean;
  rows: ReleaseRowView[];
  message: string | null;
};

/** The source the dialog opens on: the first the backend offers. */
export const firstSource = (sources: LibrarySource[] | null): string | null => sources?.[0]?.id ?? null;

export const libraryDownloadView = (state: LibraryDownloadState): LibraryDownloadView => {
  const { listing, checking, busy } = state;
  const idle = busy === null;
  const label = state.sources.find((source) => source.id === state.source)?.label ?? "this library";
  return {
    sourceOptions: state.sources.map((source) => ({ data: source.id, label: source.label })),
    source: state.source,
    sourceChoosable: state.sources.length > 1,
    sourceLabel: label,
    sourceEnabled: idle,
    checkLabel: checking ? "Checking…" : "Check for new versions",
    checkEnabled: !checking && idle,
    rows: listing?.status === "success" ? downloadRows(listing.versions, busy, state.download) : [],
    message: state.message ?? listingMessage(listing, label, `No ${label} releases are published.`),
  };
};

// ── Adding the user's own ────────────────────────────────────────────────────

export const ADD_HINT =
  "Pick a library's zip, its folder, or a DLL. Files you downloaded in Desktop Mode are in Downloads; a USB drive is under /run/media.";

const REFUSALS: Record<LibraryRefusal, string> = {
  "nothing-known":
    "DeckyScaler found no library in it. It takes a provider folder (with ffx, dlssg… inside) or DLLs OptiScaler loads, such as libxess.dll.",
  "reserved-name": "Its provider is named like one of OptiScaler's own choices, which OptiScaler would take instead.",
  "already-added": "It is already added.",
};

/** Why what the user picked isn't a library, in words; a reason this frontend doesn't know yet as it came. */
export const refusalText = (reason: LibraryRefusal): string => REFUSALS[reason] ?? reason;

/** What adding came to: the backend's words, why it isn't a library, or that the backend didn't answer. */
export const addOutcome = (answer: UserLibraryResult | null): string => {
  if (answer === null) return "The plugin backend did not answer.";
  if (answer.status === "error" && answer.reason) return refusalText(answer.reason);
  return answer.message ?? (answer.status === "success" ? "The library is added." : "Adding it failed.");
};

/** Where the picker opens, in order of trying: the Downloads folder files from Desktop Mode land in, then home;
 *  the picker's own start while the home isn't known yet. */
export const pickerStarts = (home: string | null): string[] => (home ? [`${home}/Downloads`, home] : ["/"]);

// ── Manage dialog ────────────────────────────────────────────────────────────

export type LibraryManageState = {
  installed: UserLibraries | null;
  busy: string | null;
  message: string | null;
};

export type LibraryManageView = { rows: ReleaseRowView[]; usage: string | null; message: string | null };

const ORIGINS: Record<UserLibrary["origin"], string> = { downloaded: "downloaded", file: "your file" };

const describeLibrary = (library: UserLibrary): string => {
  // "Upscaler, frame generation": a sentence, its first slot capitalised.
  const serves = library.slots.map((slot, index) => (index === 0 ? slotLabel(slot) : slotLabel(slot).toLowerCase())).join(", ");
  const used = library.games.length ? `used by ${count(library.games.length, "game", "games")}` : "no games";
  return [serves, ORIGINS[library.origin] ?? library.origin, byteSize(library.size), used].join(" · ");
};

export const libraryManageView = (state: LibraryManageState): LibraryManageView => {
  const { installed, busy } = state;
  const libraries = installed?.libraries ?? [];
  return {
    rows: libraries.map((library) => ({
      id: library.id,
      label: library.label,
      description: busy === library.id ? "Removing…" : describeLibrary(library),
      action: { label: "Remove", enabled: busy === null },
    })),
    usage: installed?.installed_bytes ? `Libraries take ${byteSize(installed.installed_bytes)}.` : null,
    message: state.message ?? (installed && libraries.length === 0 ? "No library is added yet." : null),
  };
};

export type LibraryRemoveConfirmation = { title: string; lines: string[]; okLabel: string; removes: boolean; alert: boolean };

/** The removal question: who has the library (each keeps its copy until patched again), or why it can't be asked. */
export const libraryRemoveConfirmation = (label: string, removal: UserLibraryRemoval | null): LibraryRemoveConfirmation => {
  if (removal === null || removal.status === "error") {
    return {
      title: `Can't remove ${label}`,
      lines: [removal?.message ?? "The plugin backend did not answer."],
      okLabel: "OK",
      removes: false,
      alert: true,
    };
  }
  if (removal.games.length === 0 && !removal.global) {
    return { title: `Remove ${label}?`, lines: ["No game has it."], okLabel: "Remove", removes: true, alert: false };
  }
  const games = removal.games.length
    ? ["These games have it:", ...removal.games, "Each keeps its own copy until it's patched again."]
    : [];
  const everyGame = removal.global ? ["It is picked for every game; that goes back to OptiScaler settings."] : [];
  return { title: `Remove ${label}?`, lines: [...games, ...everyGame], okLabel: "Remove anyway", removes: true, alert: false };
};

// ── A game's page ────────────────────────────────────────────────────────────

export type GameLibraryPickers = { pickers: SlotPicker[]; note: string | null };

/** A game's own choice per slot, under its version and proxy: following the global choice, none, or a library;
 *  disabled for a version that takes no libraries. What the choice comes to, and whether the game needs patching
 *  again for it, are the backend's to say (`choice`). */
export const gameLibraryPickers = (
  installed: UserLibraries | null,
  choice: GameLibraryChoice | null,
  takesLibraries: boolean,
): GameLibraryPickers => {
  if (installed === null || choice === null) return { pickers: [], note: null };
  const libraries = installed.libraries;
  const pickers = installed.slots.map((slot) => ({
    slot,
    label: slotLabel(slot),
    options: takesLibraries
      ? [
          { data: FOLLOW, label: `Same as global: ${labelOf(libraries, installed.global[slot])}` },
          { data: NONE, label: "None" },
          ...serving(libraries, slot),
        ]
      : [{ data: FOLLOW, label: "Libraries need OptiScaler 10" }],
    selected: takesLibraries ? choice.own[slot] ?? FOLLOW : FOLLOW,
    enabled: takesLibraries,
    hint: takesLibraries ? hintFor(libraries, slot, choice.resolved[slot]) : null,
  }));
  return { pickers, note: takesLibraries && choice.pending ? "Patch again to use the libraries picked here." : null };
};

/** The choice a game's pick sends: following the global one is no choice of its own. */
export const changedChoice = (picked: string): string | null => (picked === FOLLOW ? null : picked);

/** What a patched game has of the user's libraries, by slot; null when it has none. */
export const librariesLine = (placed: PlacedLibrary[] | undefined): string | null =>
  placed?.length ? placed.map((library) => `${slotLabel(library.slot)}: ${library.label}`).join(" · ") : null;
