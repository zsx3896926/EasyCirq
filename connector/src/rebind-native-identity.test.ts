/// <reference types="@jlceda/pro-api-types" />
import assert from 'node:assert/strict';
import { test, type TestContext } from 'node:test';
import { runAction } from './actions';
import JSZip from 'jszip';

type State = Record<string, unknown>;
type Ref = { uuid: string; libraryUuid: string };
type Event = { kind: string; documentUuid: string; args: unknown[] };
const DEVICE = 'a'.repeat(32), DEVICE_LIBRARY = 'b'.repeat(32);
const OLD_ASSET = 'c'.repeat(32), NEW_ASSET = 'd'.repeat(32), OTHER_ASSET = '9'.repeat(32);
const PERSONAL_LIBRARY = 'e'.repeat(32), CLONE_DEVICE = 'f'.repeat(32), SECOND_DEVICE = '0'.repeat(32);
const PROJECT = '1234567890abcdef'.repeat(2), PAGE = '1234567890abcdef', OTHER_PAGE = 'fedcba0987654321';
const OLD_ID = '1'.repeat(16), OLD_DEVICE_INSTANCE = '2'.repeat(16), OLD_FP_INSTANCE = '3'.repeat(16);
const CANDIDATE_ID = '4'.repeat(16), CANDIDATE_DEVICE_INSTANCE = '5'.repeat(16), CANDIDATE_FP_INSTANCE = '6'.repeat(16);
const RESTORED_ID = '7'.repeat(16), RESTORED_DEVICE_INSTANCE = '8'.repeat(16), RESTORED_FP_INSTANCE = '9'.repeat(16);
const NAME = 'Synthetic rebind device', MODEL = 'SYNTHETIC-REBIND-A', SUPPLIER = 'C123456';
const TARGET_NAME = 'Synthetic target footprint', CLONE_NAME = `${NAME}_${TARGET_NAME}`;
const OLD_REF: Ref = { uuid: OLD_ASSET, libraryUuid: DEVICE_LIBRARY };
const NEW_REF: Ref = { uuid: NEW_ASSET, libraryUuid: DEVICE_LIBRARY };
const clone = <T>(value: T): T => structuredClone(value);
const mutationKinds = new Set(['device.modify', 'device.copy', 'device.delete', 'component.create', 'component.modify', 'component.delete']);

function primitive(state: State): any {
	const fields: Record<string, string> = {
		PrimitiveId: 'primitiveId', ComponentType: 'componentType', Designator: 'designator', Name: 'name',
		X: 'x', Y: 'y', Rotation: 'rotation', Mirror: 'mirror', Net: 'net', SubPartName: 'subPartName',
		AddIntoBom: 'addIntoBom', AddIntoPcb: 'addIntoPcb', UniqueId: 'uniqueId',
		Manufacturer: 'manufacturer', ManufacturerId: 'manufacturerId', Supplier: 'supplier', SupplierId: 'supplierId',
		Component: 'device', Symbol: 'symbol', Footprint: 'footprint', OtherProperty: 'otherProperty',
	};
	return Object.fromEntries(Object.entries(fields).map(([method, key]) => [`getState_${method}`, () => state[key]]));
}

interface HarnessOptions {
	exactNativeDevice?: boolean;
	exactMissingAssociation?: boolean;
	custom?: 'mpn' | 'name';
	cloneFallback?: boolean;
	mismatchUniqueId?: boolean;
	wrongCandidateSource?: boolean;
	missingRollbackSource?: boolean;
	preflight?: 'missing-source' | 'duplicate-source' | 'wrong-owner' | 'wrong-source-asset' | 'ambiguous' | 'conflict' | 'query-error';
	drift?: 'native-source' | 'scope-query' | 'preflight-association' | 'device-modify' | 'candidate-create' | 'instance-restore';
}

function harness(options: HarnessOptions = {}) {
	let currentPage = PAGE, createCount = 0, originalGets = 0;
	const events: Event[] = [];
	const associations = new Map<string, Ref>([[DEVICE, clone(OLD_REF)], [CLONE_DEVICE, clone(OLD_REF)]]);
	const originalState = (): State => ({
		primitiveId: OLD_ID, componentType: 'part', designator: 'U3', name: NAME,
		x: 1350, y: 1020, rotation: 90, mirror: true, net: '', subPartName: '',
		addIntoBom: true, addIntoPcb: true, uniqueId: 'synthetic-stable-link',
		manufacturer: 'Synthetic vendor', manufacturerId: options.custom === 'name' ? '' : MODEL,
		supplier: options.custom ? '' : 'LCSC', supplierId: options.custom ? '' : SUPPLIER,
		device: { uuid: OLD_DEVICE_INSTANCE, libraryUuid: DEVICE_LIBRARY, name: NAME },
		symbol: { uuid: 'abcdef0123456789', libraryUuid: DEVICE_LIBRARY },
		footprint: { uuid: OLD_FP_INSTANCE, libraryUuid: DEVICE_LIBRARY, name: 'Synthetic old package' },
		otherProperty: { Voltage: '3.3V', Purpose: 'synthetic fixture' },
		nativeSource: clone(OLD_REF),
	});
	const states = new Map<string, State>([[OLD_ID, originalState()]]);
	const log = (kind: string, ...args: unknown[]) => events.push({ kind, documentUuid: currentPage, args: clone(args) });
	const drift = (when: HarnessOptions['drift']) => {
		if (options.drift === when && currentPage === PAGE) { currentPage = OTHER_PAGE; log('context.drift', when); }
	};
	const detail = (uuid: string, libraryUuid: string): State | undefined => {
		if (![DEVICE, CLONE_DEVICE, SECOND_DEVICE].includes(uuid)) return undefined;
		return {
			uuid, libraryUuid, name: uuid === CLONE_DEVICE ? CLONE_NAME : NAME,
			property: { supplierId: options.custom ? '' : SUPPLIER, manufacturerId: options.custom === 'name' ? '' : MODEL },
			...(options.exactMissingAssociation ? {} : { association: { footprint: clone(associations.get(uuid) ?? associations.get(DEVICE)!) } }),
		};
	};
	const scopedRow = (uuid: string, libraryUuid: string): State => ({ uuid, libraryUuid, name: uuid === CLONE_DEVICE ? CLONE_NAME : NAME });
	const sourceEntry = (state: State): State => {
		const footprint = state.footprint as Ref, source = state.nativeSource as Ref;
		return {
			footprintUuid: footprint.uuid,
			documentSource: [
				JSON.stringify({ type: 'DOCHEAD' }) + '||' + JSON.stringify({ docType: 'FOOTPRINT', uuid: footprint.uuid }) + '|',
				JSON.stringify({ type: 'META' }) + '||' + JSON.stringify({ title: 'Synthetic native footprint', source: `${source.uuid}|${source.libraryUuid}` }) + '|',
			].join('\n'),
		};
	};
	const eda: any = {
		sys_Log: { add: () => undefined },
		dmt_Project: { getCurrentProjectInfo: async () => ({ uuid: PROJECT }) },
		dmt_SelectControl: { getCurrentDocumentInfo: async () => ({ uuid: currentPage, tabId: `${currentPage}@${PROJECT}`, documentType: 1 }) },
		sys_FileManager: { getDocumentFootprintSources: async () => {
			let entries = [...states.values()].filter(state => !(options.missingRollbackSource && state.primitiveId === RESTORED_ID)).map(sourceEntry);
			if (!events.some(event => mutationKinds.has(event.kind))) {
				if (options.preflight === 'missing-source') entries = [];
				if (options.preflight === 'duplicate-source') entries.push(clone(entries[0]));
				if (options.preflight === 'wrong-owner') entries[0].documentSource = String(entries[0].documentSource).replace(OLD_FP_INSTANCE, CANDIDATE_FP_INSTANCE);
				if (options.preflight === 'wrong-source-asset') entries[0].documentSource = String(entries[0].documentSource).replace(OLD_ASSET, OTHER_ASSET);
			}
			log('native.sources', entries); drift('native-source'); return options.exactNativeDevice ? [] : entries;
		}, getProjectFile: async () => {
			if (!options.exactNativeDevice) throw new Error('synthetic archive export is unavailable in document-source fixtures');
			const rows: string[] = [];
			for (const state of states.values()) {
				rows.push(String(sourceEntry(state).documentSource));
				const device = state.device as Ref, footprint = state.footprint as Ref;
				rows.push(JSON.stringify({ type: 'DOCHEAD' }) + '||' + JSON.stringify({ docType: 'DEVICE', uuid: device.uuid }) + '|');
				rows.push(JSON.stringify({ type: 'META' }) + '||' + JSON.stringify({ source: `${DEVICE}|${DEVICE_LIBRARY}`, attributes: { Footprint: footprint.uuid } }) + '|');
			}
			rows.push(JSON.stringify({ type: 'DOCHEAD' }) + '||' + JSON.stringify({ docType: 'SCH_PAGE', uuid: currentPage }) + '|');
			log('native.project', rows);
			const zip = new JSZip(); zip.file('synthetic.epru', rows.join('\n'));
			return new Blob([await zip.generateAsync({ type: 'arraybuffer' })]);
		} },
		lib_LibrariesList: { getPersonalLibraryUuid: async () => PERSONAL_LIBRARY },
		lib_Device: {
			getByLcscIds: async (ids: string[], _unused: unknown, all: boolean) => {
				log('device.byLcsc', ids, all); assert.deepEqual(ids, [SUPPLIER]); assert.equal(all, true);
				if (options.exactNativeDevice) throw new Error('exact native DEVICE source must not query LCSC candidates');
				return [scopedRow(DEVICE, DEVICE_LIBRARY)];
			},
			search: async (query: string, library: string) => {
				log('device.search', query, library); drift('scope-query');
				if (options.exactNativeDevice) throw new Error('exact native DEVICE source must not search candidates');
				if (options.preflight === 'query-error') throw new Error('synthetic scoped read failure');
				if (library === PERSONAL_LIBRARY) return [scopedRow(CLONE_DEVICE, PERSONAL_LIBRARY)];
				assert.equal(library, DEVICE_LIBRARY);
				assert.equal(query, options.custom === 'name' ? NAME : MODEL);
				const row = scopedRow(DEVICE, DEVICE_LIBRARY);
				if (options.preflight === 'conflict') row.footprint = { uuid: OTHER_ASSET, libraryUuid: DEVICE_LIBRARY };
				return options.preflight === 'ambiguous' ? [row, scopedRow(SECOND_DEVICE, DEVICE_LIBRARY)] : [row];
			},
			get: async (uuid: string, library: string) => {
				log('device.get', uuid, library);
				if (uuid === DEVICE && ++originalGets === 2) drift('preflight-association');
				return detail(uuid, library);
			},
			modify: async (uuid: string, library: string, _name: unknown, _description: unknown, update: { footprint?: Ref }) => {
				log('device.modify', uuid, library, update);
				if (options.cloneFallback && uuid === DEVICE) return false;
				assert.ok(update.footprint); associations.set(uuid, clone(update.footprint!));
				drift('device-modify'); return true;
			},
			copy: async (...args: unknown[]) => { log('device.copy', ...args); throw new Error('existing synthetic clone should be reused'); },
			delete: async (...args: unknown[]) => { log('device.delete', ...args); return true; },
		},
		sch_PrimitiveComponent: {
			get: async (id: string) => { log('component.get', id); const state = states.get(id); return state ? primitive(state) : undefined; },
			getAll: async () => [...states.values()].map(primitive),
			create: async (device: Ref, x: number, y: number, subPartName: string, rotation: number, mirror: boolean, addIntoBom: boolean, addIntoPcb: boolean) => {
				createCount++; const candidate = createCount === 1;
				log('component.create', device, candidate ? CANDIDATE_ID : RESTORED_ID);
				const association = associations.get(device.uuid)!;
				const state: State = {
					...originalState(), primitiveId: candidate ? CANDIDATE_ID : RESTORED_ID,
					name: device.uuid === CLONE_DEVICE ? CLONE_NAME : NAME, designator: 'U?', uniqueId: `synthetic-generated-${createCount}`,
					x, y, subPartName, rotation, mirror, addIntoBom, addIntoPcb,
					manufacturer: '', manufacturerId: '', supplier: '', supplierId: '', otherProperty: {},
					device: { uuid: candidate ? CANDIDATE_DEVICE_INSTANCE : RESTORED_DEVICE_INSTANCE, libraryUuid: device.libraryUuid, name: device.uuid === CLONE_DEVICE ? CLONE_NAME : NAME },
					footprint: { uuid: candidate ? CANDIDATE_FP_INSTANCE : RESTORED_FP_INSTANCE, libraryUuid: association.libraryUuid, name: 'Synthetic placed package' },
					nativeSource: candidate && options.wrongCandidateSource ? clone(OLD_REF) : clone(association),
				};
				states.set(String(state.primitiveId), state); drift('candidate-create'); return primitive(state);
			},
			modify: async (id: string, properties: State) => {
				log('component.modify', id, properties); const state = states.get(id);
				if (!state) return undefined;
				for (const [key, value] of Object.entries(properties)) {
					if (options.mismatchUniqueId && id === CANDIDATE_ID && key === 'uniqueId') continue;
					state[key] = clone(value);
				}
				drift('instance-restore'); return primitive(state);
			},
			delete: async (id: string) => { log('component.delete', id); states.delete(id); return true; },
		},
	};
	return { eda, events, states, associations };
}

function install(t: TestContext, mock: any) {
	const globals = globalThis as any;
	const keys = ['eda', 'EDMT_EditorDocumentType', 'document', 'MutationObserver'] as const;
	const previous = Object.fromEntries(keys.map(key => [key, globals[key]]));
	t.after(() => { for (const key of keys) { if (previous[key] === undefined) delete globals[key]; else globals[key] = previous[key]; } });
	globals.eda = mock;
	globals.EDMT_EditorDocumentType = { HOME: -1, BLANK: 0, SCHEMATIC_PAGE: 1, PCB: 3 };
	globals.document = { body: {}, querySelectorAll: () => [] };
	globals.MutationObserver = class { observe() {} disconnect() {} };
}

async function rebind(t: TestContext, f: ReturnType<typeof harness>): Promise<any> {
	install(t, f.eda);
	return runAction('schematic.rebind.footprint', {
		primitiveId: OLD_ID, footprint: TARGET_NAME, footprintUuid: NEW_ASSET, footprintLibraryUuid: DEVICE_LIBRARY,
	});
}

function facts(error: any): any {
	const text = String(error.detail); const start = text.indexOf('{');
	assert.ok(start >= 0, text); return JSON.parse(text.slice(start));
}

test('native16 rebind proves sparse original and fresh replacement against their separate32 sources', async t => {
	const f = harness(), result = await rebind(t, f);
	assert.equal(result.result.mode, 'in-place'); assert.equal(result.result.verified, true);
	assert.equal(result.mutationContextAvailable, true);
	assert.deepEqual(result.result.originalPlacedReference, { uuid: OLD_FP_INSTANCE, libraryUuid: DEVICE_LIBRARY, name: 'Synthetic old package' });
	assert.deepEqual(result.result.originalLibraryReference, OLD_REF);
	assert.deepEqual(result.result.device, { uuid: DEVICE, libraryUuid: DEVICE_LIBRARY });
	assert.equal(result.result.component.footprint.uuid, CANDIDATE_FP_INSTANCE);
	assert.equal(result.result.component.uniqueId, 'synthetic-stable-link');
	assert.equal(f.states.has(OLD_ID), false); assert.equal(f.states.has(CANDIDATE_ID), true);
	const firstMutation = f.events.findIndex(event => mutationKinds.has(event.kind));
	assert.ok(f.events.slice(0, firstMutation).some(event => event.kind === 'device.search' && event.args[1] === DEVICE_LIBRARY));
	const oldDelete = f.events.findIndex(event => event.kind === 'component.delete' && event.args[0] === OLD_ID);
	assert.ok(f.events.slice(0, oldDelete).some(event => event.kind === 'native.sources' && JSON.stringify(event.args).includes(NEW_ASSET)), 'fresh candidate native source must be reviewed before deleting the original');
	const finalSource = f.events.filter(event => event.kind === 'native.sources').at(-1)!;
	assert.match(JSON.stringify(finalSource.args), new RegExp(CANDIDATE_FP_INSTANCE));
	assert.match(JSON.stringify(finalSource.args), new RegExp(NEW_ASSET));
});

test('native16 rebind uses exact native DEVICE origin without querying unrelated candidates', async t => {
	const f = harness({ exactNativeDevice: true }), result = await rebind(t, f);
	assert.equal(result.result.mode, 'in-place'); assert.equal(result.result.verified, true);
	assert.deepEqual(result.result.originalLibraryReference, OLD_REF);
	assert.deepEqual(result.result.device, { uuid: DEVICE, libraryUuid: DEVICE_LIBRARY });
	assert.equal(result.result.component.footprint.uuid, CANDIDATE_FP_INSTANCE);
	assert.equal(result.result.component.uniqueId, 'synthetic-stable-link');
	assert.equal(f.states.has(OLD_ID), false); assert.equal(f.states.has(CANDIDATE_ID), true);
	assert.equal(f.events.some(event => ['device.byLcsc', 'device.search'].includes(event.kind)), false);
	const firstMutation = f.events.findIndex(event => mutationKinds.has(event.kind));
	const preflightGets = f.events.slice(0, firstMutation).filter(event => event.kind === 'device.get');
	assert.equal(preflightGets.length, 2, 'one exact identity get followed by the existing association guard');
	assert.ok(preflightGets.every(event => event.args[0] === DEVICE && event.args[1] === DEVICE_LIBRARY));
	const oldDelete = f.events.findIndex(event => event.kind === 'component.delete' && event.args[0] === OLD_ID);
	assert.ok(f.events.slice(firstMutation, oldDelete).some(event => event.kind === 'native.project' && JSON.stringify(event.args).includes(CANDIDATE_FP_INSTANCE)
		&& JSON.stringify(event.args).includes(NEW_ASSET)), 'fresh candidate native source must be reviewed before deleting the original');
});

test('native16 exact native DEVICE detail without an association refuses before every mutation', async t => {
	const f = harness({ exactNativeDevice: true, exactMissingAssociation: true });
	await assert.rejects(() => rebind(t, f), (error: any) => {
		assert.match(`${error.message} ${error.detail}`, /native DEVICE device\.get.*association/i); return true;
	});
	assert.equal(f.events.some(event => mutationKinds.has(event.kind)), false);
	assert.equal(f.events.some(event => ['device.byLcsc', 'device.search'].includes(event.kind)), false);
	assert.deepEqual(f.events.filter(event => event.kind === 'device.get').map(event => event.args), [[DEVICE, DEVICE_LIBRARY]]);
	assert.equal(f.states.has(OLD_ID), true); assert.deepEqual(f.associations.get(DEVICE), OLD_REF);
});

test('native16 uniqueId failure rolls library back to the proven32 asset and freshly verifies restored original', async t => {
	const f = harness({ mismatchUniqueId: true });
	await assert.rejects(() => rebind(t, f), (error: any) => {
		const report = facts(error); assert.equal(report.phase, 'restore-and-verify');
		assert.equal(report.rollback.verified, true); assert.equal(report.rollback.restoredOriginal.primitiveId, RESTORED_ID);
		assert.match(report.cause, /uniqueId/); return true;
	});
	const updates = f.events.filter(event => event.kind === 'device.modify');
	assert.deepEqual(updates.map(event => (event.args[2] as any).footprint), [NEW_REF, OLD_REF]);
	assert.ok(updates.every(event => (event.args[2] as any).footprint.uuid.length === 32));
	assert.equal(f.states.has(CANDIDATE_ID), false); assert.equal(f.states.has(RESTORED_ID), true);
	assert.equal(f.states.get(RESTORED_ID)?.uniqueId, 'synthetic-stable-link');
	const rollbackWrite = f.events.findIndex(event => event.kind === 'device.modify' && (event.args[2] as any).footprint.uuid === OLD_ASSET);
	const rollbackReads = f.events.slice(rollbackWrite + 1);
	assert.ok(rollbackReads.some(event => event.kind === 'native.sources' && JSON.stringify(event.args).includes(RESTORED_FP_INSTANCE)));
	assert.ok(rollbackReads.some(event => event.kind === 'device.search' && event.args[0] === MODEL && event.args[1] === DEVICE_LIBRARY));
	assert.ok(rollbackReads.some(event => event.kind === 'device.get' && event.args[0] === DEVICE));
});

test('native16 replacement with a wrong source is rejected before deleting the original', async t => {
	const f = harness({ wrongCandidateSource: true });
	await assert.rejects(() => rebind(t, f), (error: any) => {
		const report = facts(error); assert.equal(report.phase, 'candidate-binding-readback');
		assert.equal(report.rollback.verified, true); return true;
	});
	assert.equal(f.events.some(event => event.kind === 'component.delete' && event.args[0] === OLD_ID), false);
	assert.equal(f.states.has(OLD_ID), true); assert.equal(f.states.has(CANDIDATE_ID), false);
	assert.deepEqual(f.associations.get(DEVICE), OLD_REF);
});

test('native16 rollback lacking restored native evidence remains unverified and exposes its new primitive', async t => {
	const f = harness({ mismatchUniqueId: true, missingRollbackSource: true });
	await assert.rejects(() => rebind(t, f), (error: any) => {
		const report = facts(error); assert.equal(report.rollback.verified, false);
		assert.equal(report.rollback.restoredOriginal.primitiveId, RESTORED_ID);
		assert.equal(report.rollback.restoredOriginal.verified, false);
		assert.match(report.rollback.errors.join('; '), /original instance restore|native|identity/i); return true;
	});
	assert.equal(f.states.has(RESTORED_ID), true); assert.equal(f.states.has(CANDIDATE_ID), false);
	assert.deepEqual(f.associations.get(DEVICE), OLD_REF);
});

test('native16 missing, ambiguous, conflicting, and incomplete preflight evidence refuses every mutation', async t => {
	for (const preflight of ['missing-source', 'duplicate-source', 'wrong-owner', 'wrong-source-asset', 'ambiguous', 'conflict', 'query-error'] as const) {
		await t.test(preflight, async sub => {
			const f = harness({ preflight });
			await assert.rejects(() => rebind(sub, f), (error: any) => { assert.match(error.message, /Cannot resolve|BEFORE|identity/i); return true; });
			assert.equal(f.events.some(event => mutationKinds.has(event.kind)), false);
			assert.equal(f.states.has(OLD_ID), true); assert.deepEqual(f.associations.get(DEVICE), OLD_REF);
		});
	}
});

test('native16 preflight context drift refuses mutation after native, scoped, or final association reads', async t => {
	for (const drift of ['native-source', 'scope-query', 'preflight-association'] as const) await t.test(drift, async sub => {
		const f = harness({ drift });
		await assert.rejects(() => rebind(sub, f), (error: any) => { assert.match(`${error.message} ${error.detail}`, /context|project\/document/i); return true; });
		assert.equal(f.events.some(event => mutationKinds.has(event.kind)), false);
		assert.equal(f.states.has(OLD_ID), true);
	});
});

test('native16 drift after device, candidate, or restoration mutation cannot operate on the new page', async t => {
	for (const drift of ['device-modify', 'candidate-create', 'instance-restore'] as const) await t.test(drift, async sub => {
		const f = harness({ drift });
		await assert.rejects(() => rebind(sub, f), (error: any) => {
			const report = facts(error); assert.equal(report.rollback.verified, false);
			assert.match(`${error.message} ${error.detail}`, /context|project\/document/i); return true;
		});
		const driftIndex = f.events.findIndex(event => event.kind === 'context.drift'); assert.ok(driftIndex >= 0);
		assert.equal(f.events.slice(driftIndex + 1).some(event => mutationKinds.has(event.kind)), false);
		assert.equal(f.events.some(event => mutationKinds.has(event.kind) && event.documentUuid === OTHER_PAGE), false);
		if (drift !== 'instance-restore') assert.equal(f.states.has(OLD_ID), true);
		if (drift === 'device-modify') assert.equal(f.states.has(CANDIDATE_ID), false);
	});
});

test('native16 supplierless custom device can reuse a proven personal clone by exact MPN or stable name', async t => {
	for (const custom of ['mpn', 'name'] as const) await t.test(custom, async sub => {
		const f = harness({ custom, cloneFallback: true }), result = await rebind(sub, f);
		assert.equal(result.result.mode, 'cloned-to-personal-library'); assert.equal(result.result.verified, true);
		assert.deepEqual(result.result.device, { uuid: CLONE_DEVICE, libraryUuid: PERSONAL_LIBRARY });
		assert.equal(result.result.component.supplierId, '');
		assert.equal(f.events.some(event => event.kind === 'device.byLcsc'), false);
		assert.equal(f.events.some(event => event.kind === 'device.copy'), false);
		const scoped = f.events.filter(event => event.kind === 'device.search');
		assert.ok(scoped.some(event => event.args[0] === (custom === 'name' ? NAME : MODEL) && event.args[1] === DEVICE_LIBRARY));
		assert.ok(scoped.some(event => event.args[0] === (custom === 'name' ? CLONE_NAME : MODEL) && event.args[1] === PERSONAL_LIBRARY));
	});
});
