import { SmartClipboardButton } from "./SmartClipboardButton";
import { ProxyDllView, WRAPPER_PATCH_CONFIRMATION } from "../presentation/launch";

/** What a game set up by hand takes: its launch options, or the launch wrapper's commands. */
export function ClipboardCommands({ launch }: { launch: ProxyDllView }) {
  return (
    <>
      {launch.launchOptions && <SmartClipboardButton command={launch.launchOptions} buttonText="Copy launch options" />}
      {launch.wrapper && (
        <>
          <SmartClipboardButton
            command={launch.wrapper.patch}
            buttonText="Copy Patch Command"
            confirmation={WRAPPER_PATCH_CONFIRMATION}
          />
          <SmartClipboardButton command={launch.wrapper.unpatch} buttonText="Copy Unpatch Command" />
        </>
      )}
    </>
  );
}
