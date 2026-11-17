import { describe, expect, it } from "vitest";
import type { GameLibraryChoice, UserLibraries, UserLibrary } from "../api";
import {
  ADD_HINT,
  FOLLOW,
  NONE,
  addOutcome,
  applyOutcome,
  changedChoice,
  chooseOutcome,
  firstSource,
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
} from "./libraries";

const ANR: UserLibrary = {
  id: "anr-v-b19", label: "Apex Neural Rendering FG V.B19", origin: "downloaded",
  slots: ["frame-generation"], turns_on: ["frame-generation"], size: 5_700_000, games: ["Hades II", "Cyberpunk 2077"],
};
const SDK: UserLibrary = {
  id: "xess-sdk-3-0-2", label: "XeSS_SDK_3.0.2", origin: "file",
  slots: ["upscaler", "frame-generation"], turns_on: ["upscaler"], size: 41_000_000, games: [],
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
      "2 libraries added. Games on OptiScaler 10 get the ones picked here unless they have their own.",
    );
  });

  it("offers per slot OptiScaler's own settings or a library serving it, with the global pick selected", () => {
    const view = librariesBlockView({ installed: INSTALLED, busy: false, message: null });

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
    const view = librariesBlockView({ installed: { ...INSTALLED, global: { "frame-generation": SDK.id } }, busy: false, message: null });

    expect(view.pickers[1].hint).toBe("Uses its files. Frame generation itself is turned on in OptiScaler settings: FGInput and FGOutput.");
  });

  it("offers to apply the choice to the patched games that don't have it, and holds everything meanwhile", () => {
    const one = librariesBlockView({ installed: { ...INSTALLED, to_apply: ["Hades II"] }, busy: false, message: null });
    const two = librariesBlockView({ installed: { ...INSTALLED, to_apply: ["Hades II", "Cyberpunk 2077"] }, busy: true, message: null });

    expect(one.apply).toEqual({
      text: "1 patched game doesn't have the libraries picked for it yet: Hades II.", label: "Apply to it", enabled: true,
    });
    expect(two.apply?.text).toBe("2 patched games don't have the libraries picked for it yet: Hades II, Cyberpunk 2077.");
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

describe("saving a choice", () => {
  it("says nothing once saved, else why not", () => {
    expect(chooseOutcome({ status: "success" })).toBeNull();
    expect(chooseOutcome({ status: "error", message: "x isn't a library for that." })).toBe("x isn't a library for that.");
    expect(chooseOutcome(null)).toBe("The plugin backend did not answer.");
  });
});

describe("the download dialog", () => {
  const state = {
    sources: [{ id: "anr", label: "Apex Neural Rendering FG" }], source: "anr", listing: null, checking: false,
    busy: null, download: null, message: null,
  };

  it("shows one source as a line and lists its releases", () => {
    const view = libraryDownloadView({
      ...state,
      listing: { status: "success", versions: [{ id: "anr-v-b19", version: "V.B19", date: "20261117", state: "available", reason: null, size: 3_418_118 }], listing_error: null },
    });

    expect(view.sourceChoosable).toBe(false);
    expect(view.sourceLabel).toBe("Apex Neural Rendering FG");
    expect(view.rows[0]).toEqual({ id: "anr-v-b19", label: "V.B19 · 2026-11-17", description: "3 MB download", action: { label: "Download", enabled: true } });
    expect(view.message).toBeNull();
  });

  it("opens on the first source the backend offers", () => {
    expect(firstSource([{ id: "anr", label: "ANR" }, { id: "x", label: "X" }])).toBe("anr");
    expect(firstSource([])).toBeNull();
    expect(firstSource(null)).toBeNull();
  });

  it("holds the dialog during a download and says why nothing is listed", () => {
    const busy = libraryDownloadView({ ...state, busy: "anr-v-b19", checking: false });
    const empty = libraryDownloadView({ ...state, listing: { status: "success", versions: [], listing_error: null } });

    expect([busy.sourceEnabled, busy.checkEnabled]).toEqual([false, false]);
    expect(empty.message).toBe("No Apex Neural Rendering FG releases are published.");
    expect(libraryDownloadView({ ...state, sources: [...state.sources, { id: "x", label: "X" }] }).sourceChoosable).toBe(true);
  });
});

describe("adding the user's own", () => {
  it("says why what was picked isn't a library, else what the backend said", () => {
    expect(addOutcome({ status: "error", reason: "already-added" })).toBe("It is already added.");
    expect(addOutcome({ status: "error", message: "Adding x.zip failed: bad zip" })).toBe("Adding x.zip failed: bad zip");
    expect(addOutcome({ status: "success", message: "libxess.dll 2.0.2.68 is added." })).toBe("libxess.dll 2.0.2.68 is added.");
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
      "Frame generation · downloaded · 6 MB · used by 2 games",
      "Upscaler, frame generation · your file · 41 MB · no games",
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
    expect(gameLibraryPickers(INSTALLED, { ...choice, pending: true }, true).note).toBe("Patch again to use the libraries picked here.");
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
    expect(slotLabel("upscaler")).toBe("Upscaler");
  });
});
