import { DeveloperModeChange, confirmedDeveloperModeChange, developerModeChange } from "../presentation/updates";

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
