package app

// skill_asset.go — locating a file that ships inside the SKILL tree,
// cwd-independently.
//
// Two different assets now need this: bom-enrich.py (issue #115) and
// standard-parts.json (the role-id → deviceUuid bridge `sch block-apply` needs
// to place a block's parts). Both live under .agents/skills/easycirq-agent/, both must be
// findable from WHEREVER the agent runs the CLI (a project dir, /tmp, $HOME), and
// both have the same fallback ladder — so the ladder lives here once instead of
// being copied per asset.
//
// Why this exists at all: internal/blocks go:embeds the block library, but
// go:embed cannot reach `..`, so standard-parts.json (the skill's parts library)
// cannot ride along in the binary. Until that bridge is embedded, blocks are
// self-contained but their PARTS are not — see internal/blocks/placement.go.

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/zsx3896926/EasyCirq/runtime/internal/selfupdate"
)

// skillAsset describes one locatable skill file.
type skillAsset struct {
	// name is the bare filename, used in probe messages and the $PATH lookup.
	name string
	// rels are the asset's paths relative to a skills ROOT (a dir holding
	// per-skill dirs). Extra entries keep pre-merge skill layouts working.
	rels []string
	// searchPath enables the $PATH fallback. Meaningful for executables only —
	// a JSON data file is never on $PATH, and probing for it there would only
	// add a misleading line to the error.
	searchPath bool
	// flagHint names the CLI flag that overrides the search, for the error text.
	flagHint string
}

// resolve finds the asset, in priority order:
//
//  1. explicit (the --flag) — used if it exists, hard error if it doesn't (a typo
//     must not silently fall through to some other copy);
//  2. $EASYCIRQ_SKILLS_DIR/<skill>/… — the deployment override;
//  3. the INSTALLED skill dirs (~/.claude/…, ~/.codex/…, ~/.agents/…),
//     resolved via selfupdate.Targets so this never drifts from `easycirq skill
//     status` / `skill sync`;
//  4. .agents/skills/ walked up from the running binary (dev: ./bin/easycirq);
//  5. .agents/skills/ walked up from the working directory;
//  6. the bare name on $PATH (executables only).
//
// The error lists every path probed, so a failure says exactly where to put the
// file instead of just "not found".
func (a skillAsset) resolve(explicit string) (string, error) {
	var probed []string
	seen := map[string]bool{}
	// hit records a candidate and reports whether it is a usable file. Repeat
	// candidates are probed once: two rels can collapse to the same path under an
	// installed skill dir, and a doubled line in the error only reads as noise.
	hit := func(path string) bool {
		if !seen[path] {
			seen[path] = true
			probed = append(probed, path)
		}
		st, err := os.Stat(path)
		return err == nil && !st.IsDir()
	}

	if explicit = strings.TrimSpace(explicit); explicit != "" {
		if hit(explicit) {
			return explicit, nil
		}
		return "", fmt.Errorf("%s %s: no such file", a.flagHint, explicit)
	}

	// 2. Explicit skills-root override.
	if root := strings.TrimSpace(os.Getenv("EASYCIRQ_SKILLS_DIR")); root != "" {
		for _, rel := range a.rels {
			if c := filepath.Join(root, filepath.FromSlash(rel)); hit(c) {
				return c, nil
			}
		}
	}

	// 3. Installed skill dirs (each Target.Dir is …/skills/easycirq-agent).
	// rels are skills-root-relative, so strip the leading skill-name segment.
	for _, t := range selfupdate.Targets(false) {
		for _, rel := range a.rels {
			sub := rel
			if i := strings.IndexByte(sub, '/'); i >= 0 {
				sub = sub[i+1:]
			}
			if c := filepath.Join(t.Dir, filepath.FromSlash(sub)); hit(c) {
				return c, nil
			}
		}
	}

	// 4/5. Repository skills walked up from the binary, then from cwd.
	walkUp := func(dir string) (string, bool) {
		for i := 0; i < 8; i++ {
			for _, rel := range a.rels {
				if c := filepath.Join(dir, ".agents", "skills", filepath.FromSlash(rel)); hit(c) {
					return c, true
				}
			}
			parent := filepath.Dir(dir)
			if parent == dir {
				break
			}
			dir = parent
		}
		return "", false
	}
	if exe, err := os.Executable(); err == nil {
		// Resolve symlinks: a /usr/local/bin/easycirq symlinked into the repo's
		// bin/ should walk up the REPO, not /usr/local.
		if real, rerr := filepath.EvalSymlinks(exe); rerr == nil {
			exe = real
		}
		if path, ok := walkUp(filepath.Dir(exe)); ok {
			return path, nil
		}
	}
	if cwd, err := os.Getwd(); err == nil {
		if path, ok := walkUp(cwd); ok {
			return path, nil
		}
	}

	// 6. PATH (executables only).
	if a.searchPath {
		if path, err := exec.LookPath(a.name); err == nil {
			probed = append(probed, "$PATH/"+a.name+" → "+path)
			return path, nil
		}
		probed = append(probed, "$PATH/"+a.name)
	}

	return "", fmt.Errorf("%s not found — probed:\n  %s\npass %s /path/to/%s, "+
		"set EASYCIRQ_SKILLS_DIR to your skills root, or install the skill (`easycirq skill sync --create-missing`)",
		a.name, strings.Join(probed, "\n  "), a.flagHint, a.name)
}

// standardPartsAsset is the parts library: the role-id ("res.1k_0402") →
// {libraryUuid, deviceUuid} bridge. `sch block-apply` cannot place anything
// without it.
var standardPartsAsset = skillAsset{
	name: "standard-parts.json",
	rels: []string{
		"design-hardware/references/standard-parts.json",
		"easycirq-agent/references/standard-parts.json",
		"easycirq-schematic/references/standard-parts.json", // pre-merge skill name
	},
	flagHint: "--parts",
}

// resolveStandardParts locates standard-parts.json for block instantiation.
func resolveStandardParts(explicit string) (string, error) {
	return standardPartsAsset.resolve(explicit)
}

// shadowedStandardParts lists the OTHER copies of standard-parts.json that exist on
// disk, nearest-first, excluding the one that was actually used.
//
// Why this exists (2026-11-02): the resolver walks a ladder and returns the FIRST
// hit, silently. On this machine three installed skill dirs each held a copy —
// .claude and .codex at 160 parts, .agents at 171. The block reported
//
//	role D: part "diode.1n4148w_sod123" not found in standard-parts.json
//
// for a key that was sitting on disk, because the resolver had hit a stale copy and
// the message never said which file it read. Naming the resolved path fixes half of
// that; naming the shadowed copies fixes the other half, because "there are three
// of these and you are reading the wrong one" is the actual situation.
func shadowedStandardParts(resolved string) []string {
	var out []string
	seen := map[string]bool{}
	cleanResolved := filepath.Clean(resolved)
	add := func(candidate string) {
		candidate = filepath.Clean(candidate)
		if seen[candidate] || candidate == cleanResolved {
			return
		}
		seen[candidate] = true
		st, err := os.Stat(candidate)
		if err != nil || st.IsDir() {
			return
		}
		out = append(out, candidate)
	}
	if root := strings.TrimSpace(os.Getenv("EASYCIRQ_SKILLS_DIR")); root != "" {
		for _, rel := range standardPartsAsset.rels {
			add(filepath.Join(root, filepath.FromSlash(rel)))
		}
	}
	for _, t := range selfupdate.Targets(false) {
		for _, rel := range standardPartsAsset.rels {
			sub := rel
			if i := strings.IndexByte(sub, '/'); i >= 0 {
				sub = sub[i+1:]
			}
			add(filepath.Join(t.Dir, filepath.FromSlash(sub)))
		}
	}
	walkUp := func(dir string) {
		for i := 0; i < 8; i++ {
			for _, rel := range standardPartsAsset.rels {
				add(filepath.Join(dir, ".agents", "skills", filepath.FromSlash(rel)))
			}
			parent := filepath.Dir(dir)
			if parent == dir {
				return
			}
			dir = parent
		}
	}
	if exe, err := os.Executable(); err == nil {
		if real, rerr := filepath.EvalSymlinks(exe); rerr == nil {
			exe = real
		}
		walkUp(filepath.Dir(exe))
	}
	if cwd, err := os.Getwd(); err == nil {
		walkUp(cwd)
	}
	return out
}

// standardPartsDiagnostic renders the "which file did I read, and what else is on
// disk" note appended to a parts-not-found refusal. Empty when there is nothing
// useful to say (a single copy, or an explicit --parts the user already knows).
func standardPartsDiagnostic(resolved string, shadowed []string) string {
	if strings.TrimSpace(resolved) == "" {
		return ""
	}
	var b strings.Builder
	fmt.Fprintf(&b, "\n  read: %s", resolved)
	if len(shadowed) > 0 {
		b.WriteString("\n  other copies on disk (the resolver returns the FIRST hit, so a stale")
		b.WriteString("\n  copy here is why a part can be missing while the file has it):")
		for _, copy := range shadowed {
			fmt.Fprintf(&b, "\n    %s", copy)
		}
		b.WriteString("\n  fix: `easycirq skill sync` (or copy the current file over them),")
		b.WriteString("\n       or pin the right one with --parts <path>")
	}
	return b.String()
}
