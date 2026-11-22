#include "experiments/vowel-inversion/vowel_measurement.h"
static VocalTract tract;
static TlModel model;
extern "C" void init(const char *speaker) { tract.readFromXml(speaker); }
extern "C" int evaluate(const double *values, double *out) {
  Shape x;
  std::copy_n(values, x.size(), x.begin());
  auto m = measure(tract, model, x);
  std::copy(m.f.begin(), m.f.end(), out);
  return m.valid && m.area >= .12;
}
