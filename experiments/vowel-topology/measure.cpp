#include "../vowel-inversion/vowel_measurement.h"
static VocalTract tract;
static TlModel model;
extern "C" void init(const char *speaker) { tract.readFromXml(speaker); }
extern "C" int evaluate(const double *values, double *out) {
  Shape x;
  std::copy_n(values, x.size(), x.begin());
  auto m = measure(tract, model, x);
  std::copy(m.f.begin(), m.f.end(), out);
  // The tongue-side floor keeps up to 0.15 cm^2 open where the tongue
  // touches the palate, velum or uvula, so test the area before it.
  return m.valid && std::min(m.area, tract.minAreaBeforeTongueSideFloor_cm2) >= .12;
}


// Smallest centre-line cross-sectional area before VTL raises it to the
// tongue-side minimum (up to 0.15 cm^2 from TS2/TS3): with the floor a
// tongue touching the palate, velum or uvula still leaves the tube open.
extern "C" double open_area(const double *values) {
  Shape x;
  std::copy_n(values, x.size(), x.begin());
  measure(tract, model, x);
  return tract.minAreaBeforeTongueSideFloor_cm2;
}
