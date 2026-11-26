# Notes for Claude

VocalTractLab 2.4, extended to build the voice of Fulkhisa Kanon (降久嘉音) with physical models. Write to the user in Japanese.

## Where things go

- **Surveys, reports and other notes that are not code** go in `local/YYYY-MM-DD/` (the date the work starts), for example `local/2026-11-26/GUI調査/`. `local/` is git-ignored.
- `docs/` is git-ignored too. Never commit anything under `docs/`, and never quote it in commits or pull requests: the repository is public.
- Experiments live in `experiments/<name>/` with a README (Japanese). Large outputs go in each experiment's ignored `out/` or `build/`.
- Speakers live in `speakers/fulkhisa-kanon/fulkhisa-kanon-vX-Y-Z.speaker`. A new version gets an entry in `docs/話者の系譜.md` (local only).

## How work is run

- The session in the main checkout coordinates. Each task of its own runs in its own session and worktree, branched from `main`.
- A task session commits and pushes its own branch only. It never merges into `main` and never deletes branches. The coordinating session reviews, merges, and then removes the worktree and branch after moving untracked files that matter into `local/`.
- Commit and push at checkpoints without asking. Ask before a force push or history rewrite.
- Never commit or overwrite the user's hand-made files (`*-manual-edit*.speaker`, `*intuition*`, recording-derived files). Recordings and the JVS corpus stay out of git.

## Running things

- Python: `build-mac/py.sh script.py ...` (venv in `build-mac/venv`; sets `JVS_NPZ`, `VTL_LIB`, `VTL_SPEAKER`). `build-mac/` is git-ignored.
- GUI and API: `cmake -S . -B build-mac/gui && cmake --build build-mac/gui -j8`, then `./build-mac/gui/VocalTractLab2`.
