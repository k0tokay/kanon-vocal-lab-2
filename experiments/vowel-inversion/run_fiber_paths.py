"""Run build-mac/fiber-path on the two previously fitted manual /a/ shapes."""
import csv
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[2]
results = Path(__file__).resolve().parent / "results"
folder = results / "fiber-paths"
folder.mkdir(exist_ok=True)
speaker = root / "speakers/fulkhisa-kanon/fulkhisa-kanon-v0-8-vowel-variation.speaker"
with (results / "manual/shapes.csv").open() as source:
    rows = [row for row in csv.DictReader(source) if row["vowel"] == "a"]
reference = next(row for row in rows if row["stage"] == "reference")
labels = list(reference)[list(reference).index("HX"):]
for row in rows:
    if row["stage"] != "fitted":
        continue
    values = " ".join(r[k] for r in (reference, row) for k in labels)
    for mode in ("straight", "corrected"):
        output = subprocess.check_output(
            [root / "build-mac/fiber-path", speaker, mode],
            input=values, cwd=root, text=True)
        path = folder / f"{row['start']}-{mode}.csv"
        records = list(csv.DictReader(output.splitlines()))
        assert len(records) == 513
        path.write_text(output)
        print(path.name, max(float(r["error_log"]) for r in records),
              records[-1]["error_log"], min(float(r["min_area_cm2"]) for r in records))
