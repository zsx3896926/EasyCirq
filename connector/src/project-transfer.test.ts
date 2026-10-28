/// <reference types="@jlceda/pro-api-types" />
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { runAction } from './actions';

for (const scenario of ['open', 'open-page-delayed', 'open-page-missing', 'open-page-wrong-project', 'open-page-false', 'open-false', 'open-wrong-project', 'open-unconfirmed', 'open-string-confirm', 'open-blank-target', 'open-invalid-page', 'export', 'export-wrong-project', 'export-drift', 'export-empty', 'export-oversized', 'export-size-mismatch', 'export-missing']) {
	test(`typed project transfer: ${scenario}`, async () => {
		const scope = globalThis as unknown as { eda: unknown };
		const old = scope.eda;
		const oldTimer = globalThis.setTimeout;
		let checks = 0, exports = 0, projectOpens = 0, pageReads = 0, pageOpens = 0;
		scope.eda = {
			dmt_Project: {
				openProject: async (id: string) => { projectOpens++; assert.equal(id, 'target'); return scenario !== 'open-false'; },
				getCurrentProjectInfo: async () => ({ uuid: scenario === 'open-wrong-project' || scenario === 'export-wrong-project' || (scenario === 'export-drift' && checks++ > 0) ? 'other' : 'target' }),
			},
			dmt_Schematic: { getAllSchematicPagesInfo: async () => { pageReads++; return scenario === 'open-page-missing' || pageReads === 1 ? [] : [{ uuid: 'page-1' }]; } },
			dmt_EditorControl: { openDocument: async (id: string) => { pageOpens++; assert.equal(id, 'page-1'); return scenario === 'open-page-false' ? undefined : 'tab'; } },
			dmt_SelectControl: { getCurrentDocumentInfo: async () => ({ uuid: 'page-1', parentProjectUuid: scenario === 'open-page-wrong-project' ? 'other' : 'target' }) },
			sys_FileManager: { getProjectFile: async (name: string, unused: unknown, format: string) => {
				exports++; assert.equal(name, 'project.epro2'); assert.equal(unused, undefined); assert.equal(format, 'epro2');
				if (scenario === 'export-missing') return undefined;
				if (scenario === 'export-oversized') return { size: 16777217, arrayBuffer: () => { throw Error('must reject before allocation'); } };
				if (scenario === 'export-size-mismatch') return { size: 1, arrayBuffer: async () => new ArrayBuffer(2) };
				return new Blob([scenario === 'export-empty' ? '' : 'PKfixture']);
			} },
		};
		globalThis.setTimeout = ((f: () => void) => { f(); return 0; }) as unknown as typeof setTimeout;
		try {
			const opening = scenario.startsWith('open');
			const payload: Record<string, unknown> = { projectUuid: scenario === 'open-blank-target' ? ' ' : 'target' };
			if (opening && scenario !== 'open-unconfirmed') payload.allowDiscardUnsaved = scenario === 'open-string-confirm' ? 'true' : true;
			if (scenario.startsWith('open-page')) payload.pageUuid = 'page-1';
			if (scenario === 'open-invalid-page') payload.pageUuid = 42;
			const op = runAction(opening ? 'project.open' : 'project.export', payload);
			if (['open', 'open-page-delayed', 'export'].includes(scenario)) {
				const got = await op;
				assert.equal(got.result?.uuid, 'target');
				if (scenario === 'export') assert.equal(Buffer.from(got.result?.base64 as string, 'base64').toString(), 'PKfixture');
				if (scenario === 'open-page-delayed') { assert.equal(pageOpens, 1); assert.equal(pageReads, 2); assert.equal(got.result?.documentVerified, true); }
			} else await assert.rejects(op);
			if (scenario === 'open-page-missing') assert.equal(pageOpens, 0);
			if (['open-unconfirmed', 'open-string-confirm', 'open-blank-target', 'open-invalid-page'].includes(scenario)) assert.equal(projectOpens, 0);
			if (scenario === 'export-wrong-project') assert.equal(exports, 0);
			assert.ok(projectOpens <= 1);
		} finally { scope.eda = old; globalThis.setTimeout = oldTimer; }
	});
}

for (const scenario of ['import', 'import-explicit-team', 'import-no-team', 'import-bad-option', 'import-empty', 'import-none', 'import-unreadable', 'import-blank-name']) {
	test(`typed project import: ${scenario}`, async () => {
		const scope = globalThis as unknown as { eda: unknown };
		const old = scope.eda;
		let imports = 0;
		let seen: { name?: string; size?: number; type?: unknown; props?: unknown; saveTo?: Record<string, unknown> } = {};
		scope.eda = {
			dmt_Project: {
				getCurrentProjectInfo: async () => (scenario === 'import-no-team' ? { uuid: 'active' } : { uuid: 'active', teamUuid: 'team-active' }),
				getProjectInfo: async (id: string) => (scenario === 'import-unreadable' ? undefined : { uuid: id, friendlyName: 'blink', teamUuid: 'team-active' }),
			},
			sys_FileManager: { importProjectByProjectFile: async (file: File, type: unknown, props: unknown, saveTo: Record<string, unknown>) => {
				imports++; seen = { name: file.name, size: file.size, type, props, saveTo };
				return scenario === 'import-none' ? undefined : { uuid: 'new-project' };
			} },
		};
		try {
			const payload: Record<string, unknown> = { fileName: 'blink.epro2', base64: scenario === 'import-empty' ? '' : Buffer.from('PKfixture').toString('base64'),
				friendlyName: scenario === 'import-blank-name' ? ' ' : 'blink' };
			if (scenario === 'import-explicit-team') payload.teamUuid = 'team-x';
			if (scenario === 'import-bad-option') payload.importOption = 'ExtractLibraries';
			const op = runAction('project.import', payload);
			if (scenario === 'import' || scenario === 'import-explicit-team') {
				const got = await op;
				assert.equal(got.result?.uuid, 'new-project');
				assert.equal(got.result?.contentVerified, false);
				assert.deepEqual(seen, { name: 'blink.epro2', size: 9, type: 'EasyEDA Pro', props: { importOption: 'ImportDocument' },
					saveTo: { operation: 'New Project', newProjectOwnerTeamUuid: scenario === 'import' ? 'team-active' : 'team-x', newProjectFriendlyName: 'blink' } });
			} else await assert.rejects(op);
			if (['import-no-team', 'import-bad-option', 'import-empty', 'import-blank-name'].includes(scenario)) assert.equal(imports, 0);
			assert.ok(imports <= 1);
		} finally { scope.eda = old; }
	});
}
