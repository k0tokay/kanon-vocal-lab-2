// Synthesize a gestural score and log what happens at the glottis and at the oral
// constriction (ctypes). The VTL API returns only audio.
// Build (repository root):
//   clang++ -shared -fPIC -std=c++14 -O2 -w -Ibackend experiments/consonant-articulation/cdiag.cpp \
//     $(ls backend/*.cpp | grep -v SoundLib.cpp) -o build-mac/cdiag.so
#include "Constants.h"
#include "GeometricGlottis2019.h"
#include "GeometricGlottis2025.h"
#include "GesturalScore.h"
#include "Synthesizer.h"
#include "TdsModel.h"
#include "VocalTract.h"
#include "XmlNode.h"

#include <cstring>
#include <string>
#include <vector>

extern "C" {

int cd_num_columns() { return 11; }

// One row every `step` samples: t, lung pressure (dPa), x_bottom, x_top, rel_amp, glottal
// area (cm2, the two glottis sections' minimum), mouth flow (cm3/s), intraoral pressure just
// above the glottis (dPa), oral minimum area (cm2), its position (cm), VO.
int cd_run(const char *speaker, const char *ges, int step, double *rows, int max_rows) {
  // On the heap: these objects are too large for the stack. Not freed (diagnosis only).
  VocalTract &vt = *new VocalTract();
  GeometricGlottis2025 &glottis = *new GeometricGlottis2025();
  try { vt.readFromXml(speaker); } catch (...) { return -1; }
  vt.calculateAll();
  XmlNode *root = xmlParseFile(speaker, "speaker");
  if (!root) return -2;
  XmlNode *models = root->getChildElement("glottis_models");
  bool ok = false;
  for (int i = 0; i < models->numChildElements("glottis_model"); i++) {
    XmlNode *m = models->getChildElement("glottis_model", i);
    if (m->getAttributeString("type") == glottis.getName()) ok = glottis.readFromXml(*m);
  }
  delete root;
  if (!ok) return -3;
  glottis.resetMotion();
  GesturalScore &score = *new GesturalScore(&vt, &glottis);
  bool inRange = true;
  if (!score.loadGesturesXml(std::string(ges), inRange)) return -4;
  score.calcCurves();

  TdsModel &model = *new TdsModel();
  Synthesizer &synth = *new Synthesizer();
  synth.init(&glottis, &vt, &model);
  glottis.resetMotion();
  synth.reset();
  std::vector<double> audio;
  int n = score.getDuration_pt(), row = 0;
  double tp[VocalTract::NUM_PARAMS], gp[Glottis::MAX_CONTROL_PARAMS];
  for (int s = 0; s < n && row < max_rows; s += step) {
    score.getParams((double)s / AUDIO_SAMPLING_RATE_HZ, tp, gp);
    synth.addChunk(gp, tp, s == 0 ? 0 : step, audio);
    double *r = rows + row * cd_num_columns();
    r[0] = (double)s / AUDIO_SAMPLING_RATE_HZ;
    r[1] = gp[1]; r[2] = gp[2]; r[3] = gp[3]; r[4] = gp[6];
    TdsModel::TubeSection *t = model.tubeSection;
    r[5] = std::min(t[Tube::LOWER_GLOTTIS_SECTION].area, t[Tube::UPPER_GLOTTIS_SECTION].area);
    double in = 0.0, out = 0.0;
    model.getSectionFlow(Tube::LAST_MOUTH_SECTION, in, out);
    r[6] = out;
    r[7] = model.getSectionPressure(Tube::FIRST_PHARYNX_SECTION + 2);
    double m = 1e9, p = 0;
    for (int i = Tube::FIRST_PHARYNX_SECTION + 4; i <= Tube::LAST_MOUTH_SECTION; i++)
      if (t[i].area < m) { m = t[i].area; p = t[i].pos + .5 * t[i].length; }
    r[8] = m; r[9] = p; r[10] = tp[VocalTract::VO];
    row++;
  }
  return row;
}

}  // extern "C"
