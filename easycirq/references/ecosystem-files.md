# EasyEDA file inspection and local preview

Use `scripts/ecosystem_files.py` for **read-only** file-level preflight before
importing a downloaded/generated project or submitting it to a local viewer.
It never connects to EDA, extracts project files, modifies the project or proves
native DRC/ERC. A `pass` is scoped to the checks named in the JSON report.

```bash
python scripts/ecosystem_files.py inspect --input authorized-copy.epro2
python scripts/ecosystem_files.py validate --doc PCB --type LINE --input line.json
python scripts/ecosystem_files.py preview --viewer-url http://127.0.0.1:8080/index.html --out review/index.html
```

`inspect` bounds archive entry count and expanded bytes, rejects traversal,
case-insensitive duplicate paths, symlinks and encrypted members, checks CRC and
parses document line-record structure without extraction. It does not reconstruct
final-consistency tickets/deletes or certify complete document references.

`validate` checks only the explicitly bundled pinned schema payloads: DOCHEAD,
PCB/FOOTPRINT LINE/VIA, SCH_PAGE/SYMBOL LINE, SCH_PAGE TEXT/WIRE, SYMBOL TEXT.
Bare primitives require `--doc`; unknown schemas or unsupported schema constraints
return `incomplete` / `valid:null`, never a successful validation. It uses a small
stdlib interpreter for the keywords actually present, not the upstream Ajv tool.
It deliberately does not infer missing data or turn field defaults into facts.

The upstream schema descriptions identify real-client discrepancies: PCB groupId
can actually be numeric 0 although its schema says string; VIA zIndex can be
absent although required. Conformity errors therefore are **not** proof that a
native file is invalid. Do not rewrite imported fields merely to silence them.
Electrical connectivity, units, visual quality and host import remain separate.

## Viewer integration

Build the separately installed `easyeda/easyeda-viewer` at reviewed commit
`a60b22d098d25850d1f28427e51dd2619b008ed9`, then serve its dist/index.html on an
explicit loopback HTTP(S) URL. Serve the generated review page through localhost
as well. The renderer is not bundled and actual rendering is NOT RUN in this
integration; `prepared` only means the wrapper was generated.

The adapter sends files only after explicit file selection, supports designator
location and checks both postMessage origin and source window. It uses an exact
targetOrigin, rejects unknown commands and hides annotation UI. The local viewer
is trusted code: hiding UI is not a security boundary against a malicious build.
No public viewer/CDN is accepted. This does not establish that the separately
provided viewer bytes match the reviewed commit; verify its build independently.

Annotations are independent review data, never engineering edits. Export is
supported only via the documented same-origin API v1.2.0; projectId and revision
must match. Cross-origin postMessage cannot export/change annotations. No
annotation persistence service is supplied, and font differences mean viewer
screenshots are not official EDA exports.

## Sources and licensing

- Format schemas: `easyeda/easyeda-format-skill` commit
  `4fcab1747d47b2ae01d7f93a485859970c5cf933`, MIT. Six schemas copied verbatim with
  normalized line endings; copyright and license in `vendor/easyeda-format/LICENSE`.
- Viewer API/record structure reviewed at the commit above:
  `docs/easyeda-viewer-api.md`, `src/core/parse/records.ts`, Apache-2.0. No renderer
  code copied; our independent parser/adapter is under the parent project license.
- Source URLs and local file hashes in `vendor/easyeda-format/source.json`.

## Executed checks in this integration

- 21 targeted tests passed, including ZIP path/case/symlink rejection, malformed
  tickets, duplicate/nonfinite JSON, tombstones/DELETE_DOC distinction, schema
  scoping, negative CLI exit and a Node-executed viewer protocol contract test.
- Actual read-only inspection of the frozen dual-button LED archive (SHA256
  3c3d985353553fde412d71065b12fa911180c0a9d79649ac56b67bf81ddb9fc9)
  passed container/record structure: 2 entries, 4 atom tombstone records recognized.
- Wrapper generated at C:/Users/jlc/work/ecosystem-files-proof/review.html;
  report at the same directory real-inspect.json. Actual viewer rendering,
  browser interaction, and original EDA import remain NOT RUN.
