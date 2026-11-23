// Tract-parameter trajectory of a gestural score (ctypes).
//
// The VTL API only exports tube sequences and audio; for measuring a
// consonant we want the articulatory parameters frame by frame, so that
// vtlmap can give the exact area function and transfer-function peaks.
// Build (repository root):
//   clang++ -shared -fPIC -std=c++14 -O2 -w -Ibackend experiments/consonant-tuning/ctrack.cpp \
//     $(ls backend/*.cpp | grep -v SoundLib.cpp) -o build-mac/ctrack.so
#include "GeometricGlottis2025.h"
#include "GesturalScore.h"
#include "VocalTract.h"
#include "Constants.h"

#include <algorithm>
#include <string>

extern "C" {

int ct_num_params() { return VocalTract::NUM_PARAMS; }

// Writes up to max_frames rows of NUM_PARAMS tract parameters, sampled every
// step_s from t = 0. Returns the number of rows, or -1 on a load error.
int ct_tract_sequence(const char *speaker, const char *ges, double step_s,
                      double *out, int max_frames) {
  static VocalTract *vt = nullptr;
  static std::string loaded;
  static GeometricGlottis2025 glottis;   // only the tract curves are used
  if (!vt || loaded != speaker) {
    delete vt;
    vt = new VocalTract();
    try {
      vt->readFromXml(speaker);
    } catch (...) {
      delete vt;
      vt = nullptr;
      return -1;
    }
    vt->calculateAll();
    loaded = speaker;
  }
  GesturalScore score(vt, &glottis);
  bool inRange = true;
  if (!score.loadGesturesXml(std::string(ges), inRange)) return -1;
  score.calcCurves();
  double dur = score.getDuration_pt() / (double)AUDIO_SAMPLING_RATE_HZ;
  double glot[Glottis::MAX_CONTROL_PARAMS];
  int n = 0;
  for (double t = 0.0; t < dur && n < max_frames; t += step_s, n++)
    score.getParams(t, out + n * VocalTract::NUM_PARAMS, glot);
  return n;
}

}  // extern "C"
