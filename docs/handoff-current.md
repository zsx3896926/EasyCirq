# v1.0.1 publication recovery

- v1.0.0 release exists, tag ce9b289; no installer assets were uploaded.
- Release run 40463286671 failed in Python 3.10 full tests: adapters.py used a
  Python 3.12-only nested f-string. Existing PR validation used default newer
  Python; updater tests on 3.10 did not import the design engine.
- Fixed fallback text ID formatting without changing its result; added full
  Python 3.10/3.13 CI. Worktree C:/Users/jlc/work/hds-release-hotfix,
  branch fix/release-python310. Source version 1.0.1.
- Recovery workflow builds/tests exact main on four OS/Python combinations,
  builds clean packages, verifies installed archive smoke, creates draft v1.0.1
  with complete assets, then publishes latest and marks v1.0.0 superseded.
  It refuses overwriting existing releases/assets and does not move v1.0.0 tag.
- Targeted design engine: 73 OK. Local full suite / clean package and exact-head
  Python 3.10 CI must be verified before final publication completion.
- No EDA calls or installed user clients changed. Existing live/renderer limits
  remain as documented. Notes: docs/releases/v1.0.1.md.
