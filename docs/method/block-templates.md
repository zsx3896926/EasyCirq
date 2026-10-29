# Block templates (drift-free placement)

A block template freezes the *relative* geometry of a real, well-placed block
instance: `easycirq-block-template/v1 {block, origin{role,ref,x,y}, parts[],
pins[], bbox}`.  Instantiation is a pure translation to a planned origin, so
the same circuit lands at exactly the same relative positions every time —
unlike `block-apply`, whose grid layout shifts near page edges.

## Pipeline

1. `tools/layout2/role_resolver.resolve_roles()` binds block manifest roles to
   page designators deterministically (MPN + `internal_nets` topology,
   backtracking, ambiguity raises);
2. `tools/layout2/templates.extract_template()` freezes the instance;
3. `tools/pipeline.py --engine templates` translates each template to the
   planned module bbox and emits absolute `parts[]` in the apply bundle.

## Shipped templates

| template | parts | origin | source |
|---|---|---|---|
| `aw8737_classd_spk.template.json` | 12 | U2 | A-audio page (explicit role map: R_INP=R3, R_INN=R2, R_SHDN=R4, C_VDD1/2=C15/C16, C_C1/2=C11/C12, FB_P/N=FB2/FB1, C_EMI_P/N=C13/C14) |
| `mems_mic_analog.template.json` | 5 | MK1 | A-audio page (R_OUT=R6, R_REF=R7, R_FILT=R5, C_VDD=C17) |

Ambiguous blocks (e.g. ES8311 power-decoupling caps share identical nets/MPN)
stay unresolved on purpose: the resolver refuses to guess; they need a manual
role map before they can be frozen.
