import type { DeveloperModeAnswer, PluginBuild } from "../api";
import {
  DeveloperModeChange,
  confirmedDeveloperModeChange,
  developerModeChange,
  developerModeNoAnswer,
} from "../presentation/updates";

export type DeveloperModeSaveEffects = {
  /** Asks the backend to save Developer mode; undefined when it didn't answer. */
  save: (on: boolean) => Promise<DeveloperModeAnswer | undefined>;
  /** Keeps the mode the backend answered with as the running build's. */
  keep: (developerMode: boolean) => void;
  /** Reads the running build again; null when that got no answer either. */
  readBuild: () => Promise<PluginBuild | null>;
};

/** Saving Developer mode: the failure to show, or null once the backend has it. An answer is kept as it is, with no
 *  second read; only a save without an answer reads the build again, to learn whether it happened. */
export const saveDeveloperMode = async (
  on: boolean,
  { save, keep, readBuild }: DeveloperModeSaveEffects,
): Promise<string | null> => {
  const answer = await save(on);
  if (!answer) return developerModeNoAnswer(on, await readBuild());
  if (answer.status === "error") return answer.message;
  keep(answer.developer_mode);
  return null;
};

export type DeveloperModeEffects = {
  /** Holds the change being asked for or saved; null when there is none. */
  setChange: (change: DeveloperModeChange | null) => void;
  /** Saves Developer mode; the failure to show, or null once the backend has it. */
  save: (on: boolean) => Promise<string | null>;
  notify: (message: string) => void;
};

/** The Developer mode toggle's steps. A turn-on waits for the confirmation; a confirmed turn-on and a turn-off are
 *  saved, and the change is let go only after the backend answered, so the toggle never falls back to the old value
 *  while the save is in flight. */
export const developerModeFlow = ({ setChange, save, notify }: DeveloperModeEffects) => {
  const saveChange = async (saving: DeveloperModeChange): Promise<void> => {
    setChange(saving);
    const failure = await save(saving.on);
    setChange(null);
    if (failure) notify(failure);
  };

  return {
    onToggle: (on: boolean): Promise<void> => {
      const next = developerModeChange(on);
      if (next.stage === "saving") return saveChange(next);
      setChange(next);
      return Promise.resolve();
    },
    /** `asked` is the change the confirmation was shown for. */
    onConfirm: (asked: DeveloperModeChange | null): Promise<void> =>
      asked ? saveChange(confirmedDeveloperModeChange(asked)) : Promise.resolve(),
    onCancel: (): void => setChange(null),
  };
};
