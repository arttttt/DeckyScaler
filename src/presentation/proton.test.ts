import { describe, expect, it } from "vitest";
import type { InstalledProton, InstalledProtonTool, ProtonListing, ReleaseVersion } from "../api";
import type { ProtonMove } from "../api";
import {
  CHOOSING_HINT,
  RESTART_CONFIRMATION,
  moveOutcome,
  unconfirmed,
  ProtonDownloadState,
  UNPACKING,
  shownGames,
  installDone,
  problemText,
  protonDownloadView,
  protonManageView,
  protonOutcome,
  protonPageView,
  protonRemoveConfirmation,
  removeDone,
} from "./proton";

const GE: InstalledProtonTool = {
  id: "GE-Proton11-12-x86_64", build: "ge-proton", build_label: "GE-Proton", system: false, size: 1_600_000_000,
  games: [
    { appid: "730", name: "Counter-Strike 2", kind: "steam" },
    { appid: "1245620", name: null, kind: "unknown" },
    { appid: "4294967291", name: "Heroic", kind: "shortcut" },
  ],
  global_default: false,
};
const OTHER: InstalledProtonTool = {
  id: "Proton-EM-10.0-37", build: null, build_label: null, system: false, size: 1_400_000_000, games: [], global_default: false,
};
const SYSTEM: InstalledProtonTool = {
  id: "proton-cachyos", build: null, build_label: null, system: true, size: 1_700_000_000, games: [], global_default: true,
};
const installed = (overrides: Partial<InstalledProton> = {}): InstalledProton => ({
  status: "success", problem: null, tools: [GE, OTHER, SYSTEM], installed_bytes: 3_000_000_000, restart_needed: false, moves: [],
  ...overrides,
});

describe("the Proton page", () => {
  it("counts the installed builds, or says there is none, and always says where a game's Proton is chosen", () => {
    expect(protonPageView(installed())).toEqual({
      summary: "2 builds installed. Newest: GE-Proton11-12-x86_64.", restart: false, moves: [], moveMessage: null,
      dialogsEnabled: true, hint: CHOOSING_HINT,
    });
    expect(protonPageView(installed({ tools: [GE] })).summary).toBe("1 build installed. Newest: GE-Proton11-12-x86_64.");
    expect(protonPageView(installed({ tools: [SYSTEM] })).summary).toBe("No Proton build is installed yet."); // the system's
    expect(protonPageView(installed({ tools: [] })).summary).toBe("No Proton build is installed yet.");
    expect(protonPageView(null)).toMatchObject({ summary: "Loading…", dialogsEnabled: false });
  });

  it("offers a Steam restart only when builds came or went since Steam started", () => {
    expect(protonPageView(installed({ restart_needed: true })).restart).toBe(true);
  });

  it("says why there is no Steam to work with and keeps the dialogs closed", () => {
    expect(protonPageView(installed({ problem: "no-steam", tools: [] }))).toMatchObject({
      summary: "Steam hasn't been run on this device yet. Start it once, then come back.",
      restart: false,
      dialogsEnabled: false,
    });
    expect(problemText("several-steams")).toBe(
      "Found more than one Steam install on this device. Start Steam so DeckyScaler knows which one to use.",
    );
  });
});

const release = (id: string, version: string, state: ReleaseVersion["state"], reason: ReleaseVersion["reason"] = null): ReleaseVersion => ({
  id, version, date: "20261103", state, reason, size: 566_859_228,
});
const LISTING: ProtonListing = {
  status: "success",
  problem: null,
  versions: [
    release("GE-Proton11-13-x86_64", "GE-Proton11-13", "unsupported", "uploading"),
    release("GE-Proton11-12-x86_64", "GE-Proton11-12", "installed"),
    release("GE-Proton11-11-x86_64", "GE-Proton11-11", "available"),
  ],
  listing_error: null,
};
const OPTIONS = [
  { id: "ge-proton", label: "GE-Proton", note: null },
  { id: "proton-cachyos", label: "Proton-CachyOS", note: null },
  { id: "proton-cachyos-v3", label: "Proton-CachyOS (x86_64_v3)", note: "Built for newer CPUs; for experimenting." },
];
const downloadState = (overrides: Partial<ProtonDownloadState> = {}): ProtonDownloadState => ({
  options: OPTIONS, installedOne: false, build: "ge-proton", listing: LISTING, checking: false, busy: null, download: null, message: null,
  ...overrides,
});

describe("the download dialog", () => {
  it("offers the builds like channels and lists a build's releases as the OptiScaler dialog does", () => {
    const view = protonDownloadView(downloadState());

    expect(view.buildOptions).toEqual([
      { data: "ge-proton", label: "GE-Proton" },
      { data: "proton-cachyos", label: "Proton-CachyOS" },
      { data: "proton-cachyos-v3", label: "Proton-CachyOS (x86_64_v3)" },
    ]);
    expect(view.rows).toEqual([
      { id: "GE-Proton11-13-x86_64", label: "GE-Proton11-13 · 2026-11-03", description: "Can't be downloaded: still uploading", action: null },
      { id: "GE-Proton11-12-x86_64", label: "GE-Proton11-12 · 2026-11-03", description: "Downloaded", action: null },
      {
        id: "GE-Proton11-11-x86_64", label: "GE-Proton11-11 · 2026-11-03", description: "567 MB download",
        action: { label: "Download", enabled: true },
      },
    ]);
    expect(view).toMatchObject({ build: "ge-proton", buildEnabled: true, buildNote: null, checkLabel: "Check for new builds", checkEnabled: true, message: null });
    expect(protonDownloadView(downloadState({ build: "proton-cachyos-v3" })).buildNote).toBe("Built for newer CPUs; for experimenting.");
  });

  it("shows an install's download and unpacking on its row and holds everything else", () => {
    const busy = downloadState({ busy: "GE-Proton11-11-x86_64", download: { received: 566_859_228, total: 566_859_228 } });

    const view = protonDownloadView(busy);

    expect(view.rows[2]).toMatchObject({ description: UNPACKING, action: { enabled: false } });
    expect(view).toMatchObject({ buildEnabled: false, checkEnabled: false });
  });

  it("offers to restart Steam once a build was installed, not while another installs", () => {
    expect(protonDownloadView(downloadState()).restart).toBe(false);
    expect(protonDownloadView(downloadState({ installedOne: true })).restart).toBe(true);
    expect(protonDownloadView(downloadState({ installedOne: true, busy: "GE-Proton11-11-x86_64" })).restart).toBe(false);
  });

  it("says when GitHub failed, nothing is published, there is no Steam, or how the last install went", () => {
    const empty = { ...LISTING, versions: [] };
    expect(protonDownloadView(downloadState({ listing: { ...empty, listing_error: "GitHub answered 403" } })).message).toBe(
      "Could not list what GE-Proton publishes (GitHub answered 403).",
    );
    expect(protonDownloadView(downloadState({ listing: empty })).message).toBe("No GE-Proton releases are published.");
    const noSteam = protonDownloadView(downloadState({ listing: { ...LISTING, problem: "no-steam" } }));
    expect(noSteam.message).toBe(problemText("no-steam"));
    expect(noSteam.rows[2].action).toEqual({ label: "Download", enabled: false });
    expect(protonDownloadView(downloadState({ message: installDone("GE-Proton11-11-x86_64") })).message).toBe(
      "GE-Proton11-11-x86_64 is installed. Restart Steam to use it.",
    );
    expect(protonDownloadView(downloadState({ checking: true }))).toMatchObject({ checkLabel: "Checking…", checkEnabled: false });
    expect(protonDownloadView(downloadState({ listing: null })).rows).toEqual([]);
  });
});

describe("the manage dialog", () => {
  it("lists every build Steam would find with its size and the games that use it", () => {
    const view = protonManageView({ installed: installed(), busy: null, message: null });

    expect(view.rows).toEqual([
      { id: GE.id, label: GE.id, description: "GE-Proton · 1.6 GB · used by 2 games", action: { label: "Remove", enabled: true } },
      { id: OTHER.id, label: OTHER.id, description: "Not installed by DeckyScaler · 1.4 GB · no games", action: { label: "Remove", enabled: true } },
      { id: SYSTEM.id, label: SYSTEM.id, description: "Installed system-wide · can't be removed here", action: null },
    ]);
    expect(view.usage).toBe("Installed builds take 3.0 GB.");
    const unsized = protonManageView({ installed: installed({ tools: [{ ...GE, size: null }], installed_bytes: null }), busy: null, message: null });
    expect(unsized.rows[0].description).toBe("GE-Proton · used by 2 games"); // the one nothing names isn't counted
    expect(unsized.usage).toBeNull();
  });

  it("says when a build is the default for all games, while one is being removed, and how a removal went", () => {
    const global = { ...GE, games: [GE.games[0]], global_default: true };
    expect(protonManageView({ installed: installed({ tools: [global] }), busy: null, message: null }).rows[0].description).toBe(
      "GE-Proton · 1.6 GB · used by 1 game · the default for all games",
    );
    const removing = protonManageView({ installed: installed(), busy: GE.id, message: null });
    expect(removing.rows[0].description).toBe("Removing…");
    expect(removing.rows[1].action).toEqual({ label: "Remove", enabled: false });
    expect(protonManageView({ installed: installed(), busy: null, message: removeDone(GE.id) }).message).toBe(
      "GE-Proton11-12-x86_64 is removed.",
    );
  });

  it("says when nothing is installed or there is no Steam", () => {
    expect(protonManageView({ installed: installed({ tools: [], installed_bytes: 0 }), busy: null, message: null })).toMatchObject({
      rows: [], usage: null, message: "No Proton build is installed yet.",
    });
    expect(protonManageView({ installed: installed({ problem: "several-steams", tools: [] }), busy: null, message: null }).message).toBe(
      problemText("several-steams"),
    );
    expect(protonManageView({ installed: null, busy: null, message: null }).message).toBeNull();
  });
});

describe("removing a build", () => {
  it("warns with the games whose user chose it, sorted, leaving out what nothing names, and still removes", () => {
    const confirmation = protonRemoveConfirmation(GE.id, { status: "success", games: GE.games, global_default: false });

    expect(confirmation).toEqual({
      title: "Remove GE-Proton11-12-x86_64?",
      lines: [
        "These games are set to use it:",
        "Counter-Strike 2",
        "Heroic",
        "Steam will run them with its default Proton until you pick another one in their Properties.",
      ],
      okLabel: "Remove anyway",
      removes: true,
      alert: false,
    });
  });

  it("warns when it is the Proton for every game, and asks plainly when nothing uses it", () => {
    expect(protonRemoveConfirmation(GE.id, { status: "success", games: [], global_default: true }).lines).toEqual([
      "It is the Proton Steam uses for every game you didn't pick one for; Steam goes back to its own until you pick another.",
    ]);
    expect(protonRemoveConfirmation(GE.id, { status: "success", games: [], global_default: false })).toEqual({
      title: "Remove GE-Proton11-12-x86_64?", lines: ["No game uses it."], okLabel: "Remove", removes: true, alert: false,
    });
  });

  it("says why it can't be asked instead of removing", () => {
    expect(protonRemoveConfirmation(GE.id, null)).toMatchObject({ lines: ["The plugin backend did not answer."], removes: false, alert: true });
    expect(protonRemoveConfirmation(GE.id, { status: "error", problem: "no-steam" })).toMatchObject({
      title: "Can't remove GE-Proton11-12-x86_64", lines: [problemText("no-steam")], removes: false,
    });
    expect(protonRemoveConfirmation(GE.id, { status: "error", message: "It is installed for every user." }).lines).toEqual([
      "It is installed for every user.",
    ]);
  });

  it("names the games that aren't installed apart, when Steam's library names them", () => {
    const uninstalled = [{ appid: "1245620", name: "Elden Ring", kind: "unknown" as const }, { appid: "9", name: null, kind: "unknown" as const }];

    expect(protonRemoveConfirmation(GE.id, { status: "success", games: [GE.games[0], ...uninstalled], global_default: false }).lines).toEqual([
      "These games are set to use it:",
      "Counter-Strike 2",
      "Steam will run them with its default Proton until you pick another one in their Properties.",
      "Steam also keeps it as the choice for games that aren't installed: Elden Ring.",
    ]);
    expect(protonRemoveConfirmation(GE.id, { status: "success", games: uninstalled, global_default: false }).lines).toEqual([
      "Steam also keeps it as the choice for games that aren't installed: Elden Ring.",
    ]);
  });

  it("asks plainly when only games nothing names chose it", () => {
    expect(protonRemoveConfirmation(GE.id, { status: "success", games: [GE.games[1]], global_default: false }).lines).toEqual([
      "No game uses it.",
    ]);
    expect(shownGames(GE.games).map((game) => game.appid)).toEqual(["730", "4294967291"]);
  });
});

describe("how an action went", () => {
  it("is the backend's words, why there was no Steam, what was done, or that the backend did not answer", () => {
    expect(protonOutcome({ status: "error", message: "Not enough free space" }, "Done.")).toBe("Not enough free space");
    expect(protonOutcome({ status: "error", problem: "no-steam" }, "Done.")).toBe(problemText("no-steam"));
    expect(protonOutcome({ status: "success" }, "Done.")).toBe("Done.");
    expect(protonOutcome(null, "Done.")).toBe("The plugin backend did not answer.");
  });
});

const MOVE: ProtonMove = {
  build: "ge-proton",
  target: "GE-Proton11-13-x86_64",
  sources: ["GE-Proton11-12-x86_64"],
  games: [GE.games[0], GE.games[2], GE.games[1]],
};

describe("moving an update's games", () => {
  it("offers to move the games still on the older build, named and sorted", () => {
    const [offer] = protonPageView(installed({ moves: [MOVE] })).moves;

    expect(offer).toEqual({
      move: { ...MOVE, games: [GE.games[0], GE.games[2]] }, // what nothing names is neither moved nor spoken of
      text: "2 games still use GE-Proton11-12-x86_64: Counter-Strike 2, Heroic.",
      moveLabel: "Move them to GE-Proton11-13-x86_64",
      keepLabel: "Keep them on GE-Proton11-12-x86_64",
      enabled: true,
    });
  });

  it("speaks of one game as one, and of several older builds as where they are", () => {
    const one = { ...MOVE, games: [GE.games[0]], sources: ["GE-Proton11-11-x86_64", "GE-Proton11-12-x86_64"] };

    expect(protonPageView(installed({ moves: [one] })).moves[0]).toMatchObject({
      text: "1 game still uses GE-Proton11-11-x86_64, GE-Proton11-12-x86_64: Counter-Strike 2.",
      moveLabel: "Move it to GE-Proton11-13-x86_64",
      keepLabel: "Keep them where they are",
    });
    expect(protonPageView(installed({ moves: [{ ...one, sources: ["GE-Proton11-12-x86_64"] }] })).moves[0].keepLabel).toBe(
      "Keep it on GE-Proton11-12-x86_64",
    );
  });

  it("holds every offer while a move runs, then says how it went", () => {
    const moving = protonPageView(installed({ moves: [MOVE] }), { target: MOVE.target, busy: true, message: null });
    expect(moving.moves[0]).toMatchObject({ text: "Moving 2 games to GE-Proton11-13-x86_64…", enabled: false });
    expect(moving.moveMessage).toBeNull();

    const shown = protonPageView(installed({ moves: [MOVE] })).moves[0].move;
    const done = protonPageView(installed(), { target: MOVE.target, busy: false, message: moveOutcome(shown, []) });
    expect(done.moveMessage).toBe("Moved 2 games to GE-Proton11-13-x86_64.");
  });

  it("names the games Steam didn't confirm on the new build", () => {
    const onTarget = [GE.games[0]];

    const pending = unconfirmed(["730", "4294967291"], onTarget);

    expect(pending).toEqual(["4294967291"]);
    expect(moveOutcome({ ...MOVE, games: [GE.games[0], GE.games[2]] }, pending)).toBe(
      "Steam hasn't confirmed the move of Heroic. Moving again is harmless.",
    );
  });

  it("offers nothing when there is no Steam to work with, or no game it could name", () => {
    expect(protonPageView(installed({ problem: "no-steam", moves: [MOVE] })).moves).toEqual([]);
    expect(protonPageView(installed({ moves: [{ ...MOVE, games: [GE.games[1]] }] })).moves).toEqual([]);
  });
});

describe("restarting Steam", () => {
  it("asks first, saying a running game closes with it", () => {
    expect(RESTART_CONFIRMATION).toEqual({
      title: "Restart Steam?",
      lines: ["Steam closes and opens again, and then lists its Proton builds as they are now.", "A running game closes with it."],
      okLabel: "Restart",
    });
  });
});
