import { describe, expect, it } from "vitest";
import type { InstalledLibrary, PatchedGame } from "../api";
import { gamesPageView } from "./games";

const LIBRARY: InstalledLibrary = {
  damaged: [],
  installed_bytes: 0,
  versions: [
    { id: "nightly-20261024", version: "10.0.0-pre1", channel: "nightly", date: "20261024", size: 1, libraries: true, incomplete: false },
    { id: "nightly-20261023", version: "10.0.0-pre1", channel: "nightly", date: "20261023", size: 1, libraries: true, incomplete: false },
  ],
};

const game = (overrides: Partial<PatchedGame>): PatchedGame => ({
  directory: "/games/Cyberpunk 2077",
  name: "Cyberpunk 2077",
  appid: "1091500",
  dll_name: "dxgi.dll",
  dll_present: true,
  version_id: "nightly-20261023",
  newer_version: null,
  lacks_version_files: false,
  version_incomplete: false,
  patched_at: "2026-10-23T18:04:00+00:00",
  record: "ok",
  by_wrapper: false,
  own_settings: false,
  ...overrides,
});

const rowOf = (g: PatchedGame, library: InstalledLibrary | null = LIBRARY) => {
  const view = gamesPageView({ status: "success", games: [g] }, library);
  if (view.kind !== "ready") throw new Error(view.kind);
  return view.rows[0];
};

describe("the Games page", () => {
  it("is loading, then the backend's error, or says nothing is patched", () => {
    expect(gamesPageView(null, LIBRARY)).toEqual({ kind: "message", message: "Loading…" });
    expect(gamesPageView({ status: "error", message: "Broken." }, LIBRARY)).toEqual({ kind: "message", message: "Broken." });
    expect(gamesPageView({ status: "success", games: [] }, LIBRARY)).toEqual({ kind: "message", message: "No game is patched yet." });
    expect(gamesPageView({ status: "success", games: [], away: [] }, LIBRARY)).toEqual({ kind: "message", message: "No game is patched yet." });
  });

  it("lists a game on a drive that isn't mounted last, to forget", () => {
    const view = gamesPageView(
      { status: "success", games: [game({})], away: [{ directory: "/run/media/deck/SD/Games/Hades", name: "Hades" }] },
      LIBRARY,
    );
    if (view.kind !== "ready") throw new Error(view.kind);
    expect(view.rows.map((row) => row.title)).toEqual(["Cyberpunk 2077", "Hades"]);
    expect(view.rows[1]).toEqual({
      key: "/run/media/deck/SD/Games/Hades",
      title: "Hades",
      lines: [
        "On a drive that isn't mounted: put it back in to see its patch.",
        "Forget it if the drive won't be back, so its OptiScaler version can be removed.",
      ],
      action: { kind: "forget", directory: "/run/media/deck/SD/Games/Hades", label: "Forget" },
    });
  });

  it("lists games on a drive that isn't mounted when nothing else is patched", () => {
    const view = gamesPageView({ status: "success", games: [], away: [{ directory: "/run/media/deck/SD/Hades", name: "Hades" }] }, LIBRARY);
    expect(view.kind === "ready" && view.rows.map((row) => row.action.kind)).toEqual(["forget"]);
  });

  it("names a game's version as the library does, its proxy and when it was patched", () => {
    expect(rowOf(game({}))).toEqual({
      key: "/games/Cyberpunk 2077",
      title: "Cyberpunk 2077",
      lines: ["OptiScaler 10.0.0-pre1 · 2026-10-23 via dxgi.dll, patched 2026-10-23"],
      action: { kind: "open", appid: "1091500", label: "Open" },
    });
  });

  it("falls back to a version's id once the library no longer has it", () => {
    expect(rowOf(game({ version_id: "stable-0.9.4", patched_at: null })).lines[0]).toBe("OptiScaler stable-0.9.4 via dxgi.dll");
    expect(rowOf(game({}), null).lines[0]).toContain("OptiScaler nightly-20261023");
  });

  it("tells of a newer build and settings of its own", () => {
    expect(rowOf(game({ newer_version: "nightly-20261024", own_settings: true })).lines.slice(1)).toEqual([
      "10.0.0-pre1 · 2026-10-24 is in the library: patch again to update.",
      "Has settings of its own.",
    ]);
  });

  it("tells a game the launch wrapper patches at each launch", () => {
    expect(rowOf(game({ by_wrapper: true })).lines).toEqual([
      "OptiScaler 10.0.0-pre1 · 2026-10-23 via dxgi.dll, patched 2026-10-23",
      "Patched at each launch by the launch wrapper.",
    ]);
  });

  it("says what is wrong with a patch and what to do", () => {
    expect(rowOf(game({ dll_present: false })).lines[1]).toBe("dxgi.dll is missing: patch it again.");
    expect(rowOf(game({ record: "incomplete", dll_present: false })).lines[1]).toBe("The patch didn't finish: unpatch it, then patch again.");
    expect(rowOf(game({ record: "damaged", dll_present: false })).lines[1]).toBe("Its patch record is damaged: patch it again to repair it.");
    expect(rowOf(game({ lacks_version_files: true })).lines[1]).toBe("Its OptiScaler version has files this patch lacks: patch it again.");
    expect(rowOf(game({ lacks_version_files: true, dll_present: false })).lines[1]).toBe("dxgi.dll is missing: patch it again.");
    expect(rowOf(game({ version_incomplete: true, lacks_version_files: true })).lines[1]).toBe(
      "Its OptiScaler version is missing files: download it again from the OptiScaler page.",
    ); // the version is mended first: patching again before that adds nothing
  });

  it("opens a Steam game's page, and unpatches a directory patched by path in place", () => {
    expect(rowOf(game({ appid: "", name: "/games/Manual", directory: "/games/Manual" })).action).toEqual({
      kind: "unpatch",
      directory: "/games/Manual",
      label: "Unpatch",
    });
  });
});
