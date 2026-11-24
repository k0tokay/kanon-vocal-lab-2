"""Speaker from an estimate (build/est/*.json): static parameters, modal shape, pressure and aspiration.
python3 estimate_speaker.py estimate.json aspiration_dB cutoff_Hz out.speaker [f0_control]"""
import sys, json, make_speaker as ms, explore as X
src, asp, cut, out = sys.argv[1:5]; f0c = float(sys.argv[5]) if len(sys.argv) > 5 else 1
p = json.load(open(src))[0]['par']; r = lambda v: round(v, 3)
STA = dict(rest_length='rest_length', rest_thickness='rest_thickness', mucosa_depth='mucosa_depth', ligament_depth='ligament_depth', muscle_depth='muscle_depth', cover_shear='cover_shear_modulus', body_shear='body_shear_modulus', convergence='convergence', posterior_scale='posterior_scale')
static = {a: float('%.4g' % p[n]) for n, a in STA.items()}; static.update(aspiration_strength=float(asp), aspiration_cutoff=float(cut), f0_control=f0c)
modal = (r(p['LCA']), r(p['IA']), r(max(0, p['PCA'])), r(p['CT']), r(p['TA']), 25)
sh = dict(ms.SHAPES); sh['modal'] = sh['default'] = modal
ms.convert(X.G, out, static=static, shapes=sh, pressure=round(p['pressure'], -1)); print(modal, round(p['pressure'], -1), static)
