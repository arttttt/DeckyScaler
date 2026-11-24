import { describe, expect, it, vi } from "vitest";
import type { DeveloperModeAnswer, PluginBuild } from "../api";
import type { DeveloperModeChange } from "../presentation/updates";
import { developerModeFlow, saveDeveloperMode } from "./developerModeFlow";

/** A save the test answers when it chooses, to see what the toggle holds while the backend works. */
const pendingSave = () => {
  let answer: (failure: string | null) => void = () => undefined;
  const save = vi.fn((_on: boolean) => new Promise<string | null>((resolve) => (answer = resolve)));
  return { save, answer: (failure: string | null) => answer(failure) };
};

const flowWith = (save: (on: boolean) => Promise<string | null>) => {
  const changes: (DeveloperModeChange | null)[] = [];
  const notify = vi.fn();
  const flow = developerModeFlow({ setChange: (change) => changes.push(change), save, notify });
  return { flow, changes, notify };
};

describe("the Developer mode toggle's steps", () => {
  it("asks before turning on, and saves nothing until confirmed", async () => {
    const { save } = pendingSave();
    const { flow, changes } = flowWith(save);
    await flow.onToggle(true);
    expect(changes).toEqual([{ on: true, stage: "confirming" }]);
    expect(save).not.toHaveBeenCalled();
  });

  it("saves a confirmed turn-on, and lets the change go only once the backend answered", async () => {
    const { save, answer } = pendingSave();
    const { flow, changes, notify } = flowWith(save);
    const confirmed = flow.onConfirm({ on: true, stage: "confirming" });
    expect(save).toHaveBeenCalledWith(true);
    expect(changes).toEqual([{ on: true, stage: "saving" }]);
    answer(null);
    await confirmed;
    expect(changes).toEqual([{ on: true, stage: "saving" }, null]);
    expect(notify).not.toHaveBeenCalled();
  });

  it("turns off at once, without asking", async () => {
    const { save, answer } = pendingSave();
    const { flow, changes } = flowWith(save);
    const turnedOff = flow.onToggle(false);
    expect(save).toHaveBeenCalledWith(false);
    expect(changes).toEqual([{ on: false, stage: "saving" }]);
    answer(null);
    await turnedOff;
    expect(changes).toEqual([{ on: false, stage: "saving" }, null]);
  });

  it("lets the change go and says why when the save fails", async () => {
    const { flow, changes, notify } = flowWith(async () => "Couldn't save Developer mode: disk full");
    await flow.onConfirm({ on: true, stage: "confirming" });
    expect(changes).toEqual([{ on: true, stage: "saving" }, null]);
    expect(notify).toHaveBeenCalledWith("Couldn't save Developer mode: disk full");
  });

  it("lets the change go on a cancel, and saves nothing for a confirmation nobody asked for", async () => {
    const { save } = pendingSave();
    const { flow, changes } = flowWith(save);
    flow.onCancel();
    await flow.onConfirm(null);
    expect(changes).toEqual([null]);
    expect(save).not.toHaveBeenCalled();
  });
});

const build: PluginBuild = {
  known: true,
  channel: "stable",
  commit: "1".repeat(40),
  short_commit: "1111111",
  title: "DeckyScaler 2026.10.24",
  version: "2026.10.24",
  is_dev_build: false,
  developer_mode: false,
};

const saving = (answer: DeveloperModeAnswer | undefined, readAgain: PluginBuild | null = null) => {
  const effects = {
    save: vi.fn(async (_on: boolean) => answer),
    keep: vi.fn(),
    readBuild: vi.fn(async () => readAgain),
  };
  return effects;
};

describe("saving Developer mode", () => {
  it("keeps the mode the backend answered with, and reads nothing again", async () => {
    const effects = saving({ status: "success", developer_mode: true });
    expect(await saveDeveloperMode(true, effects)).toBeNull();
    expect(effects.save).toHaveBeenCalledWith(true);
    expect(effects.keep).toHaveBeenCalledWith(true);
    expect(effects.readBuild).not.toHaveBeenCalled();
  });

  it("keeps the answer over the request: a development build stays on", async () => {
    const effects = saving({ status: "success", developer_mode: true });
    expect(await saveDeveloperMode(false, effects)).toBeNull();
    expect(effects.keep).toHaveBeenCalledWith(true);
  });

  it("says why a refused save failed, and keeps nothing", async () => {
    const effects = saving({ status: "error", message: "Couldn't save Developer mode: disk full" });
    expect(await saveDeveloperMode(true, effects)).toBe("Couldn't save Developer mode: disk full");
    expect(effects.keep).not.toHaveBeenCalled();
    expect(effects.readBuild).not.toHaveBeenCalled();
  });

  it("reads the build again after a save without an answer, and says what it found", async () => {
    const unsaved = saving(undefined, build);
    expect(await saveDeveloperMode(true, unsaved)).toBe("The plugin backend did not answer.");
    expect(unsaved.readBuild).toHaveBeenCalled();
    expect(unsaved.keep).not.toHaveBeenCalled();

    const savedAnyway = saving(undefined, { ...build, developer_mode: true });
    expect(await saveDeveloperMode(true, savedAnyway)).toBe("The plugin backend did not answer. Developer mode is on all the same.");
  });
});
