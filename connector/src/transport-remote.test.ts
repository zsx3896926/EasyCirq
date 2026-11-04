/**
 * 远程目标：企业部署时客户端连公司服务器，而不是自己的机器。
 *
 * 默认行为必须**完全不变**——这是最容易搞坏别人的地方：
 * 没设任何配置的人，仍然连 ws://127.0.0.1:23111/eda。
 */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { buildTarget } from './transport';

test('unset override keeps the localhost default exactly as before', () => {
	const t = buildTarget(undefined, undefined, 23111);
	assert.equal(t.url, 'ws://127.0.0.1:23111/eda');
	assert.equal(t.remote, false);
	assert.equal(t.label, 'port 23111');
});

test('empty and whitespace overrides are treated as unset', () => {
	for (const v of ['', '   ', null]) {
		const t = buildTarget(v, undefined, 23111);
		assert.equal(t.url, 'ws://127.0.0.1:23111/eda', `override=${JSON.stringify(v)}`);
		assert.equal(t.remote, false);
	}
});

test('a wss:// override replaces the localhost target', () => {
	const t = buildTarget('wss://easycirq.company.com/eda', undefined, 23111);
	assert.equal(t.url, 'wss://easycirq.company.com/eda');
	assert.equal(t.remote, true);
});

test('a ws:// override is accepted too (internal networks without TLS)', () => {
	const t = buildTarget('ws://10.0.0.5:23111/eda', undefined, 23111);
	assert.equal(t.url, 'ws://10.0.0.5:23111/eda');
	assert.equal(t.remote, true);
});

test('the token is appended as a query parameter, encoded', () => {
	const t = buildTarget('wss://h/eda', 'a b&c', 23111);
	assert.equal(t.url, 'wss://h/eda?token=a%20b%26c');
});

test('a token is appended with & when the URL already has a query', () => {
	const t = buildTarget('wss://h/eda?x=1', 'tok', 23111);
	assert.equal(t.url, 'wss://h/eda?x=1&token=tok');
});

test('an empty token adds nothing', () => {
	const t = buildTarget('wss://h/eda', '  ', 23111);
	assert.equal(t.url, 'wss://h/eda');
});

test('the label never contains the token', () => {
	const t = buildTarget('wss://h/eda', 'SECRET-TOKEN', 23111);
	assert.ok(!t.label.includes('SECRET-TOKEN'), `label leaked token: ${t.label}`);
	assert.equal(t.label, 'wss://h/eda');
});

test('an http(s) override is ignored rather than coerced', () => {
	// Pasting a browser URL is a realistic mistake. Coercing http->ws would
	// produce a connection that fails with an unrelated error, so we fall back
	// to localhost and say so in the label.
	const t = buildTarget('https://easycirq.company.com/eda', 'tok', 23111);
	assert.equal(t.url, 'ws://127.0.0.1:23111/eda');
	assert.equal(t.remote, false);
	assert.match(t.label, /ignored/);
	assert.match(t.label, /ws:\/\/ or wss:\/\//);
});

test('a malformed ws URL still yields a usable label', () => {
	const t = buildTarget('ws://', undefined, 23111);
	assert.equal(t.remote, true);
	assert.equal(typeof t.label, 'string');
	assert.ok(t.label.length > 0);
});
