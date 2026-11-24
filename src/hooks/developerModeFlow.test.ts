import { describe, expect, it, vi } from "vitest";
import type { DeveloperModeChange } from "../presentation/updates";
import { developerModeFlow } from "./developerModeFlow";

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
