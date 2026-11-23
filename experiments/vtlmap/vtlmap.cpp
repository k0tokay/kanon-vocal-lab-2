// Native primitives for maps out of VTL's anatomy and articulation spaces.
//
// Every function takes plain double arrays so that Python (ctypes) can build
// arbitrary composite maps on top: formants, area functions, anatomy changes
// and VTL's own articulation adaptation between anatomies.
//
// Build (repository root):
//   clang++ -shared -fPIC -std=c++14 -O2 -w -Ibackend experiments/vtlmap/vtlmap.cpp \
//     $(ls backend/*.cpp | grep -v SoundLib.cpp) -o build-mac/vtlmap.so

#include "AnatomyParams.h"
#include "TlModel.h"
#include "VocalTract.h"

#include <algorithm>
#include <cstring>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

namespace {

struct Handle {
  VocalTract tract;
  TlModel model;
  // Shapes and parameter ranges as read from the file; setFor() replaces the
  // tract's own with transformed reference shapes.
  std::vector<VocalTract::Shape> fileShapes;
  VocalTract::Param fileParams[VocalTract::NUM_PARAMS];
};

std::string lastError;

int fail(const std::string &message) {
  lastError = message;
  return -1;
}

AnatomyParams anatomyFrom(const double *theta) {
  AnatomyParams a;
  for (int i = 0; i < AnatomyParams::NUM_ANATOMY_PARAMS; i++)
    a.param[i].x = theta[i];
  return a;
}

}  // namespace

extern "C" {

const char *vm_last_error() { return lastError.c_str(); }
int vm_num_params() { return VocalTract::NUM_PARAMS; }
int vm_num_anatomy() { return AnatomyParams::NUM_ANATOMY_PARAMS; }

// Names are written as one space-separated string.
void vm_param_names(char *out, int size) {
  std::string s;
  static VocalTract t;  // too large for the stack
  for (int i = 0; i < VocalTract::NUM_PARAMS; i++)
    s += (i ? " " : "") + t.params[i].abbr;
  std::strncpy(out, s.c_str(), size);
}

void vm_anatomy_names(char *out, int size) {
  // The abbreviations are not unique ("W1 minus incisor width"), so use the
  // enum order with short names of our own.
  static const char *names =
      "lip_width mandible_height lower_molars_height upper_molars_height "
      "palate_height palate_depth hard_palate_length soft_palate_length "
      "pharynx_length larynx_length larynx_width vocal_fold_length "
      "oral_pharyngeal_angle";
  std::strncpy(out, names, size);
}

void vm_anatomy_bounds(double *low, double *high) {
  AnatomyParams a;
  for (int i = 0; i < AnatomyParams::NUM_ANATOMY_PARAMS; i++) {
    low[i] = a.param[i].min;
    high[i] = a.param[i].max;
  }
}

// Reference speaker for AnatomyParams (VTL's adult male template). An empty
// path keeps VTL's built-in default tract.
int vm_set_reference(const char *path) {
  if (!path || !*path) return 0;
  AnatomyParams a;
  return a.loadReferenceVocalTract(path) ? 0 : fail("cannot read reference");
}

// Anatomy parameters VTL's GUI computes from age and sex.
void vm_anatomy_from_age(int ageMonths, int male, double *theta) {
  AnatomyParams a;
  a.calcFromAge(ageMonths, male != 0);
  for (int i = 0; i < AnatomyParams::NUM_ANATOMY_PARAMS; i++)
    theta[i] = a.param[i].x;
}

// Clip to VTL's ranges and its pharynx constraint (AnatomyParams::restrictParams).
void vm_restrict_anatomy(double *theta) {
  AnatomyParams a = anatomyFrom(theta);
  a.restrictParams();
  for (int i = 0; i < AnatomyParams::NUM_ANATOMY_PARAMS; i++)
    theta[i] = a.param[i].x;
}

void *vm_open(const char *speaker) {
  auto *h = new Handle;
  try {
    h->tract.readFromXml(speaker);
  } catch (std::string &e) {
    lastError = e;
    delete h;
    return nullptr;
  }
  h->tract.calculateAll();
  h->fileShapes = h->tract.shapes;
  std::copy_n(h->tract.params, VocalTract::NUM_PARAMS, h->fileParams);
  return h;
}

void vm_close(void *p) { delete static_cast<Handle *>(p); }

void vm_get_anatomy(void *p, double *theta) {
  AnatomyParams a;
  a.getFrom(&static_cast<Handle *>(p)->tract);
  for (int i = 0; i < AnatomyParams::NUM_ANATOMY_PARAMS; i++)
    theta[i] = a.param[i].x;
}

// Rebuild the tract anatomy from the reference speaker (AnatomyParams::setFor).
// This also rescales the parameter ranges; the shape list keeps the file's.
void vm_set_anatomy(void *p, const double *theta) {
  auto *h = static_cast<Handle *>(p);
  AnatomyParams a = anatomyFrom(theta);
  a.setFor(&h->tract);
  h->tract.shapes = h->fileShapes;
}

// Current (possibly anatomy-scaled) parameter ranges and neutral values.
void vm_param_bounds(void *p, double *low, double *high, double *neutral) {
  auto *h = static_cast<Handle *>(p);
  for (int i = 0; i < VocalTract::NUM_PARAMS; i++) {
    low[i] = h->tract.params[i].min;
    high[i] = h->tract.params[i].max;
    if (neutral) neutral[i] = h->tract.params[i].neutral;
  }
}

int vm_get_shape(void *p, const char *name, double *x) {
  auto *h = static_cast<Handle *>(p);
  for (auto &s : h->fileShapes)
    if (s.name == name) {
      std::copy_n(s.param, VocalTract::NUM_PARAMS, x);
      return 0;
    }
  return fail(std::string("no shape ") + name);
}

// Replace or add a shape (used when writing a speaker file).
void vm_set_shape(void *p, const char *name, const double *x) {
  auto *h = static_cast<Handle *>(p);
  for (auto &s : h->fileShapes)
    if (s.name == name) {
      std::copy_n(x, VocalTract::NUM_PARAMS, s.param);
      h->tract.shapes = h->fileShapes;
      return;
    }
  VocalTract::Shape s;
  s.name = name;
  std::copy_n(x, VocalTract::NUM_PARAMS, s.param);
  h->fileShapes.push_back(s);
  h->tract.shapes = h->fileShapes;
}

int vm_num_shapes(void *p) { return (int)static_cast<Handle *>(p)->fileShapes.size(); }

void vm_shape_name(void *p, int i, char *out, int size) {
  std::strncpy(out, static_cast<Handle *>(p)->fileShapes[i].name.c_str(), size);
}

// VTL's articulation adaptation (AnatomyParams::adaptArticulation): from the
// reference speaker's coordinates to those of anatomy theta.
void vm_adapt(const double *theta, const double *reference, double *x) {
  AnatomyParams a = anatomyFrom(theta);
  double in[VocalTract::NUM_PARAMS];
  std::copy_n(reference, VocalTract::NUM_PARAMS, in);
  a.adaptArticulation(in, x);
}

// Inverse of vm_adapt. Each x coordinate is a sign-preserving scaling, and
// each y coordinate is affine in the old y given the old x.
void vm_unadapt(const double *theta, const double *x, double *reference) {
  AnatomyParams a = anatomyFrom(theta);
  double probe[VocalTract::NUM_PARAMS], out0[VocalTract::NUM_PARAMS], out1[VocalTract::NUM_PARAMS];
  const int n = VocalTract::NUM_PARAMS;
  // Pass 1: all coordinates as if affine with no cross terms, which is exact
  // for every parameter except the y coordinates that depend on their x.
  std::fill_n(probe, n, 0.0);
  a.adaptArticulation(probe, out0);
  for (int i = 0; i < n; i++) {
    std::fill_n(probe, n, 0.0);
    probe[i] = (x[i] < out0[i]) ? -1.0 : 1.0;  // the x scaling depends on sign
    a.adaptArticulation(probe, out1);
    reference[i] = probe[i] * (x[i] - out0[i]) / (out1[i] - out0[i]);
  }
  // Pass 2: y coordinates given the recovered x coordinates.
  const int pairs[][2] = {{VocalTract::TCX, VocalTract::TCY},
                          {VocalTract::TTX, VocalTract::TTY},
                          {VocalTract::TBX, VocalTract::TBY},
                          {VocalTract::TRX, VocalTract::TRY}};
  for (auto &xy : pairs) {
    std::copy_n(reference, n, probe);
    probe[xy[1]] = 0.0;
    a.adaptArticulation(probe, out0);
    probe[xy[1]] = 1.0;
    a.adaptArticulation(probe, out1);
    reference[xy[1]] = (x[xy[1]] - out0[xy[1]]) / (out1[xy[1]] - out0[xy[1]]);
  }
}

// Formants of the static shape x (VO is clamped to <= 0, a closed nasal port).
// Returns the number of formants found; minArea gets the smallest area before
// VTL's tongue-side floor (contact test), area_after the smallest after it.
int vm_formants(void *p, const double *x, int n, double *freq, double *bw,
                double *minArea) {
  auto *h = static_cast<Handle *>(p);
  double params[VocalTract::NUM_PARAMS];
  std::copy_n(x, VocalTract::NUM_PARAMS, params);
  params[VocalTract::VO] = std::min(0.0, params[VocalTract::VO]);
  h->tract.setParams(params);
  h->tract.calculateAll();
  if (minArea) *minArea = h->tract.minAreaBeforeTongueSideFloor_cm2;
  h->tract.getTube(&h->model.tube);
  h->model.tube.resetGlottisSections(0.0);
  std::vector<double> f(n), b(n);
  int count = 0;
  bool friction, closure, nasal;
  h->model.getFormants(f.data(), b.data(), count, n, friction, closure, nasal);
  std::copy_n(f.data(), n, freq);
  if (bw) std::copy_n(b.data(), n, bw);
  return count;
}

// Like vm_formants, but on a finer spectrum (2^exponent points, at most
// 2^13) and with parabolic interpolation of the dB magnitude, so that the
// frequencies are smooth enough for finite differences. Peaks below
// -10 dB (VTL's threshold) and outside [fmin, fmax] are ignored. bw gets
// the peak level in dB instead of a bandwidth.
int vm_peaks(void *p, const double *x, int n, int exponent, double fmin, double fmax,
             double *freq, double *level, double *minArea) {
  auto *h = static_cast<Handle *>(p);
  double params[VocalTract::NUM_PARAMS];
  std::copy_n(x, VocalTract::NUM_PARAMS, params);
  params[VocalTract::VO] = std::min(0.0, params[VocalTract::VO]);
  h->tract.setParams(params);
  h->tract.calculateAll();
  if (minArea) *minArea = h->tract.minAreaBeforeTongueSideFloor_cm2;
  h->tract.getTube(&h->model.tube);
  h->model.tube.resetGlottisSections(0.0);
  exponent = std::max(9, std::min(13, exponent));
  const int length = 1 << exponent;
  ComplexSignal s;
  h->model.getSpectrum(TlModel::FLOW_SOURCE_TF, &s, length, Tube::FIRST_PHARYNX_SECTION);
  const double df = (double)AUDIO_SAMPLING_RATE_HZ / length;
  int lo = std::max(1, (int)(fmin / df)), hi = std::min(length / 2 - 2, (int)(fmax / df) + 1);
  auto db = [&](int i) { return 20.0 * std::log10(s.getMagnitude(i) + 1e-30); };
  int count = 0;
  for (int i = lo; i <= hi && count < n; i++) {
    double a0 = db(i - 1), a1 = db(i), a2 = db(i + 1);
    if (a1 >= a0 && a1 > a2 && a1 >= -10.0) {
      double den = a0 - 2 * a1 + a2;
      double d = den < 0 ? 0.5 * (a0 - a2) / den : 0.0;
      double fr = (i + d) * df;
      if (fr < fmin || fr > fmax) continue;
      freq[count] = fr;
      if (level) level[count] = a1 - 0.25 * (a0 - a2) * d;
      count++;
    }
  }
  for (int k = count; k < n; k++) {
    freq[k] = 0.0;
    if (level) level[k] = 0.0;
  }
  return count;
}

// Centre-line area function of the last evaluated shape: up to `size`
// sections of (position along the tract, area). Returns the section count.
int vm_area_function(void *p, const double *x, double *pos, double *area, int size) {
  auto *h = static_cast<Handle *>(p);
  double params[VocalTract::NUM_PARAMS];
  std::copy_n(x, VocalTract::NUM_PARAMS, params);
  params[VocalTract::VO] = std::min(0.0, params[VocalTract::VO]);
  h->tract.setParams(params);
  h->tract.calculateAll();
  int n = std::min(size, (int)VocalTract::NUM_TUBE_SECTIONS);
  for (int i = 0; i < n; i++) {
    pos[i] = h->tract.tubeSection[i].pos;
    area[i] = h->tract.tubeSection[i].area;
  }
  return n;
}

// The <vocal_tract_model> element with the current anatomy and shapes.
int vm_write_tract(void *p, const char *path) {
  auto *h = static_cast<Handle *>(p);
  std::ofstream os(path);
  if (!os) return fail("cannot write tract");
  h->tract.writeToXml(os, 2);
  return 0;
}

}  // extern "C"
