import { describe, expect, it } from "vitest";
import type { GameLibraryChoice, LibrarySource, UserLibraries, UserLibrary } from "../api";
import {
  ADD_HINT,
  FOLLOW,
  NONE,
  addOutcome,
  applyConfirmation,
  applyOutcome,
  changedChoice,
  chooseOutcome,
  downloadOutcome,
  firstSource,
  gameApplyConfirmation,
  gameLibraryPickers,
  launchOptionsToSet,
  libraryDownloadView,
  libraryManageView,
  libraryRemoveConfirmation,
  librariesBlockView,
  librariesLine,
  librariesSummary,
  pickerStart,
  refusalText,
  slotLabel,
  sourcesLine,
} from "./libraries";

const ANR: UserLibrary = {
  id: "anr-v-b19", label: "Apex Neural Rendering FG V.B19", origin: "downloaded",
  slots: ["frame-generation"], turns_on: ["frame-generation"], in_menu: true, size: 5_700_000,
  games: ["Hades II", "Cyberpunk 2077"],
};
const SDK: UserLibrary = {
  id: "xess-sdk-3-0-2", label: "XeSS_SDK_3.0.2", origin: "file",
  slots: ["upscaler", "frame-generation"], turns_on: ["upscaler"], in_menu: false, size: 41_000_000, games: [],
};
const ANR_SOURCE: LibrarySource = {
  id: "anr", label: "Apex Neural Rendering FG", slots: ["frame-generation"], repository: "apex-compute/ANR",
};
const INSTALLED: UserLibraries = {
  libraries: [ANR, SDK], slots: ["upscaler", "frame-generation"], global: { "frame-generation": "anr-v-b19" },
  to_apply: [], installed_bytes: 46_700_000,
};

describe("the block on the OptiScaler page", () => {
  it("sums up what is on the device", () => {
    expect(librariesSummary(null)).toBe("Loading…");
    expect(librariesSummary({ ...INSTALLED, libraries: [] })).toBe("No library is added yet.");
    expect(librariesSummary(INSTALLED)).toBe(
      "2 libraries added. Games on OptiScaler 10 turn on the ones picked here unless they have their own; every provider is also there to pick in OptiScaler's own menu.",
    );
  });

  it("offers per slot OptiScaler's own settings or a library serving it, with the global pick selected", () => {
    const view = librariesBlockView({ installed: INSTALLED, sources: null, busy: false, message: null });

    expect(view.pickers.map((picker) => picker.label)).toEqual(["Upscaler", "Frame generation"]);
    expect(view.pickers[0].options).toEqual([
      { data: NONE, label: "From OptiScaler settings" },
      { data: "xess-sdk-3-0-2", label: "XeSS_SDK_3.0.2" },
    ]);
    expect(view.pickers[0].selected).toBe(NONE);
    expect(view.pickers[1].selected).toBe("anr-v-b19");
    expect(view.pickers.every((picker) => picker.enabled && picker.hint === null)).toBe(true);
    expect(view.apply).toBeNull();
  });

  it("says when a frame generation pick is only pointed at, and OptiScaler's settings turn it on", () => {
    const view = librariesBlockView({ installed: { ...INSTALLED, global: { "frame-generation": SDK.id } }, sources: null, busy: false, message: null });

    expect(view.pickers[1].hint).toBe("Uses its files. Frame generation itself is turned on in OptiScaler settings: FGInput and FGOutput.");
  });

  it("offers to apply the choice to the patched games that don't have it, and holds everything meanwhile", () => {
    const one = librariesBlockView({ installed: { ...INSTALLED, to_apply: ["Hades II"] }, sources: null, busy: false, message: null });
    const two = librariesBlockView({ installed: { ...INSTALLED, to_apply: ["Hades II", "Cyberpunk 2077"] }, sources: null, busy: true, message: null });

    expect(one.apply).toEqual({
      text: "1 patched game doesn't have the current libraries yet: Hades II.", label: "Apply to it", enabled: true,
    });
    expect(two.apply?.text).toBe("2 patched games don't have the current libraries yet: Hades II, Cyberpunk 2077.");
    expect(two.apply?.label).toBe("Applying…");
    expect(two.apply?.enabled).toBe(false);
    expect(two.pickers.every((picker) => !picker.enabled)).toBe(true);
  });

  it("hands Steam the launch options of the Steam games applying patched again", () => {
    expect(
      launchOptionsToSet({
        status: "success",
        applied: [
          { name: "Hades II", appid: "1145350", launch_options: "~/deckyscaler/patch %command%" },
          { name: "/games/x", appid: "", launch_options: null },
        ],
        skipped: [],
        failed: [],
      }),
    ).toEqual([{ appid: 1145350, options: "~/deckyscaler/patch %command%" }]);
    expect(launchOptionsToSet(null)).toEqual([]);
  });

  it("tells how applying went", () => {
    expect(applyOutcome(null)).toBe("The plugin backend did not answer.");
    expect(applyOutcome({ status: "success", applied: [], skipped: [], failed: [] })).toBe("Nothing to apply.");
    expect(
      applyOutcome({
        status: "success",
        applied: [{ name: "Hades II", appid: "1145350", launch_options: null }],
        skipped: ["Cyberpunk 2077"],
        failed: [{ name: "Elden Ring", message: "Permission denied" }],
      }),
    ).toBe(
      "Applied to Hades II. Skipped Cyberpunk 2077: it's running. Apply again once closed. Couldn't apply to Elden Ring: Permission denied",
    );
  });
});

describe("what a pick reaches", () => {
  it("asks to patch again the patched games a pick reaches, which only a patch gives it", () => {
    expect(applyConfirmation(["Hades II", "Cyberpunk 2077"])).toEqual({
      title: "Patch these games again?",
      lines: [
        "The libraries picked here reach a patched game only when it is patched again: Hades II, Cyberpunk 2077.",
        "A running game is skipped; it gets them once patched again.",
      ],
      okLabel: "Patch again now",
      cancelLabel: "Later",
    });
    expect(applyConfirmation(["Hades II"])?.title).toBe("Patch this game again?");
    expect(applyConfirmation([])).toBeNull();
    expect(applyConfirmation(undefined)).toBeNull();
  });

  it("on a game's page asks to patch that game again", () => {
    expect(gameApplyConfirmation("Hades II", ["Hades II"])).toMatchObject({ title: "Patch Hades II again?", okLabel: "Patch again now" });
    expect(gameApplyConfirmation("Hades II", [])).toBeNull();
  });

  it("says what Download libraries brings", () => {
    expect(sourcesLine([ANR_SOURCE])).toBe("Apex Neural Rendering FG (frame generation)");
    expect(sourcesLine([])).toBeNull();
    expect(sourcesLine(null)).toBeNull();
    expect(librariesBlockView({ installed: INSTALLED, sources: [ANR_SOURCE], busy: false, message: null }).downloadNote).toBe(
      "Apex Neural Rendering FG (frame generation)",
    );
  });

  it("tells after a download where the library goes: a provider into every game's OptiScaler menu, any once picked", () => {
    expect(
      downloadOutcome({ status: "success", message: "Apex Neural Rendering FG V.B19 is downloaded.", in_menu: true }, "anr-v-b19"),
    ).toBe(
      "Apex Neural Rendering FG V.B19 is downloaded. Steam games get it in OptiScaler's menu at their next launch, other patched games once patched again. Pick it under Libraries to turn it on.",
    );
    expect(downloadOutcome({ status: "success", in_menu: false }, "x")).toBe("x is downloaded. Pick it under Libraries to use it.");
    expect(downloadOutcome({ status: "error", message: "No space." }, "anr-v-b19")).toBe("No space.");
  });
});

describe("saving a choice", () => {
  it("says nothing once saved, else why not", () => {
    expect(chooseOutcome({ status: "success" })).toBeNull();
    expect(chooseOutcome({ status: "error", message: "x isn't a library for that." })).toBe("x isn't a library for that.");
    expect(chooseOutcome(null)).toBe("The plugin backend did not answer.");
  });
});

describe("the download dialog", () => {
  const state = {
    sources: [ANR_SOURCE], source: "anr", listing: null, checking: false,
    busy: null, download: null, message: null,
  };

  it("picks the library first, saying what it is for and where it comes from, then lists its versions", () => {
    const view = libraryDownloadView({
      ...state,
      listing: { status: "success", versions: [{ id: "anr-v-b19", version: "V.B19", date: "20261117", state: "available", reason: null, size: 3_418_118 }], listing_error: null },
    });

    expect(view.sourceOptions).toEqual([{ data: "anr", label: "Apex Neural Rendering FG" }]);
    expect(view.source).toBe("anr");
    expect(view.sourceNote).toBe("For frame generation · from github.com/apex-compute/ANR");
    expect(view.rows[0]).toEqual({ id: "anr-v-b19", label: "V.B19 · 2026-11-17", description: "3 MB download", action: { label: "Download", enabled: true } });
    expect(view.message).toBeNull();
  });

  it("opens on the first source the backend offers", () => {
    expect(firstSource([ANR_SOURCE, { ...ANR_SOURCE, id: "x" }])).toBe("anr");
    expect(firstSource([])).toBeNull();
    expect(firstSource(null)).toBeNull();
  });

  it("holds the dialog during a download and says why nothing is listed", () => {
    const busy = libraryDownloadView({ ...state, busy: "anr-v-b19", checking: false });
    const empty = libraryDownloadView({ ...state, listing: { status: "success", versions: [], listing_error: null } });

    expect([busy.sourceEnabled, busy.checkEnabled]).toEqual([false, false]);
    expect(empty.message).toBe("No Apex Neural Rendering FG releases are published.");
    expect(libraryDownloadView({ ...state, source: null }).sourceNote).toBeNull();
  });
});

describe("adding the user's own", () => {
  it("says why what was picked isn't a library, else what the backend said", () => {
    expect(addOutcome({ status: "error", reason: "already-added" })).toBe("It is already added.");
    expect(addOutcome({ status: "error", message: "Adding x.zip failed: bad zip" })).toBe("Adding x.zip failed: bad zip");
    expect(addOutcome({ status: "success", message: "libxess.dll 2.0.2.68 is added.", in_menu: false })).toBe(
      "libxess.dll 2.0.2.68 is added. Pick it under Libraries to use it.",
    );
    expect(addOutcome({ status: "success", message: "Uniscaler is added.", in_menu: true })).toMatch(
      /^Uniscaler is added\. Steam games get it in OptiScaler's menu at their next launch/,
    );
    expect(addOutcome({ status: "error" })).toBe("Adding it failed.");
    expect(addOutcome(null)).toBe("The plugin backend did not answer.");
    expect(refusalText("nothing-known")).toContain("found no library");
  });

  it("opens the picker where Desktop Mode downloads land, and says so", () => {
    expect(pickerStart({ home: "/home/deck", downloads: "/home/deck/Downloads" })).toBe("/home/deck/Downloads");
    expect(pickerStart({ home: "/home/deck" })).toBe("/home/deck");
    expect(pickerStart(null)).toBe("/");
    expect(ADD_HINT).toContain("Downloads");
  });
});

describe("the manage dialog", () => {
  it("lists what each library serves, where it came from, what it takes and who has it", () => {
    const view = libraryManageView({ installed: INSTALLED, busy: null, message: null });

    expect(view.rows.map((row) => row.description)).toEqual([
      "Frame generation · downloaded · 6 MB · in 2 games",
      "Upscaler, frame generation · your file · 41 MB · in no game",
    ]);
    expect(view.rows[0].action).toEqual({ label: "Remove", enabled: true });
    expect(view.usage).toBe("Libraries take 47 MB.");
  });

  it("holds the rows during a removal and says when nothing is added", () => {
    const busy = libraryManageView({ installed: INSTALLED, busy: "anr-v-b19", message: null });

    expect(busy.rows[0].description).toBe("Removing…");
    expect(busy.rows.every((row) => row.action?.enabled === false)).toBe(true);
    expect(libraryManageView({ installed: { ...INSTALLED, libraries: [], installed_bytes: 0 }, busy: null, message: null })).toEqual({
      rows: [], usage: null, message: "No library is added yet.",
    });
  });

  it("asks before removing, naming who keeps a copy and whether every game had it picked", () => {
    expect(libraryRemoveConfirmation("ANR", { status: "success", games: [], global: false }).lines).toEqual(["No game has it."]);
    expect(libraryRemoveConfirmation("ANR", { status: "success", games: ["Hades II"], global: true })).toEqual({
      title: "Remove ANR?",
      lines: [
        "These games have it:", "Hades II", "Each keeps its own copy until it's patched again.",
        "It is picked for every game; that goes back to OptiScaler settings.",
      ],
      okLabel: "Remove anyway",
      removes: true,
      alert: false,
    });
    expect(libraryRemoveConfirmation("ANR", null)).toMatchObject({ title: "Can't remove ANR", removes: false, alert: true });
    expect(libraryRemoveConfirmation("ANR", { status: "success", games: [], global: true })).toMatchObject({
      lines: ["It is picked for every game; that goes back to OptiScaler settings."],
      okLabel: "Remove anyway",
    });
  });
});

describe("a game's page", () => {
  const choice: GameLibraryChoice = { status: "success", own: { upscaler: NONE }, resolved: { "frame-generation": SDK.id }, pending: false };

  it("offers following the global pick, none, or a library serving the slot", () => {
    const { pickers, note } = gameLibraryPickers(INSTALLED, choice, true);

    expect(pickers[0].options.map((option) => option.label)).toEqual(["Same as global: From OptiScaler settings", "None", "XeSS_SDK_3.0.2"]);
    expect(pickers[1].options[0]).toEqual({ data: FOLLOW, label: "Same as global: Apex Neural Rendering FG V.B19" });
    expect([pickers[0].selected, pickers[1].selected]).toEqual([NONE, FOLLOW]);
    expect(pickers[1].hint).toContain("FGInput and FGOutput");
    expect(note).toBeNull();
  });

  it("says to patch again while the game has other libraries than its choice", () => {
    expect(gameLibraryPickers(INSTALLED, { ...choice, pending: true }, true).note).toBe("Patch again to give it the current libraries.");
  });

  it("is disabled for a version that takes no libraries", () => {
    const { pickers, note } = gameLibraryPickers(INSTALLED, { ...choice, pending: true }, false);

    expect(pickers.every((picker) => !picker.enabled && picker.hint === null)).toBe(true);
    expect(pickers[0].options).toEqual([{ data: FOLLOW, label: "Libraries need OptiScaler 10" }]);
    expect(note).toBeNull();
  });

  it("waits for the libraries and the game's choice", () => {
    expect(gameLibraryPickers(null, choice, true)).toEqual({ pickers: [], note: null });
    expect(gameLibraryPickers(INSTALLED, null, true)).toEqual({ pickers: [], note: null });
  });

  it("sends no choice of the game's own for following the global one", () => {
    expect(changedChoice(FOLLOW)).toBeNull();
    expect(changedChoice(NONE)).toBe(NONE);
    expect(changedChoice("anr-v-b19")).toBe("anr-v-b19");
  });

  it("lines up what a patched game has", () => {
    expect(librariesLine(undefined)).toBeNull();
    expect(librariesLine([])).toBeNull();
    expect(
      librariesLine([
        { slot: "upscaler", id: "x", label: "XeSS_SDK_3.0.2" },
        { slot: "frame-generation", id: "a", label: "ANR V.B19" },
      ]),
    ).toBe("Upscaler: XeSS_SDK_3.0.2 · Frame generation: ANR V.B19");
    expect(
      librariesLine([
        { slot: null, id: "u", label: "Uniscaler" },
        { slot: "upscaler", id: "x", label: "XeSS_SDK_3.0.2" },
        { slot: null, id: "a", label: "ANR V.B19" },
      ]),
    ).toBe("Upscaler: XeSS_SDK_3.0.2 · In OptiScaler's menu: Uniscaler, ANR V.B19");
    expect(librariesLine([{ slot: null, id: "a", label: "ANR V.B19" }])).toBe("In OptiScaler's menu: ANR V.B19");
    expect(slotLabel("upscaler")).toBe("Upscaler");
  });
});
