import { test } from 'node:test';
import assert from 'node:assert/strict';

import { isMutatingAction, projectBindingRefusal } from './session-guard';

test('write actions are recognised as mutating', () => {
	for (const action of [
		'place_component',
		'sch.place',
		'schematic.power.connect_pin',
		'pcb.place',
		'doc.reload',
	]) {
		assert.equal(isMutatingAction(action), true, action);
	}
});

test('reads and diagnostics are not treated as writes', () => {
	for (const action of [
		'sch.list',
		'schematic.components.list',
		'sch.connectivity',
		'sch.check',
		'sch.drc',
		'health',
		'context',
	]) {
		assert.equal(isMutatingAction(action), false, action);
	}
});

test('write is refused when no project is bound', () => {
	const reason = projectBindingRefusal('sch.place', {});
	assert.match(reason ?? '', /NO_PROJECT_BOUND/);
});

test('write is refused when a project is open but no document is active', () => {
	const reason = projectBindingRefusal('sch.place', { projectUuid: 'p1', projectName: 'EasyCirq Replay 2' });
	assert.match(reason ?? '', /NO_DOCUMENT_BOUND/);
});

test('write is refused on a non-editable document type', () => {
	const reason = projectBindingRefusal('sch.place', {
		projectUuid: 'p1',
		documentUuid: 'd1',
		documentType: 'symbol',
	});
	assert.match(reason ?? '', /WRONG_DOCUMENT_TYPE/);
});

test('write is allowed with a bound schematic page', () => {
	const reason = projectBindingRefusal('sch.place', {
		projectUuid: 'p1',
		documentUuid: 'd1',
		documentType: 'schematic',
	});
	assert.equal(reason, undefined);
});

test('reads are allowed even without a project', () => {
	assert.equal(projectBindingRefusal('sch.list', {}), undefined);
});
