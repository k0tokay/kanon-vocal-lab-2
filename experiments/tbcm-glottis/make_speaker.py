"""Add the triangular body-cover glottis to a speaker file and select it.

    python3 make_speaker.py ../../speakers/fulkhisa-kanon/fulkhisa-kanon-v1-1-0.speaker out.speaker

The other glottis models and the vocal tract stay as they are. A VTL without
BodyCoverGlottis cannot read the result."""
import re, sys

STATIC = [  # name, abbr, unit, min, max, default, value for Kanon
    ("Rest length", "rest_length", "cm", .3, 2, 1, 1.0),
    ("Rest thickness", "rest_thickness", "cm", .05, .8, .2, .2),
    ("Mucosa depth", "mucosa_depth", "cm", .02, .4, .15, .15),
    ("Ligament depth", "ligament_depth", "cm", .02, .4, .15, .15),
    ("Muscle depth", "muscle_depth", "cm", .05, .8, .3, .3),
    ("Cover shear modulus", "cover_shear_modulus", "dPa", 500, 50000, 3000, 3000),
    ("Body shear modulus", "body_shear_modulus", "dPa", 500, 100000, 6000, 6000),
    ("Convergence", "convergence", "", 0, 2, 0, 0),
    ("Posterior opening scale", "posterior_scale", "", 0, 2, 1, 1),
    ("Epilarynx area", "epilarynx_area", "cm^2", .05, 5, .5, .5),
    ("Inlet length", "inlet_length", "cm", 0, .5, .06, .06),
    ("Posture speed", "posture_speed", "", .2, 20, 1, 12),
    ("F0 control", "f0_control", "", 0, 1, 1, 1),
    ("Maximal strain", "max_strain", "", 0, .6, .3, .3),
    ("Aspiration strength", "aspiration_strength", "dB", -60, 0, -40, -34),
    ("Aspiration cutoff", "aspiration_cutoff", "Hz", 300, 8000, 1000, 2000),
    ("Background noise level", "background_noise_level", "dB", -120, 0, -120, -120),
    ("Background noise cutoff", "background_noise_cutoff", "Hz", 20, 20000, 300, 300),
]
CONTROL = [  # name, abbr, unit, min, max, default
    ("f0", "f0", "Hz", 40, 1000, 220), ("Subglottal pressure", "pressure", "dPa", 0, 30000, 8000),
    ("LCA activation", "act_lca", "", 0, 1, .6), ("IA activation", "act_ia", "", 0, 1, .6),
    ("PCA activation", "act_pca", "", 0, 1, 0), ("CT activation", "act_ct", "", 0, 1, .2),
    ("TA activation", "act_ta", "", 0, 1, .25), ("Flutter", "flutter", "%", 0, 100, 25),
]
SHAPES = {  # LCA, IA, PCA, CT, TA, flutter
    "default": (.57, .40, 0, .2, .17, 25),
    "modal": (.57, .40, 0, .2, .17, 25),
    "falsetto": (.56, .40, 0, .2, .08, 25),
    "chest": (.62, .50, 0, .2, .40, 25),
    "mixed": (.62, .55, 0, .2, .25, 25),
    "pressed": (.90, .90, 0, .2, .50, 25),
    "breathy": (.50, .30, 0, .2, .18, 25),
    "stop": (1.0, 1.0, 0, .2, .80, 25),
    "h": (.2, .2, 0, .2, .15, 25),
    "whisper": (.60, 0, .1, .2, .10, 25),
    "hoarse": (.50, 0, 0, .2, .25, 25),
    "hoarse2": (.95, .20, 0, .2, .60, 25),
    "voiced-fricative": (.40, .40, 0, .2, .20, 10),
    "voiced-plosive": (.52, .45, 0, .2, .20, 10),
    "voiceless-fricative": (.15, .15, 0, .2, .15, 10),
    "voiceless-plosive": (.2, .2, 0, .2, .15, 10),
}


def block(static=None, shapes=SHAPES, pressure=8000):
    static = static or {}
    out = ['    <glottis_model type="Triangular body-cover glottis" selected="1">', '      <static_params>']
    for i, (n, a, u, lo, hi, d, v) in enumerate(STATIC):
        v = static.get(a, v)
        out.append(f'        <param index="{i}" name="{n}" abbr="{a}" unit="{u}" min="{lo:.6f}" max="{hi:.6f}" default="{d:.6f}" value="{v:.6f}"/>')
    out += ['      </static_params>', '      <control_params>']
    modal = [203.187335, pressure, *shapes["modal"]]
    for i, (n, a, u, lo, hi, d) in enumerate(CONTROL):
        out.append(f'        <param index="{i}" name="{n}" abbr="{a}" unit="{u}" min="{lo:.6f}" max="{hi:.6f}" default="{d:.6f}" value="{0 if i == 1 else modal[i]:.6f}"/>')
    out += ['      </control_params>', '      <shapes>']
    for name, p in shapes.items():
        out.append(f'        <shape name="{name}">')
        for i, v in enumerate([203.187335, pressure, *p]):
            out.append(f'          <control_param index="{i}" value="{v:.6f}"/>')
        out.append('        </shape>')
    out += ['      </shapes>', '    </glottis_model>', '']
    return out


def convert(src, dst, **kw):
    t = open(src, newline='').read()
    nl = '\r\n' if '\r\n' in t else '\n'
    t = re.sub(r'\s*<glottis_model type="Triangular body-cover glottis".*?</glottis_model>', '', t, flags=re.S)
    t = re.sub(r'(<glottis_model type="[^"]+" selected=")1"', r'\g<1>0"', t)
    i = t.index('  </glottis_models>')
    open(dst, 'w', newline='').write(t[:i] + nl.join(block(**kw)) + t[i:])


if __name__ == '__main__':
    convert(sys.argv[1], sys.argv[2])
