"""Export accepted checkpoints as GUI-selectable vowel shapes without editing the speaker."""
import csv
import json
import re
from pathlib import Path
import xml.etree.ElementTree as ET

base=Path(__file__).resolve().parent
source=base.parents[1]/"speakers/fulkhisa-kanon/fulkhisa-kanon-v0-8-vowel-variation.speaker"
folder=base/"results/integrated-long"
text=source.read_bytes()
xml=ET.fromstring(text)
params=sorted(xml.findall(".//vocal_tract_model/anatomy/param"),key=lambda p:int(p.get("index")))
keys=[p.get("name") for p in params]
with (folder/"checkpoints.csv").open("w") as f:
    writer=csv.writer(f)
    writer.writerow(["shape","path_length","distance","transfer_dB","max_formant_error_percent",*keys])
    shapes=[]
    for vowel in "ao":
        for mode in ("insensitive","sensitive"):
            points=json.loads((folder/f"{vowel}-{mode}.json").read_text())
            for i,p in enumerate(points,1):
                name=f"{vowel}-{mode}-{i:03}"
                assert len(p['x'])==len(keys)==19
                writer.writerow([name,p['length'],p['distance'],p['transfer_dB'],p['formant_error_percent'],*p['x']])
                block=ET.Element("shape",name=name)
                for k,v in zip(keys,p['x']):
                    ET.SubElement(block,"param",name=k,value=f"{v:.9f}")
                shapes.append(ET.tostring(block))
pos=text.index(b"</shapes>")
data=text[:pos]+b"\n".join(shapes)+b"\n"+text[pos:]
assert len(ET.fromstring(data).findall(".//vocal_tract_model/shapes/shape"))==len(xml.findall(".//vocal_tract_model/shapes/shape"))+len(shapes)
(folder/"kanon-long-paths.speaker").write_bytes(data)
