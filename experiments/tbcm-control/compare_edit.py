"""The consonant check of ../consonant-articulation (compare.py) for variants that edit the score.

    ./run.sh compare_edit.py variant ...     -> ../consonant-articulation/results/compare-<variant>.json
                                                (moved to results/consonants/ for table.py)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "consonant-articulation"))
import compare                     # noqa: E402
import variants                    # noqa: E402

accent = compare.accent
_patch = accent.patch_score


def main(names):
    for n in names:
        v = variants.VARIANTS[n]

        def patch(ges, segments, v=v):
            _patch(ges, segments)
            if v.get("edit"):
                v["edit"](ges, segments)
        accent.patch_score = patch
        compare.main([f"{n}={v.get('speaker', variants.BASE)}"])


if __name__ == "__main__":
    main(sys.argv[1:])
