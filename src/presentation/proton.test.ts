import { describe, expect, it } from "vitest";
import type { InstalledProton, InstalledProtonTool, ProtonListing, ReleaseVersion } from "../api";
import {
  CHOOSING_HINT,
  PROTON_MENU,
  ProtonDownloadState,
  UNPACKING,
  gameName,
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
  status: "success", problem: null, tools: [GE, OTHER, SYSTEM], installed_bytes: 3_000_000_000, restart_needed: false, ...overrides,
});

describe("the Proton page", () => {
  it("counts the installed builds, or says there is none, and always says where a game's Proton is chosen", () => {
    expect(protonPageView(installed())).toEqual({ summary: "3 builds installed.", restart: false, dialogsEnabled: true, hint: CHOOSING_HINT });
    expect(protonPageView(installed({ tools: [GE] })).summary).toBe("1 build installed.");
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

const release = (id: string, version: string, state: ReleaseVersion["state"], reason: string | null = null): ReleaseVersion => ({
  id, version, date: "20261103", state, reason, size: 566_859_228,
});
const LISTING: ProtonListing = {
  status: "success",
  problem: null,
  versions: [
    release("GE-Proton11-13-x86_64", "GE-Proton11-13", "unsupported", "still uploading"),
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
  options: OPTIONS, build: "ge-proton", listing: LISTING, checking: false, busy: null, download: null, message: null, ...overrides,
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
      { id: GE.id, label: GE.id, description: "GE-Proton · 1.6 GB · used by 3 games", action: { label: "Manage", enabled: true } },
      { id: OTHER.id, label: OTHER.id, description: "Not installed by DeckyScaler · 1.4 GB · no games", action: { label: "Manage", enabled: true } },
      { id: SYSTEM.id, label: SYSTEM.id, description: "Installed system-wide · can't be removed here", action: null },
    ]);
    expect(view.usage).toBe("Installed builds take 3.0 GB.");
    expect(PROTON_MENU).toEqual([{ action: "remove", label: "Remove", destructive: true }]);
  });

  it("says when a build is the default for all games, while one is being removed, and how a removal went", () => {
    const global = { ...GE, games: [GE.games[0]], global_default: true };
    expect(protonManageView({ installed: installed({ tools: [global] }), busy: null, message: null }).rows[0].description).toBe(
      "GE-Proton · 1.6 GB · used by 1 game · the default for all games",
    );
    const removing = protonManageView({ installed: installed(), busy: GE.id, message: null });
    expect(removing.rows[0].description).toBe("Removing…");
    expect(removing.rows[1].action).toEqual({ label: "Manage", enabled: false });
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
  it("warns with the games whose user chose it, sorted, unnamed ones said as such, and still removes", () => {
    const confirmation = protonRemoveConfirmation(GE.id, { status: "success", games: GE.games, global_default: false });

    expect(confirmation).toEqual({
      title: "Remove GE-Proton11-12-x86_64?",
      lines: [
        "These games are set to use it:",
        "app 1245620 · not installed",
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

  it("names a game nothing names any more by its appid", () => {
    expect(gameName({ appid: "1245620", name: null, kind: "unknown" })).toBe("app 1245620 · not installed");
    expect(gameName({ appid: "730", name: "Counter-Strike 2", kind: "steam" })).toBe("Counter-Strike 2");
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
