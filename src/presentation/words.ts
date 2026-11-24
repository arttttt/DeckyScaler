/** English words the views share. */

/** Said when a call to the plugin's backend got no answer. */
export const BACKEND_DID_NOT_ANSWER = "The plugin backend did not answer.";

/** The word for one, or for any other number. */
export const plural = (n: number, one: string, many: string): string => (n === 1 ? one : many);

/** A number and the word that follows it: "1 game", "3 games". */
export const count = (n: number, one: string, many: string): string => `${n} ${plural(n, one, many)}`;

/** Words in an English list: "A", "A and B", "A, B and C". */
export const listed = (items: readonly string[]): string =>
  items.length < 2 ? items.join("") : `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
