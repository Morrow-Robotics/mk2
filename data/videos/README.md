# Videos

MK2 is self-contained: put the Baseline-0 source videos here, in this repo — do not
point the harness at another checkout. The `.mp4` files are gitignored (they are inputs,
not code); this README is the only thing committed.

Expected files:

| clip | filename |
|---|---|
| development | `pexels_7581335.mp4` (multi-item office packing) |
| holdout | `pexels_7855140.mp4` (single-product packing) |
| negative | `mixkit_42119.mp4` (incomplete / insufficient view) |

Then:

```bash
python eval/run.py development --video data/videos/pexels_7581335.mp4
python eval/run.py holdout     --video data/videos/pexels_7855140.mp4
python eval/run.py negative    --video data/videos/mixkit_42119.mp4
```

The exact video bytes are hashed into every run's `manifest.json` and its run id, so the
provenance is pinned regardless of where the file originally came from.
