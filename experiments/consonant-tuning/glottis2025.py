"""Select Geometric glottis 2025 in a speaker file and fill it from the file's
own Geometric glottis 2019 block (static params and all shapes; the 2019
double pulsing is dropped, skewness is replaced by --pulse-shape, rel_amp is
capped at 1). Writes a new file; the source is not changed."""
import re, sys
def blk(t, name):
    i = t.index(f'<glottis_model type="{name}"'); j = t.index('</glottis_model>', i) + len('</glottis_model>'); return i, j
def convert(src, dst, modal=None, pulse_shape=0.5, jitter=10.0, statics_from_2019=True):
    t = open(src, newline='').read()
    nl = '\r\n' if '\r\n' in t else '\n'
    i9, j9 = blk(t, 'Geometric glottis 2019'); g19 = t[i9:j9]
    i5, j5 = blk(t, 'Geometric glottis 2025'); g25 = t[i5:j5]
    if statics_from_2019:
        st19 = dict(re.findall(r'<param index="(\d)" name="[^"]+"[^>]*value="([^"]+)"', g19[g19.index('<static_params>'):g19.index('</static_params>')]))
        s = g25[g25.index('<static_params>'):g25.index('</static_params>')]
        for k in '0123':
            s = re.sub(rf'(<param index="{k}" [^>]*value=")[^"]+', rf'\g<1>{st19[k]}', s)
        s = re.sub(r'(<param index="4" [^>]*value=")[^"]+', rf'\g<1>{jitter:.6f}', s)
        g25 = g25.replace(g25[g25.index('<static_params>'):g25.index('</static_params>')], s)
        shapes = []
        for m in re.finditer(r'<shape name="([^"]+)">(.*?)</shape>', g19, re.S):
            v = [float(x) for x in re.findall(r'value="([^"]+)"', m.group(2))]
            if m.group(1) == 'modal' and modal:
                for k, x in modal.items(): v[k] = x
            w = v[:6] + [min(v[6], 1.0), pulse_shape, v[9]]
            shapes.append(f'        <shape name="{m.group(1)}">{nl}' + ''.join(f'          <control_param index="{k}" value="{x:.6f}"/>{nl}' for k, x in enumerate(w)) + f'        </shape>{nl}')
        a = g25.index('<shapes>') + len('<shapes>'); b = g25.index('</shapes>')
        g25 = g25[:a] + nl + ''.join(shapes) + '      ' + g25[b:]
    g19 = g19.replace('selected="1"', 'selected="0"'); g25 = g25.replace('selected="0"', 'selected="1"')
    out = t[:i9] + g19 + t[j9:i5] + g25 + t[j5:] if i9 < i5 else t[:i5] + g25 + t[j5:i9] + g19 + t[j9:]
    open(dst, 'w', newline='').write(out)
def set_rest_length(path, length_cm):
    t = open(path, newline='').read(); i = t.index('Geometric glottis 2025'); j = t.index('</static_params>', i)
    g = re.sub(r'(<param index="1" name="Rest length"[^>]*value=")[^"]+', rf'\g<1>{length_cm:.6f}', t[i:j])
    open(path, 'w', newline='').write(t[:i] + g + t[j:])


def set_aspiration(path, strength_dB, cutoff_Hz, model='Geometric glottis 2025'):
    """Write the "Aspiration strength" / "Aspiration cutoff" static params
    (added on branch consonant-tuning; a VTL without them cannot read the file)."""
    t = open(path, newline='').read(); nl = '\r\n' if '\r\n' in t else '\n'
    i = t.index(f'<glottis_model type="{model}"'); j = t.index('</static_params>', i)
    s = t[i:j]
    s = re.sub(r'\s*<param index="\d+" name="Aspiration (strength|cutoff)"[^>]*/>', '', s)
    n = len(re.findall(r'<param index=', s))
    k = s.rstrip().rfind('/>') + 2
    add = (f'{nl}        <param index="{n}" name="Aspiration strength" abbr="aspiration_strength" unit="dB" '
           f'min="-60.000000" max="0.000000" default="-40.000000" value="{strength_dB:.6f}"/>'
           f'{nl}        <param index="{n+1}" name="Aspiration cutoff" abbr="aspiration_cutoff" unit="Hz" '
           f'min="300.000000" max="8000.000000" default="1000.000000" value="{cutoff_Hz:.6f}"/>')
    s = s[:k] + add + s[k:]
    open(path, 'w', newline='').write(t[:i] + s + t[j:])


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('src'); ap.add_argument('dst')
    ap.add_argument('--modal', default='', help='modal control params, e.g. 2=0.03,3=0.03,4=0.011,5=1.222,6=1')
    ap.add_argument('--rest-length', type=float)
    ap.add_argument('--pulse-shape', type=float, default=0.5)
    ap.add_argument('--jitter', type=float, default=10.0)
    ap.add_argument('--aspiration', help='strength_dB,cutoff_Hz (VTL: -40,1000)')
    a = ap.parse_args()
    modal = {int(k): float(v) for k, v in (kv.split('=') for kv in a.modal.split(',') if kv)}
    convert(a.src, a.dst, modal=modal, pulse_shape=a.pulse_shape, jitter=a.jitter)
    if a.rest_length:
        set_rest_length(a.dst, a.rest_length)
    if a.aspiration:
        set_aspiration(a.dst, *(float(v) for v in a.aspiration.split(',')))
    print('wrote', a.dst)
