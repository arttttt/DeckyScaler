import { describe, expect, it } from "vitest";
import type { ReleaseVersion } from "../api";
import { reasonText, actionOutcome, byteSize, downloadProgress, downloadRows, listingMessage, versionLabel } from "./releases";

describe("sizes", () => {
  it("reads in megabytes, and in gigabytes from a thousand megabytes", () => {
    expect(byteSize(312_400_000)).toBe("312 MB");
    expect(byteSize(1)).toBe("1 MB");
    expect(byteSize(999_000_000)).toBe("999 MB");
    expect(byteSize(1_000_000_000)).toBe("1.0 GB");
    expect(byteSize(1_690_000_000)).toBe("1.7 GB");
  });
});

describe("a release's name", () => {
  it("is its version and the day it was built, or the version alone when the day is unknown", () => {
    expect(versionLabel({ version: "GE-Proton11-12", date: "20261103" })).toBe("GE-Proton11-12 · 2026-11-03");
    expect(versionLabel({ version: "GE-Proton10-34", date: "" })).toBe("GE-Proton10-34");
  });
});

describe("a download's progress", () => {
  it("counts up, then says what follows once everything arrived", () => {
    expect(downloadProgress(null)).toBe("Downloading…");
    expect(downloadProgress({ received: 5_000_000, total: null })).toBe("Downloading: 5 MB");
    expect(downloadProgress({ received: 212_000_000, total: 567_000_000 })).toBe("Downloading: 37% of 567 MB");
    expect(downloadProgress({ received: 567_000_000, total: 567_000_000 })).toBe("Unpacking…");
    expect(downloadProgress({ received: 567_000_000, total: 567_000_000 }, "Unpacking… a while")).toBe("Unpacking… a while");
  });
});

const version = (id: string, state: ReleaseVersion["state"], reason: ReleaseVersion["reason"] = null): ReleaseVersion => ({
  id, version: id, date: "20261103", state, reason, size: 567_000_000,
});

describe("a download dialog's rows", () => {
  const versions = [version("a", "installed"), version("b", "available"), version("c", "unsupported", "uploading")];

  it("offers what can be downloaded and says what the rest are", () => {
    expect(downloadRows(versions, null, null)).toEqual([
      { id: "a", label: "a · 2026-11-03", description: "Downloaded", action: null },
      { id: "b", label: "b · 2026-11-03", description: "567 MB download", action: { label: "Download", enabled: true } },
      { id: "c", label: "c · 2026-11-03", description: "Can't be downloaded: still uploading", action: null },
    ]);
  });

  it("shows the download under way on its row and holds the others", () => {
    const rows = downloadRows(versions, "b", { received: 567_000_000, total: 567_000_000 }, "Unpacking… slowly");

    expect(rows[1]).toEqual({ id: "b", label: "b · 2026-11-03", description: "Unpacking… slowly", action: { label: "Download", enabled: false } });
  });
});

describe("why a dialog lists nothing", () => {
  it("is the backend's error, GitHub failing, or nothing being published", () => {
    expect(listingMessage({ status: "error", message: "Unknown build: x" }, "GE-Proton", "None.")).toBe("Unknown build: x");
    expect(listingMessage({ status: "success", versions: [], listing_error: "GitHub answered 403" }, "GE-Proton", "None.")).toBe(
      "Could not list what GE-Proton publishes (GitHub answered 403).",
    );
    expect(listingMessage({ status: "success", versions: [], listing_error: null }, "GE-Proton", "None.")).toBe("None.");
    expect(listingMessage({ status: "success", versions: [1], listing_error: null }, "GE-Proton", "None.")).toBeNull();
    expect(listingMessage(null, "GE-Proton", "None.")).toBeNull();
  });
});

describe("how an action went", () => {
  it("is the backend's words, else what was done, else that the backend did not answer", () => {
    expect(actionOutcome({ status: "error", message: "No room" }, "Done.")).toBe("No room");
    expect(actionOutcome({ status: "success" }, "Done.")).toBe("Done.");
    expect(actionOutcome(null, "Done.")).toBe("The plugin backend did not answer.");
  });
});

describe("why a release can't be downloaded", () => {
  it("is worded from the backend's kind, and a kind this frontend doesn't know shows as it came", () => {
    expect(reasonText("uploading")).toBe("still uploading");
    expect(reasonText("no-checksum")).toBe("no checksum to verify the download");
    expect(reasonText("elsewhere")).toBe("a download outside the release");
    expect(reasonText("no-archive")).toBe("no archive this plugin can read");
    expect(reasonText("several-archives")).toBe("more than one archive");
    expect(reasonText("unknown-family")).toBe("a version this plugin does not support yet");
    expect(reasonText("from-the-future" as never)).toBe("from-the-future");
    expect(reasonText(null)).toBe("unknown reason");
  });
});
