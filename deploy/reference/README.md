# Reference copy of the production deploy workflow

`deploy.workflow.yml.txt` is a byte-identical copy of `.github/workflows/deploy.yml` from
`rooman-itsd/Rooman-Billing` at `a287d17`.

- It is stored here, outside `.github/workflows/` and with a `.txt` extension, so GitHub Actions never runs it.
- This repository therefore cannot build or publish images to `ghcr.io/rooman-itsd/*`, the production images.
- `backend/tests/test_deployment_config.py` reads this copy, so the deployment checks still cover it.

Don't move it back into `.github/workflows/`. Moving production to this repository needs a
separate, explicitly approved migration plan.
