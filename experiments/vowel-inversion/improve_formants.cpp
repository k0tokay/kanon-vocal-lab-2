// Headless vowel experiment using the GUI's step sizes, area floor and native formant estimator.
// Build from the repository root: clang++ -std=c++14 -Ibackend -Wl,-rpath,build-mac/gui experiments/vowel-inversion/improve_formants.cpp build-mac/gui/libVocalTractLabApi.dylib -o build-mac/improve-formants
// Run: build-mac/improve-formants SPEAKER_FILE MIN_AREA_CM2 [VOWEL] (0.01 for recorded results).
#include "VocalTract.h"
#include "TlModel.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <iomanip>
#include <iostream>

using Shape = std::array<double, VocalTract::NUM_PARAMS>;
struct Measurement {
  std::array<double, 3> f{};
  double area = 1e6;
  bool valid = false;
};

Measurement measure(VocalTract &tract, TlModel &model, Shape x) {
  x[VocalTract::VO] = std::min(0.0, x[VocalTract::VO]);
  tract.setParams(x.data());
  tract.calculateAll();
  Measurement result;
  for (const auto &section : tract.tubeSection)
    result.area = std::min(result.area, section.area);
  tract.getTube(&model.tube);
  model.tube.resetGlottisSections(0.0);
  double bandwidth[3];
  int count;
  bool friction, closure, nasal;
  model.getFormants(result.f.data(), bandwidth, count, 3, friction, closure, nasal);
  result.valid = count == 3;
  return result;
}

double error(const Measurement &m, const Measurement &target) {
  if (!m.valid) return INFINITY;
  double sum = 0;
  for (int j = 0; j < 3; ++j) sum += std::pow(m.f[j]/target.f[j]-1, 2);
  return 100 * std::sqrt(sum/3);
}

int main(int argc, char **argv) {
  if (argc < 3 || argc > 5) return 1;
  const double minArea = std::stod(argv[2]);
  static VocalTract tract;
  tract.readFromXml(argv[1]);
  static TlModel model;
  Shape ref;
  auto &vowel = tract.shapes.at(tract.getShapeIndex(argc >= 4 ? argv[3] : "a"));
  std::copy_n(vowel.param, ref.size(), ref.begin());
  ref[VocalTract::VO] = std::min(0.0, ref[VocalTract::VO]);
  auto target = measure(tract, model, ref);
  if (!target.valid) return 2;
  // HX HY JX JA LP LD VS VO TCX TCY TTX TTY TBX TBY TRX TRY TS1 TS2 TS3.
  const Shape step = {.05/1.5,.05,.05,.05,.05,.05,.1,0,.05,.05,.05,.05,.05,.05,.05,.05,.05,.05,.05};
  std::cout << "start,steps,rms_percent,min_area_cm2,F1,F2,F3";
  for (auto &p : tract.params) std::cout << "," << p.abbr;
  std::cout << "\n" << std::setprecision(9);
  std::vector<std::string> seeds = {"reference","open-jaw","protruded-lips","raised-jaw"};
  if (argc == 5) seeds = {argv[4]};
  for (std::string seed : seeds) {
    Shape x = ref;
    if (seed == "open-jaw") x[VocalTract::JA] -= .8;
    if (seed == "raised-jaw") x[VocalTract::JA] += .85;
    if (seed == "protruded-lips") x[VocalTract::LP] += .35;
    if (seed == "wide-spread" || seed == "raised-rounded") {
      bool open = seed == "wide-spread";
      x[VocalTract::JA] += open ? -3.0 : 2.8;
      x[VocalTract::LP] += open ? -0.85 : 0.85;
      x[VocalTract::LD] += open ? 0.65 : 0.15;
    }
    if (seed.substr(0,5) == "from-") {
      auto &source = tract.shapes.at(tract.getShapeIndex(seed.substr(5)));
      std::copy_n(source.param, x.size(), x.begin());
      x[VocalTract::VO] = std::min(0.0, x[VocalTract::VO]);
    }
    for (int j = 0; j < VocalTract::NUM_PARAMS; ++j)
      x[j] = std::min(tract.params[j].max, std::max(tract.params[j].min, x[j]));
    auto m = measure(tract, model, x);
    if (m.area < minArea) { std::cerr << seed << " requires GUI area repair\n"; return 3; }
    std::array<int,VocalTract::NUM_PARAMS> moves{};
    int iterations = 0;
    while (iterations < 100 && seed != "reference") {
      double best = error(m,target);
      int selected = -1, direction = 0;
      for (int j = 0; j < VocalTract::NUM_PARAMS; ++j) {
        if (step[j] == 0) continue;
        for (int sign : {1,-1}) {
          if (std::abs(moves[j]+sign)>6) continue;
          Shape trial = x;
          trial[j] += sign*step[j];
          if (trial[j]<tract.params[j].min || trial[j]>tract.params[j].max) continue;
          auto measurement = measure(tract,model,trial);
          double e = error(measurement,target);
          if (measurement.area >= minArea && e < best) {
            best=e; selected=j; direction=sign;
          }
        }
      }
      if (selected<0) break;
      x[selected] += direction*step[selected];
      moves[selected] += direction;
      m = measure(tract,model,x);
      ++iterations;
    }
    std::cout << seed << "," << iterations << "," << error(m,target) << "," << m.area;
    for (double f : m.f) std::cout << "," << f;
    for (double v : x) std::cout << "," << v;
    std::cout << std::endl;
  }
}
