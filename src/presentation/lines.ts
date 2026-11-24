/** Lines of presentation text as the one string a page shows with its breaks (components/MultilineText): the parts
 *  there are, one per line, empty ones left out. */
export const lines = (parts: readonly (string | null | undefined)[]): string => parts.filter(Boolean).join("\n");
