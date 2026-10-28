/// <reference types="@jlceda/pro-api-types" />
/**
 * Official PCB manufacture exports (beta host APIs):
 *   - getGerberFile     → Gerber bundle (default = editor "one-click export",
 *                         which already includes the drilling layers)
 *   - getPickAndPlaceFile → CPL / assembly coordinates (csv|xlsx)
 *   - getNetlistFile    → netlist (JLCEDA / Protel2 / PADS / Allegro / DISA …)
 *
 * These are @beta APIs. The handlers therefore: (1) require an active PCB with a
 * readable project/document context, (2) reject empty files, (3) verify the
 * export context did not change while the host was writing the file, and
 * (4) always attach the file as an artifact instead of claiming success.
 */
import { readResponseContext, mutationContextError } from './eda-context';
import { ActionError, ErrorCodes, type ActionResult } from './protocol';
import { blobToBase64, newArtifactId, optionalBoolean, optionalNumber, optionalString } from './util';

export const MAX_MANUFACTURE_BYTES = 32 * 1024 * 1024;

const NETLIST_TYPES = ['Allegro', 'PADS', 'Protel2', 'JLCEDA', 'EasyEDA', 'DISA', 'DSNET'] as const;

function safeBasename(value: string | undefined, fallback: string): string {
	const name = (value ?? fallback).trim();
	if (!name || name.length > 128 || /[\\/\x00-\x1f]/.test(name)) {
		throw new ActionError(ErrorCodes.MISSING_PAYLOAD_FIELD, 'fileName must be a plain basename (<=128 chars, no path separators).');
	}
	return name;
}

async function requirePcbExportContext(what: string) {
	const before = await readResponseContext();
	if (before.documentType !== 'pcb' || !before.projectUuid || !before.documentUuid) {
		throw new ActionError(ErrorCodes.INVALID_STATE, `Activate the target PCB before exporting ${what}.`);
	}
	return before;
}

function assertArtifact(file: File | undefined, what: string): File {
	if (!file) {
		throw new ActionError(ErrorCodes.EDA_CALL_FAILED, `Official ${what} export returned no file (the host API is beta; verify the active PCB and try again).`);
	}
	if (!file.size) {
		throw new ActionError(ErrorCodes.EDA_CALL_FAILED, `Official ${what} export returned an empty file.`);
	}
	if (file.size > MAX_MANUFACTURE_BYTES) {
		throw new ActionError(ErrorCodes.EDA_CALL_FAILED,
			`Official ${what} export is ${file.size} bytes, exceeding the ${MAX_MANUFACTURE_BYTES}-byte transport limit.`,
			JSON.stringify({ size: file.size, limit: MAX_MANUFACTURE_BYTES }));
	}
	return file;
}

async function assertContextStable(before: Awaited<ReturnType<typeof readResponseContext>>, what: string) {
	const drift = mutationContextError(before, await readResponseContext());
	if (drift) throw new ActionError(ErrorCodes.INVALID_STATE, `PCB changed during ${what} export: ${drift}. No artifact accepted.`);
}

export async function pcbManufactureGerber(payload: Record<string, unknown>): Promise<ActionResult> {
	const allowed = ['fileName', 'colorSilkscreen', 'unit', 'integerNumber', 'decimalNumber', 'drill', 'drillTable', 'flyingProbe'];
	if (Object.keys(payload).some(k => !allowed.includes(k))) throw new ActionError(ErrorCodes.MISSING_PAYLOAD_FIELD, 'Unknown Gerber export option.');
	const fileName = safeBasename(optionalString(payload, 'fileName'), 'board-gerber');
	const colorSilkscreen = optionalBoolean(payload, 'colorSilkscreen') ?? false;
	const unitRaw = optionalString(payload, 'unit') ?? 'mm';
	if (unitRaw !== 'mm' && unitRaw !== 'inch') throw new ActionError(ErrorCodes.MISSING_PAYLOAD_FIELD, 'unit must be mm or inch.');
	const integerNumber = optionalNumber(payload, 'integerNumber') ?? 4;
	const decimalNumber = optionalNumber(payload, 'decimalNumber') ?? 5;
	if (!Number.isInteger(integerNumber) || !Number.isInteger(decimalNumber) || integerNumber < 1 || integerNumber > 6 || decimalNumber < 1 || decimalNumber > 6) {
		throw new ActionError(ErrorCodes.MISSING_PAYLOAD_FIELD, 'integerNumber/decimalNumber must be integers 1..6.');
	}
	const drill = optionalBoolean(payload, 'drill') ?? true;
	const drillTable = optionalBoolean(payload, 'drillTable') ?? false;
	const flyingProbe = optionalBoolean(payload, 'flyingProbe') ?? false;
	const before = await requirePcbExportContext('Gerber');
	if (typeof eda.pcb_ManufactureData?.getGerberFile !== 'function') {
		throw new ActionError(ErrorCodes.EDA_API_UNAVAILABLE, 'This host does not expose pcb_ManufactureData.getGerberFile.');
	}
	let file: File | undefined;
	try {
		file = await eda.pcb_ManufactureData.getGerberFile(
			fileName,
			colorSilkscreen,
			unitRaw as ESYS_Unit.MILLIMETER | ESYS_Unit.INCH,
			{ integerNumber, decimalNumber },
			{
				metallicDrillingInformation: drill,
				nonMetallicDrillingInformation: true,
				drillTable,
				flyingProbeTestingFile: flyingProbe,
			},
		);
	}
	catch (err) {
		throw new ActionError(ErrorCodes.EDA_CALL_FAILED, 'Official Gerber export failed.', String(err));
	}
	const accepted = assertArtifact(file, 'Gerber');
	await assertContextStable(before, 'Gerber');
	const id = newArtifactId();
	return {
		result: {
			artifactId: id,
			fileName: accepted.name || `${fileName}.zip`,
			size: accepted.size,
			format: 'gerber-zip',
			unit: unitRaw,
			digitalFormat: { integerNumber, decimalNumber },
			colorSilkscreen,
			includesDrillingLayers: drill,
			drillTable,
			flyingProbeTestingFile: flyingProbe,
			exportContext: before,
			capabilityNote: 'Uses the official @beta pcb_ManufactureData.getGerberFile. The bundle layout follows the editor one-click export (layers + drilling layers); inspect the archive before manufacturing.',
		},
		artifacts: [{
			id, kind: 'pcb_gerber',
			fileName: accepted.name || `${fileName}.zip`,
			mimeType: accepted.type || 'application/zip',
			inlineBase64: await blobToBase64(accepted),
		}],
		warnings: ['Beta API: the Gerber bundle content must be inspected (layers, units, drill data) before it is treated as a manufacturing artifact.'],
	};
}

export async function pcbManufactureCpl(payload: Record<string, unknown>): Promise<ActionResult> {
	const allowed = ['fileName', 'fileType', 'unit'];
	if (Object.keys(payload).some(k => !allowed.includes(k))) throw new ActionError(ErrorCodes.MISSING_PAYLOAD_FIELD, 'Unknown CPL export option.');
	const fileType = optionalString(payload, 'fileType') ?? 'csv';
	if (fileType !== 'csv' && fileType !== 'xlsx') throw new ActionError(ErrorCodes.MISSING_PAYLOAD_FIELD, 'fileType must be csv or xlsx.');
	const unitRaw = optionalString(payload, 'unit') ?? 'mm';
	if (unitRaw !== 'mm' && unitRaw !== 'mil') throw new ActionError(ErrorCodes.MISSING_PAYLOAD_FIELD, 'unit must be mm or mil.');
	const fileName = safeBasename(optionalString(payload, 'fileName'), `board-cpl.${fileType}`);
	const before = await requirePcbExportContext('CPL');
	if (typeof eda.pcb_ManufactureData?.getPickAndPlaceFile !== 'function') {
		throw new ActionError(ErrorCodes.EDA_API_UNAVAILABLE, 'This host does not expose pcb_ManufactureData.getPickAndPlaceFile.');
	}
	let file: File | undefined;
	try {
		file = await eda.pcb_ManufactureData.getPickAndPlaceFile(fileName, fileType as 'xlsx' | 'csv', unitRaw as ESYS_Unit.MILLIMETER | ESYS_Unit.MIL);
	}
	catch (err) {
		throw new ActionError(ErrorCodes.EDA_CALL_FAILED, 'Official CPL export failed.', String(err));
	}
	const accepted = assertArtifact(file, 'CPL');
	await assertContextStable(before, 'CPL');
	const id = newArtifactId();
	return {
		result: {
			artifactId: id,
			fileName: accepted.name || fileName,
			size: accepted.size,
			format: `cpl-${fileType}`,
			unit: unitRaw,
			exportContext: before,
			capabilityNote: 'Uses the official @beta pcb_ManufactureData.getPickAndPlaceFile. Rows/rotations must be checked against the BOM before assembly.',
		},
		artifacts: [{
			id, kind: 'pcb_cpl',
			fileName: accepted.name || fileName,
			mimeType: accepted.type || (fileType === 'csv' ? 'text/csv' : 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'),
			inlineBase64: await blobToBase64(accepted),
		}],
		warnings: ['Beta API: verify CPL row count, rotation convention and units against the BOM.'],
	};
}

export async function pcbManufactureNetlist(payload: Record<string, unknown>): Promise<ActionResult> {
	const allowed = ['fileName', 'netlistType'];
	if (Object.keys(payload).some(k => !allowed.includes(k))) throw new ActionError(ErrorCodes.MISSING_PAYLOAD_FIELD, 'Unknown netlist export option.');
	const netlistType = optionalString(payload, 'netlistType') ?? 'JLCEDA';
	if (!(NETLIST_TYPES as readonly string[]).includes(netlistType)) {
		throw new ActionError(ErrorCodes.MISSING_PAYLOAD_FIELD, `netlistType must be one of: ${NETLIST_TYPES.join(', ')}.`);
	}
	const fileName = safeBasename(optionalString(payload, 'fileName'), 'board-netlist');
	const before = await requirePcbExportContext('netlist');
	if (typeof eda.pcb_ManufactureData?.getNetlistFile !== 'function') {
		throw new ActionError(ErrorCodes.EDA_API_UNAVAILABLE, 'This host does not expose pcb_ManufactureData.getNetlistFile.');
	}
	let file: File | undefined;
	try {
		file = await eda.pcb_ManufactureData.getNetlistFile(fileName, netlistType as ESYS_NetlistType);
	}
	catch (err) {
		throw new ActionError(ErrorCodes.EDA_CALL_FAILED, 'Official netlist export failed.', String(err));
	}
	const accepted = assertArtifact(file, 'netlist');
	await assertContextStable(before, 'netlist');
	const id = newArtifactId();
	return {
		result: {
			artifactId: id,
			fileName: accepted.name || fileName,
			size: accepted.size,
			netlistType,
			exportContext: before,
			capabilityNote: 'Uses the official @beta pcb_ManufactureData.getNetlistFile (PCB side).',
		},
		artifacts: [{
			id, kind: 'pcb_netlist',
			fileName: accepted.name || fileName,
			mimeType: accepted.type || 'text/plain',
			inlineBase64: await blobToBase64(accepted),
		}],
		warnings: ['Beta API: parse the returned netlist and compare it with the schematic intent before relying on it.'],
	};
}
