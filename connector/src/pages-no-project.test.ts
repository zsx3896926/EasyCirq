import { test } from 'node:test';
import assert from 'node:assert/strict';

import { HANDLERS } from './actions';

// 没有打开工程时，官方 API 返回 undefined。原来直接 .map 会抛
// "Cannot read properties of undefined (reading 'map')" —— 客户读不懂，
// 还会以为连接器坏了。这里钉住：必须给 INVALID_STATE 和一句人话。
test('schematic.pages.list with no project emits a clear INVALID_STATE', async () => {
	const handler = (HANDLERS as unknown as Record<string, unknown>)[
		'schematic.pages.list'
	] as ((p: Record<string, unknown>) => Promise<unknown>) | undefined;
	assert.ok(handler, 'handler missing');

	const g = globalThis as unknown as { eda?: unknown };
	const saved = g.eda;
	g.eda = {
		dmt_Schematic: {
			getAllSchematicsInfo: async () => undefined,
			getAllSchematicPagesInfo: async () => undefined,
		},
	};
	try {
		await assert.rejects(
			async () => handler({}),
			(err: { code?: string; message?: string; detail?: string }) => {
				assert.equal(err.code, 'INVALID_STATE');
				assert.match(String(err.message), /\u6ca1\u6709\u6253\u5f00\u4efb\u4f55\u5de5\u7a0b/);
				assert.match(String(err.detail), /no project is open/);
				assert.doesNotMatch(String(err.message), /reading 'map'/);
				return true;
			},
		);
	}
	finally {
		g.eda = saved;
	}
});
