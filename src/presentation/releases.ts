/**
 * What the dialogs that download and manage releases share, OptiScaler versions and Proton builds alike: how a
 * release is named, how big things are, how a download goes, and a row of the list.
 */

import type { ReleaseReason, ReleaseVersion } from "../api";

/** Bytes of the release being downloaded received so far, and the total when GitHub said it. */
export type ReleaseDownload = { received: number; total: number | null };

/** A release's row in a dialog: tapping it downloads it, or opens what can be done with it. */
export type ReleaseRowView = {
  id: string;
  label: string;
  description: string;
  action: { label: string; enabled: boolean } | null;
};

const MEGABYTE = 1_000_000;
const GIGABYTE = 1_000_000_000;

/** A size as people read it: megabytes, gigabytes from a thousand megabytes on. */
export const byteSize = (bytes: number): string =>
  bytes >= GIGABYTE ? `${(bytes / GIGABYTE).toFixed(1)} GB` : `${Math.max(1, Math.round(bytes / MEGABYTE))} MB`;

const formatDate = (yyyymmdd: string): string =>
  /^\d{8}$/.test(yyyymmdd) ? `${yyyymmdd.slice(0, 4)}-${yyyymmdd.slice(4, 6)}-${yyyymmdd.slice(6)}` : yyyymmdd;

/** How a release is named everywhere: a nightly's number repeats across builds, its date does not. */
export const versionLabel = (version: { version: string; date: string }): string =>
  version.date ? `${version.version} · ${formatDate(version.date)}` : version.version;

/** A download under way; once it has all arrived, the unpacking that follows. */
export const downloadProgress = (download: ReleaseDownload | null, unpacking = "Unpacking…"): string => {
  if (!download) return "Downloading…";
  if (!download.total) return `Downloading: ${byteSize(download.received)}`;
  if (download.received >= download.total) return unpacking;
  const percent = Math.floor((download.received / download.total) * 100);
  return `Downloading: ${percent}% of ${byteSize(download.total)}`;
};

const REASONS: Record<ReleaseReason, string> = {
  uploading: "still uploading",
  "no-checksum": "no checksum to verify the download",
  elsewhere: "a download outside the release",
  "no-archive": "no archive this plugin can read",
  "several-archives": "more than one archive",
  "unknown-family": "a version this plugin does not support yet",
};

/** Why a release can't be downloaded, in words; a reason this frontend doesn't know yet as it came. */
export const reasonText = (reason: ReleaseReason | null): string => (reason ? REASONS[reason] ?? reason : "unknown reason");

const describePublished = (version: ReleaseVersion): string => {
  if (version.state === "installed") return "Downloaded";
  if (version.state === "unsupported") return `Can't be downloaded: ${reasonText(version.reason)}`;
  return `${byteSize(version.size)} download`;
};

/** A download dialog's rows: each release, the one downloading showing how it goes, the others held meanwhile. */
export const downloadRows = (
  versions: ReleaseVersion[],
  busy: string | null,
  download: ReleaseDownload | null,
  unpacking?: string,
): ReleaseRowView[] =>
  versions.map((version) => ({
    id: version.id,
    label: versionLabel(version),
    description: busy === version.id ? downloadProgress(download, unpacking) : describePublished(version),
    action: version.state === "available" ? { label: "Download", enabled: busy === null } : null,
  }));

/** Why a download dialog lists nothing, or that GitHub could not be asked. */
export const listingMessage = (
  listing: { status: "success"; versions: unknown[]; listing_error: string | null } | { status: "error"; message: string } | null,
  publisher: string,
  nothing: string,
): string | null => {
  if (listing?.status === "error") return listing.message;
  if (listing?.listing_error) return `Could not list what ${publisher} publishes (${listing.listing_error}).`;
  if (listing?.versions.length === 0) return nothing;
  return null;
};

/** A dialog's note once an action ends: the backend's words, or a fallback when it did not answer. */
export const actionOutcome = (answer: { status: string; message?: string } | null, done: string): string =>
  answer?.message ?? (answer?.status === "success" ? done : "The plugin backend did not answer.");
