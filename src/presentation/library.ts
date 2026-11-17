import type {
  InstalledLibrary,
  InstalledVersion,
  LibraryChannel,
  LibraryListing,
  LibraryRemoval,
} from "../api";

import {
  ReleaseDownload,
  ReleaseRowView,
  byteSize,
  downloadProgress,
  downloadRows,
  listingMessage,
  versionLabel,
} from "./releases";
import { count } from "./words";

// ── The panel ────────────────────────────────────────────────────────────────

/** One line in the panel: how many versions are on the device and the newest of them. */
export const librarySummary = (library: InstalledLibrary | null): string => {
  if (library === null) return "Loading…";
  const [newest] = library.versions;
  if (!newest) return "No version is downloaded yet.";
  return `${count(library.versions.length, "version", "versions")} downloaded. Newest: ${versionLabel(newest)}.`;
};

// ── Download dialog ──────────────────────────────────────────────────────────

export type DownloadState = {
  channel: LibraryChannel;
  listing: LibraryListing | null;
  checking: boolean;
  /** The version being downloaded. */
  busy: string | null;
  download: ReleaseDownload | null;
  /** What the last download came to; cleared by the next action. */
  message: string | null;
};

export type DownloadView = {
  channelOptions: { data: LibraryChannel; label: string }[];
  channel: LibraryChannel;
  /** The channel stays put during a download: its end reloads the channel's listing. */
  channelEnabled: boolean;
  checkLabel: string;
  checkEnabled: boolean;
  rows: ReleaseRowView[];
  message: string | null;
};

export const CHANNEL_OPTIONS: { data: LibraryChannel; label: string }[] = [
  { data: "stable", label: "Stable releases" },
  { data: "nightly", label: "Nightly builds" },
];

export const downloadView = (state: DownloadState): DownloadView => {
  const { listing, checking, busy, channel } = state;
  const idle = busy === null;
  return {
    channelOptions: CHANNEL_OPTIONS,
    channel,
    channelEnabled: idle,
    checkLabel: checking ? "Checking…" : "Check for new versions",
    checkEnabled: !checking && idle,
    rows: listing?.status === "success" ? downloadRows(listing.versions, busy, state.download) : [],
    message: state.message ?? listingMessage(listing, "OptiScaler", `No ${channel} versions are published.`),
  };
};

// ── Manage dialog ────────────────────────────────────────────────────────────

export type ManageAction = "reinstall" | "remove";

export type ManageState = {
  library: InstalledLibrary | null;
  busy: { id: string; action: ManageAction } | null;
  download: ReleaseDownload | null;
  /** What the last action came to; cleared by the next one. */
  message: string | null;
};

export type ManageView = {
  rows: ReleaseRowView[];
  usage: string | null;
  message: string | null;
};

export type ManageMenuItem = {
  action: ManageAction;
  label: string;
  destructive: boolean;
  /** Asks first, saying what it changes. */
  confirms: boolean;
};

const describeInstalled = (version: InstalledVersion): string =>
  `${version.channel === "nightly" ? "Nightly" : "Stable"} · ${byteSize(version.size)}`;

const busyDescription = (action: ManageAction, download: ReleaseDownload | null): string =>
  action === "reinstall" ? downloadProgress(download) : "Removing…";

export const manageView = (state: ManageState): ManageView => {
  const { library, busy } = state;
  const versions = library?.versions ?? [];
  return {
    rows: versions.map((version) => ({
      id: version.id,
      label: versionLabel(version),
      description:
        busy?.id === version.id
          ? busyDescription(busy.action, state.download)
          : describeInstalled(version),
      action: { label: "Manage", enabled: busy === null },
    })),
    usage: library && library.installed_bytes > 0 ? `Downloaded versions take ${byteSize(library.installed_bytes)}.` : null,
    message: state.message ?? (library && versions.length === 0 ? "No version is downloaded yet." : null),
  };
};

/** What the dialog says when an action succeeded and the backend gave no words of its own. */
export const manageDone = (action: ManageAction, id: string): string =>
  action === "reinstall" ? `${id} is downloaded again.` : `${id} is removed.`;

/** What can be done with a downloaded version. */
export const MANAGE_MENU: ManageMenuItem[] = [
  { action: "reinstall", label: "Download again", destructive: false, confirms: false },
  { action: "remove", label: "Remove", destructive: true, confirms: true },
];

/** What the dialog shows when Remove is picked: the question, or — told before asking — why it can't be removed. */
export type RemoveConfirmation = { title: string; lines: string[]; okLabel: string; removes: boolean; alert: boolean };

const cantRemove = (version: InstalledVersion, reason: string): RemoveConfirmation => ({
  title: `Can't remove OptiScaler ${versionLabel(version)}`,
  lines: [reason],
  okLabel: "OK",
  removes: false,
  alert: true,
});

/** Removing a version asks first, or says why it can't: games are patched with it. */
export const removeConfirmation = (version: InstalledVersion, removal: LibraryRemoval | null): RemoveConfirmation => {
  if (removal === null) return cantRemove(version, "The plugin backend did not answer.");
  if (removal.refused !== null) return cantRemove(version, removal.refused);
  return {
    title: `Remove OptiScaler ${versionLabel(version)}?`,
    lines: ["No game is patched with it."],
    okLabel: "Remove",
    removes: true,
    alert: false,
  };
};
