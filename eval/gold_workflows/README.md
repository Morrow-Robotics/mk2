# Gold workflows

One JSON file per evaluation video, each a hand-authored `WorkflowSpec` (the schema in
`src/morrow/schemas.py`). These are the ground truth `eval/metrics.py` scores against.

Rules that keep the benchmark honest:

- **No gold label ever enters inference.** These files are read only by the scorer,
  never passed to `morrow analyze`. If a gold spec leaks into a prompt, the number is meaningless.
- Author the gold spec from the video and its description *before* looking at any model output.
- Cover a narrow family to start — picking, placing, inserting, sorting, closing — across
  20–30 unseen clips. Breadth comes after the model is reliable on one family.
- When the demonstration genuinely underspecifies the task, the gold `status` should be
  `needs_confirmation` or `needs_new_video`, and the gap belongs in `unknowns`. A model
  that confidently invents the missing detail should lose points, not gain them.
