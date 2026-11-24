import { describe, expect, it } from "vitest";
import type { LatestStable, PluginBuild } from "../api";
import { NO_INSTALL } from "./install";
import {
  DEVELOPER_MODE_CONFIRMATION,
  UpdatesState,
  confirmedDeveloperModeChange,
  developerModeChange,
  developerModeNoAnswer,
  updateAvailableLine,
  updatesView,
  withDeveloperMode,
} from "./updates";

const release: PluginBuild = {
  known: true,
  channel: "stable",
  commit: "1".repeat(40),
  short_commit: "1111111",
  title: "DeckyScaler 2026.10.24",
  version: "2026.10.24",
  is_dev_build: false,
  developer_mode: false,
};
const dev: PluginBuild = { ...release, channel: "dev", title: "Dev build · main @ 1111111", is_dev_build: true, developer_mode: true };
const NEWER = { version: "2026.10.25", title: "DeckyScaler 2026.10.25", published_at: "2026-10-25T09:00:00Z" };
const latest = (offer: "update" | "switch" | "none", r: typeof NEWER | null = NEWER): LatestStable => ({ status: "success", release: r, offer });

const state = (overrides: Partial<UpdatesState> = {}): UpdatesState => ({
  build: release,
  checking: false,
  latest: null,
  install: NO_INSTALL,
  deckyInstallerAvailable: true,
  developerModeChange: null,
  ...overrides,
});

describe("the Updates section", () => {
  it("names the running build, or why it can't update itself, and checks only a known build", () => {
    expect(updatesView(state({ build: null })).running).toBe("Loading…");
    expect(updatesView(state()).running).toBe("Running DeckyScaler 2026.10.24");
    const unknown = updatesView(state({ build: { known: false, version: "", message: "Built by hand." } }));
    expect(unknown).toMatchObject({ running: "Built by hand.", checkEnabled: false, developerMode: { visible: false } });
  });

  it("offers a newer release to install, and says when up to date or nothing is released", () => {
    expect(updatesView(state({ latest: latest("update") }))).toMatchObject({
      releaseLine: "DeckyScaler 2026.10.25 is available.",
      install: { visible: true, label: "Install DeckyScaler 2026.10.25", enabled: true },
    });
    expect(updatesView(state({ latest: latest("none") }))).toMatchObject({ releaseLine: "Up to date.", install: { visible: false } });
    expect(updatesView(state({ latest: latest("none", null) })).releaseLine).toBe("No release is published yet.");
    expect(updatesView(state({ latest: { status: "error", message: "GitHub answered 403" } })).releaseLine).toBe("GitHub answered 403");
    expect(updatesView(state()).releaseLine).toBeNull();
  });

  it("offers a development build the switch to the release", () => {
    expect(updatesView(state({ build: dev, latest: latest("switch") }))).toMatchObject({
      releaseLine: "The newest release is DeckyScaler 2026.10.25.",
      install: { visible: true, label: "Switch to DeckyScaler 2026.10.25", enabled: true },
    });
  });

  it("checks and installs one at a time, and installs again after a cancel in Decky", () => {
    expect(updatesView(state({ checking: true, latest: latest("update") }))).toMatchObject({
      checkLabel: "Checking…",
      checkEnabled: false,
      install: { enabled: false },
    });
    const downloading = updatesView(state({ latest: latest("update"), install: { phase: "downloading", download: null, error: null } }));
    expect(downloading).toMatchObject({ checkEnabled: false, install: { enabled: false }, message: "Downloading DeckyScaler 2026.10.25…" });
    expect(updatesView(state({ latest: latest("update"), install: { ...NO_INSTALL, phase: "unconfirmed" } })).install.enabled).toBe(true);
  });

  it("never installs without Decky's installer, and says so", () => {
    expect(updatesView(state({ latest: latest("update"), deckyInstallerAvailable: false }))).toMatchObject({
      install: { enabled: false },
      message: "Decky's installer is not reachable from this plugin; install builds by URL instead.",
    });
    expect(updatesView(state({ latest: latest("none"), deckyInstallerAvailable: false })).message).toBeNull();
  });

  it("lets a release turn Developer mode on and off, and keeps it on in a development build", () => {
    expect(updatesView(state()).developerMode).toEqual({
      visible: true,
      on: false,
      enabled: true,
      description: "Offers development builds: unreviewed, and they may break things.",
    });
    expect(updatesView(state({ build: dev })).developerMode).toEqual({
      visible: true,
      on: true,
      enabled: false,
      description: "On in a development build. Switch to a release to turn it off.",
    });
  });

  it("asks before Developer mode turns on, turns it off at once, and saves a turn-on once confirmed", () => {
    expect(developerModeChange(true)).toEqual({ on: true, stage: "confirming" });
    expect(developerModeChange(false)).toEqual({ on: false, stage: "saving" });
    expect(confirmedDeveloperModeChange(developerModeChange(true))).toEqual({ on: true, stage: "saving" });
  });

  it("shows the asked-for Developer mode while it's asked and saved, locked, and the saved one after a cancel", () => {
    const asking = updatesView(state({ developerModeChange: { on: true, stage: "confirming" } }));
    expect(asking.developerMode).toMatchObject({ on: true, enabled: false });
    expect(asking.confirmation).toBe(DEVELOPER_MODE_CONFIRMATION);

    const savingOn = updatesView(state({ developerModeChange: { on: true, stage: "saving" } }));
    expect(savingOn.developerMode).toMatchObject({ on: true, enabled: false });
    expect(savingOn.confirmation).toBeNull();

    const turnedOn = { ...release, developer_mode: true };
    const savingOff = updatesView(state({ build: turnedOn, developerModeChange: { on: false, stage: "saving" } }));
    expect(savingOff.developerMode).toMatchObject({ on: false, enabled: false });

    const cancelled = updatesView(state());
    expect(cancelled.developerMode).toMatchObject({ on: false, enabled: true });
    expect(cancelled.confirmation).toBeNull();
    expect(updatesView(state({ build: turnedOn })).developerMode).toMatchObject({ on: true, enabled: true });
  });
});

describe("the build after a Developer mode save", () => {
  it("takes the backend's answer, and leaves a build it doesn't know as it is", () => {
    expect(withDeveloperMode(release, true)).toEqual({ ...release, developer_mode: true });
    expect(withDeveloperMode({ ...release, developer_mode: true }, false)).toEqual(release);
    const unknown: PluginBuild = { known: false, version: "", message: "Built by hand." };
    expect(withDeveloperMode(unknown, true)).toBe(unknown);
    expect(withDeveloperMode(null, true)).toBeNull();
  });
});

describe("a Developer mode save without an answer", () => {
  it("says the mode is what was asked only when the build read again shows it", () => {
    expect(developerModeNoAnswer(true, { ...release, developer_mode: true })).toBe(
      "The plugin backend did not answer. Developer mode is on all the same.",
    );
    expect(developerModeNoAnswer(false, release)).toBe("The plugin backend did not answer. Developer mode is off all the same.");
    expect(developerModeNoAnswer(true, release)).toBe("The plugin backend did not answer.");
    expect(developerModeNoAnswer(true, null)).toBe("The plugin backend did not answer.");
    expect(developerModeNoAnswer(true, { known: false, version: "", message: "Built by hand." })).toBe(
      "The plugin backend did not answer.",
    );
  });
});

describe("the Quick Access update line", () => {
  it("shows only a newer release, not a switch from a development build", () => {
    expect(updateAvailableLine({ build: release, checking: false, latest: latest("update") })).toBe("DeckyScaler 2026.10.25 is available.");
    expect(updateAvailableLine({ build: dev, checking: false, latest: latest("switch") })).toBeNull();
    expect(updateAvailableLine({ build: release, checking: false, latest: null })).toBeNull();
  });
});
