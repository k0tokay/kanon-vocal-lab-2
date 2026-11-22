#pragma once
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

inline Measurement measure(VocalTract &tract, TlModel &model, Shape x) {
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
