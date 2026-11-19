import type {
  DamagedLibrary,
  GameLibraryChoice,
  LibraryRefusal,
  LibrarySlot,
  LibrarySource,
  LibrariesApplied,
  PathDefaults,
  PlacedLibrary,
  UserLibraries,
  UserLibrary,
  UserLibraryListing,
  UserLibraryRemoval,
  UserLibraryResult,
} from "../api";
import { ReleaseDownload, ReleaseRowView, actionOutcome, byteSize, downloadRows, listingMessage } from "./releases";
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

/** What the backend says of the slots whose pick can't go in: `left_out` a provider's name another pick already
 *  has, `missing` a library that isn't on the device. */
type CantGoIn = { left_out: LibrarySlot[]; missing: LibrarySlot[] };

/** A pick naming a library that isn't on the device, as the pickers name it: by what is left of it, else its id. */
const missingLabel = (installed: UserLibraries, id: string): string => {
  const damaged = installed.damaged.find((item) => item.id === id);
  return damaged ? `${damaged.label} (damaged)` : `${id} (not on the device)`;
};

/** What a slot's pick is called: its library, a library that isn't on the device, or OptiScaler's settings. */
const pickLabel = (installed: UserLibraries, slot: LibrarySlot, id: string | undefined, cantGoIn: CantGoIn): string =>
  id && cantGoIn.missing.includes(slot)
    ? missingLabel(installed, id)
    : installed.libraries.find((library) => library.id === id)?.label ?? NOT_SET;

/** The option a pick naming a library that isn't on the device needs, so its dropdown shows what is picked. */
const missingOption = (installed: UserLibraries, slot: LibrarySlot, id: string | undefined, cantGoIn: CantGoIn) =>
  id && cantGoIn.missing.includes(slot) ? [{ data: id, label: missingLabel(installed, id) }] : [];

/** What to know of a library picked for a slot it doesn't switch on by itself: OptiScaler's own settings do. */
const ONLY_POINTED: Partial<Record<LibrarySlot, string>> = {
  "frame-generation": "Uses its files. Frame generation itself is turned on in OptiScaler settings: FGInput and FGOutput.",
};

/** Why a pick doesn't go in, as the backend says which slots' picks can't (`CantGoIn`). */
const LEFT_OUT = "Can't go in: one of its providers has the same name as one of the library picked above.";
const MISSING = "Can't go in: this library is damaged or no longer on the device. Pick another, or download or add it again.";

const hintFor = (libraries: UserLibrary[], slot: LibrarySlot, id: string | undefined, cantGoIn: CantGoIn): string | null => {
  if (cantGoIn.missing.includes(slot)) return MISSING;
  if (cantGoIn.left_out.includes(slot)) return LEFT_OUT;
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
  /** What Download libraries brings. */
  downloadNote: string | null;
  /** Every game's choice, per slot; none until the libraries have answered. */
  pickers: SlotPicker[];
  /** Patched games a patch now would change, and the button that does it. */
  apply: { text: string; label: string; enabled: boolean } | null;
  message: string | null;
};

export type LibrariesBlockState = {
  installed: UserLibraries | null;
  sources: LibrarySource[] | null;
  /** Applying the choice to patched games, or saving a choice. */
  busy: boolean;
  /** What the last action came to; cleared by the next one. */
  message: string | null;
};

export const librariesSummary = (installed: UserLibraries | null): string => {
  if (installed === null) return "Loading…";
  if (installed.libraries.length === 0) return "No library is added yet.";
  return `${count(installed.libraries.length, "library", "libraries")} added. Games on OptiScaler 10 turn on the ones picked here unless they have their own; every provider is also there to pick in OptiScaler's own menu.`;
};

export const librariesBlockView = (state: LibrariesBlockState): LibrariesBlockView => {
  const { installed, busy } = state;
  const libraries = installed?.libraries ?? [];
  const pending = installed?.to_apply ?? [];
  return {
    summary: librariesSummary(installed),
    downloadNote: sourcesLine(state.sources),
    pickers: installed
      ? installed.slots.map((slot) => ({
          slot,
          label: slotLabel(slot),
          options: [
            { data: NONE, label: NOT_SET },
            ...serving(libraries, slot),
            ...missingOption(installed, slot, installed.global[slot], installed),
          ],
          selected: installed.global[slot] ?? NONE,
          enabled: !busy,
          hint: hintFor(libraries, slot, installed.global[slot], installed),
        }))
      : [],
    apply: pending.length
      ? {
          text: `${count(pending.length, "patched game", "patched games")} ${plural(pending.length, "doesn't", "don't")} have the current libraries yet: ${pending.join(", ")}.`,
          label: busy ? "Applying…" : `Apply to ${plural(pending.length, "it", "them")}`,
          enabled: !busy,
        }
      : null,
    message: state.message,
  };
};

/** What a source's library is for, in a sentence's middle: "frame generation". */
const servesText = (slots: LibrarySlot[]): string => slots.map((slot) => slotLabel(slot).toLowerCase()).join(" and ");

/** What Download libraries brings, said under its button before the dialog opens. */
export const sourcesLine = (sources: LibrarySource[] | null): string | null =>
  sources?.length ? sources.map((source) => `${source.label} (${servesText(source.slots)})`).join(", ") : null;

/** A pick saved for patched games that don't have it yet asks to patch them again now: a pick reaches a game only
 *  when it is patched. */
export type ApplyConfirmation = { title: string; lines: string[]; okLabel: string; cancelLabel: string };

export const applyConfirmation = (games: string[] | undefined): ApplyConfirmation | null =>
  games?.length
    ? {
        title: `Patch ${plural(games.length, "this game", "these games")} again?`,
        lines: [
          `The libraries picked here reach a patched game only when it is patched again: ${games.join(", ")}.`,
          "A running game is skipped; it gets them once patched again.",
        ],
        okLabel: "Patch again now",
        cancelLabel: "Later",
      }
    : null;

/** On a game's page, its own pick: the game itself is patched again, there and then. */
export const gameApplyConfirmation = (game: string, games: string[] | undefined): ApplyConfirmation | null =>
  games?.length
    ? {
        title: `Patch ${game} again?`,
        lines: ["The libraries picked here reach the game only when it is patched again."],
        okLabel: "Patch again now",
        cancelLabel: "Later",
      }
    : null;

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
  /** The libraries that can be downloaded: picking one lists its versions. */
  sourceOptions: { data: string; label: string }[];
  source: string | null;
  /** What the picked library is for, and where it comes from. */
  sourceNote: string | null;
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
  const picked = state.sources.find((source) => source.id === state.source);
  const label = picked?.label ?? "this library";
  return {
    sourceOptions: state.sources.map((source) => ({ data: source.id, label: source.label })),
    source: state.source,
    sourceNote: picked ? `For ${servesText(picked.slots)} · from github.com/${picked.repository}` : null,
    sourceEnabled: idle,
    checkLabel: checking ? "Checking…" : "Check for new versions",
    checkEnabled: !checking && idle,
    rows: listing?.status === "success" ? downloadRows(listing.versions, busy, state.download) : [],
    message: state.message ?? listingMessage(listing, label, `No ${label} releases are published.`),
  };
};

/** Where a library just added goes: a provider into every patched game's OptiScaler menu (the launch wrapper puts it
 *  into a Steam game at its next launch), and any library into a game once picked for it. */
const addedNote = (inMenu: boolean | undefined): string =>
  inMenu
    ? "Steam games get it in OptiScaler's menu at their next launch, other patched games once patched again. Pick it under Libraries to turn it on."
    : "Pick it under Libraries to use it.";

/** What a download came to, and where the library goes. */
export const downloadOutcome = (answer: UserLibraryResult | null, id: string): string => {
  const said = actionOutcome(answer, `${id} is downloaded.`);
  return answer?.status === "success" ? `${said} ${addedNote(answer.in_menu)}` : said;
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

/** What adding came to: the backend's words and where the library goes, why it isn't a library, or that the
 *  backend didn't answer. */
export const addOutcome = (answer: UserLibraryResult | null): string => {
  if (answer === null) return "The plugin backend did not answer.";
  if (answer.status === "error") return answer.reason ? refusalText(answer.reason) : answer.message ?? "Adding it failed.";
  return `${answer.message ?? "The library is added."} ${addedNote(answer.in_menu)}`;
};

/** Where the picker opens: the Downloads folder files from Desktop Mode land in (home when there is none, as the
 *  backend says); the root while that isn't known yet. */
export const pickerStart = (defaults: PathDefaults | null): string => defaults?.downloads ?? "/";

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
  const used = library.games.length ? `in ${count(library.games.length, "game", "games")}` : "in no game";
  return [serves, ORIGINS[library.origin] ?? library.origin, byteSize(library.size), used].join(" · ");
};

/** A damaged library: what happened to it, and what it still takes. */
const describeDamaged = (damaged: DamagedLibrary): string =>
  ["Damaged: it no longer goes into games", byteSize(damaged.size)].join(" · ");

export const libraryManageView = (state: LibraryManageState): LibraryManageView => {
  const { installed, busy } = state;
  const removable = (id: string, label: string, description: string): ReleaseRowView => ({
    id,
    label,
    description: busy === id ? "Removing…" : description,
    action: { label: "Remove", enabled: busy === null },
  });
  const rows = [
    ...(installed?.libraries ?? []).map((library) => removable(library.id, library.label, describeLibrary(library))),
    ...(installed?.damaged ?? []).map((damaged) => removable(damaged.id, damaged.label, describeDamaged(damaged))),
  ];
  return {
    rows,
    usage: installed?.installed_bytes ? `Libraries take ${byteSize(installed.installed_bytes)}.` : null,
    message: state.message ?? (installed && rows.length === 0 ? "No library is added yet." : null),
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
          { data: FOLLOW, label: `Same as global: ${pickLabel(installed, slot, installed.global[slot], installed)}` },
          { data: NONE, label: "None" },
          ...serving(libraries, slot),
          ...missingOption(installed, slot, choice.own[slot], choice),
        ]
      : [{ data: FOLLOW, label: "Libraries need OptiScaler 10" }],
    selected: takesLibraries ? choice.own[slot] ?? FOLLOW : FOLLOW,
    enabled: takesLibraries,
    hint: takesLibraries ? hintFor(libraries, slot, choice.resolved[slot], choice) : null,
  }));
  return { pickers, note: takesLibraries && choice.pending ? "Patch again to give it the current libraries." : null };
};

/** The choice a game's pick sends: following the global one is no choice of its own. */
export const changedChoice = (picked: string): string | null => (picked === FOLLOW ? null : picked);

/** What a patched game has of the user's libraries: those turned on, by slot, then those only there to pick in
 *  OptiScaler's menu; null when it has none. */
export const librariesLine = (placed: PlacedLibrary[] | undefined): string | null => {
  const picked = (placed ?? []).flatMap((library) => (library.slot === null ? [] : [`${slotLabel(library.slot)}: ${library.label}`]));
  const offered = (placed ?? []).filter((library) => library.slot === null).map((library) => library.label);
  const parts = [...picked, ...(offered.length ? [`In OptiScaler's menu: ${offered.join(", ")}`] : [])];
  return parts.length ? parts.join(" · ") : null;
};
