# Gold workflows

One JSON file per evaluation video, each a hand-authored `WorkflowSpec` (the schema in
`src/morrow/schemas.py`). These are the ground truth `eval/metrics.py` scores against.

## Scope rule (how to decide what belongs in the spec)

**The description defines requested scope. The video supplies participants and the
demonstrated method. Incidental scene objects are excluded, and extra demonstrated
actions do not become required goals without textual or mechanical support.**

Consequences, applied in the current gold:

- **Incidental scene objects are not entities.** In the office clip, the markers,
  highlighter pack and folders on the desk are context, not workflow participants —
  including them would turn entity recall into scene-object detection. They appear only
  inside the scope-ambiguity question in `unknowns`.
- **Extra demonstrated actions are not goals.** The single-product clip shows a shipping
  label being applied, but the description only asks to pack and close. The label is
  therefore absent from the executable spec (no entity, step, or goal); synthesis is
  expected to detect it in observations and then filter it as out of scope.
- **A role selector is enough; hidden contents are not an unknown.** "Paper-wrapped
  product" fully identifies the participant for this task, so the product's contents are
  not listed in `unknowns`. An `accepted` spec must not carry questions that imply
  confirmation is needed; genuine scope ambiguity (which items to pack) does, and keeps
  that clip at `needs_confirmation`.

## Rules that keep the benchmark honest

- **No gold label ever enters inference.** These files are read only by the scorer,
  never passed to `morrow analyze`. If a gold spec leaks into a prompt, the number is meaningless.
- Author the gold spec from the video and its description *before* looking at any model output.
- Cover a narrow family to start — picking, placing, inserting, sorting, closing — across
  20–30 unseen clips. Breadth comes after the model is reliable on one family.
- When the demonstration genuinely underspecifies the task, the gold `status` should be
  `needs_confirmation` or `needs_new_video`, and the gap belongs in `unknowns`. A model
  that confidently invents the missing detail should lose points, not gain them.
