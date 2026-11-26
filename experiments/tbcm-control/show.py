"""Per-vowel table of a variant from build/diag/<variant>/rows.json."""
import json, sys
rows = json.load(open(f"build/diag/{sys.argv[1]}/rows.json"))
print(f"{'key':6}{'v':3}{'prev':5}{'t0':>6}{'dur':>5}{'f0t':>6}{'err':>7}{'h12s':>6}{'h12q':>6}{'cqs':>6}{'cqq':>6}{'drs':>6}{'drq':>6}{'dc':>6}{'ta':>6}{'ia':>6}{'on':>6}")
for r in rows:
    s, q = r['sent'], r['steady']
    print(f"{r['key']:6}{r['vowel']:3}{r['prev']:5}{r['t0']:6.2f}{(r['t1']-r['t0'])*1000:5.0f}{s['f0_target']:6.0f}{s['f0_err']:7.2f}{s['h1h2']:6.1f}{q['h1h2']:6.1f}{s['cq']:6.2f}{q['cq']:6.2f}{s['drop']:6.1f}{q['drop']:6.1f}{s['dc']:6.1f}{s['ta']:6.2f}{s['ia']:6.2f}{r['onset']:6.0f}")
