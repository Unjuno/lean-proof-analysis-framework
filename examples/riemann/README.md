# First case study: Lean Riemann Hypothesis project

Upstream: [leanprover-community/riemann-hypothesis](https://github.com/leanprover-community/riemann-hypothesis)

Pinned commit: `aa01316131472849f8e3b5b3e49f04d0a06c983f`

This directory pins **10 selected Lean files** in `expected_blobs.json` by Git blob SHA-1. They are a *partial, illustrative sample*, not an exhaustive proof analysis. The sources are not committed here: the fetcher downloads them locally and checks all hashes.

```bash
python examples/riemann/fetch_pilot.py --manifest examples/riemann/expected_blobs.json --out work/rh-pilot
lpaf analyze work/rh-pilot --out reports/generated/rh-pilot \
  --repo leanprover-community/riemann-hypothesis \
  --commit aa01316131472849f8e3b5b3e49f04d0a06c983f \
  --expected-manifest examples/riemann/expected_blobs.json \
  --entry riemannHypothesis --json
```

`Challenge.lean` contains intentional `sorry` placeholders in the *challenge task* and must not be presented as an error in the final proof. Please check the original upstream source and its license before redistribution. The output is a **navigation aid**, never a correctness result.
