/**
 * Session guard: mutating actions require an active project + schematic document.
 *
 * Incident 2026-10-30: EasyEDA registered a window with no project open; the
 * runtime still accepted write requests, they were routed to a different,
 * degraded window, and 109 connects were refused -- the page meanwhile looked
 * "placed" but was never saved. The guard closes the first half of that hole:
 * with no bound project/document the connector refuses the write *before any
 * mutation*, using `PRECONDITION_REFUSED` (zero mutation, excluded from write
 * health), so the runtime cannot mistake "wrong window" for "unhealthy
 * connector".
 */

import type { ResponseContext } from './protocol';
import { ErrorCodes } from './protocol';

/**
 * Action prefixes that mutate the document. Kept name-based (not a whitelist
 * of every action) so new mutating actions are covered by construction; reads
 * and diagnostics never match.
 */
const MUTATING_PATTERNS: ReadonlyArray<RegExp> = [
	/^sch\./,
	/^schematic\./,
	/^pcb\./,
	/^project\.(?:save|transfer)/,
	/^doc\.(?:save|reload|close)/,
];

/** Read-only actions that share a mutating prefix but never change the page. */
const READ_ONLY_EXCEPTIONS: ReadonlyArray<RegExp> = [
	/\.(?:list|read|info|dump|connectivity|check|drc|lint|measure)$/,
	/^schematic\.(?:components|nets?|pins)\.(?:list|read|describe)$/,
	/\.check$/,
];

/**
 * @param action - protocol action name
 * @returns true when the action is expected to mutate the document
 */
export function isMutatingAction(action: string): boolean {
	if (!action) return false;
	if (READ_ONLY_EXCEPTIONS.some((re) => re.test(action))) return false;
	return MUTATING_PATTERNS.some((re) => re.test(action));
}

export interface ProjectBinding {
	projectUuid?: string;
	documentUuid?: string;
	documentType?: string;
}

/**
 * Decide whether a write may proceed.
 *
 * @param action - protocol action name
 * @param context - context sampled right before dispatch
 * @returns undefined when allowed, otherwise a refusal reason
 */
export function projectBindingRefusal(
	action: string,
	context: ResponseContext | ProjectBinding | undefined,
): string | undefined {
	if (!isMutatingAction(action)) return undefined;
	if (!context) return 'NO_PROJECT_BOUND: context unavailable; refusing to mutate an unbound editor';
	const project = typeof context.projectUuid === 'string' ? context.projectUuid.trim() : '';
	if (!project) {
		return 'NO_PROJECT_BOUND: no project is open in this window; open the project (or bind a session) before writing';
	}
	const document = typeof context.documentUuid === 'string' ? context.documentUuid.trim() : '';
	if (!document) {
		return 'NO_DOCUMENT_BOUND: project is open but no document is active; open the schematic page before writing';
	}
	if (context.documentType && context.documentType !== 'schematic' && context.documentType !== 'pcb') {
		return `WRONG_DOCUMENT_TYPE: ${context.documentType} is not editable by write actions`;
	}
	return undefined;
}

/** Structured refusal for the transport layer. */
export function refusalError(reason: string): { code: string; message: string } {
	return { code: ErrorCodes.PRECONDITION_REFUSED, message: reason };
}
