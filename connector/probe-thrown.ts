import { describeThrown } from "./src/util";

const cases: Array<[string, unknown]> = [
  ["RangeError('')", new RangeError("")],
  ["Error('')", new Error("")],
  ["Error('boom')", new Error("boom")],
  ["RangeError('   ')", new RangeError("   ")],
];

for (const [label, value] of cases) {
  const out = describeThrown(value);
  console.log(`${label.padEnd(22)} -> ${JSON.stringify(out)}`);
}
