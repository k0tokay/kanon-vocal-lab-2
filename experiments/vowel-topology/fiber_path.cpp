// Read two parameter vectors from stdin. Write validated path samples as CSV.
#include "../vowel-inversion/vowel_measurement.h"

int main(int argc, char **argv) {
  if (argc != 3) return 1;
  static VocalTract tract;
  static TlModel model;
  tract.readFromXml(argv[1]);
  Shape start, end;
  for (Shape *x : {&start, &end})
    for (double &v : *x) if (!(std::cin >> v)) return 2;
  const auto target = measure(tract, model, start);
  if (!target.valid) return 3;
  auto error = [&](const Measurement &m) {
    double e = 0;
    if (!m.valid || m.area < .12) return HUGE_VAL;
    for (int j = 0; j < 3; ++j)
      e = std::max(e, std::abs(std::log(m.f[j]/target.f[j])));
    return e;
  };
  std::array<Shape, 17> knots;
  for (int i = 0; i <= 16; ++i) {
    Shape &x = knots[i];
    for (int j = 0; j < int(x.size()); ++j)
      x[j] = start[j] + (end[j]-start[j])*i/16.;
    if (i == 0 || i == 16 || std::string(argv[2]) == "straight") continue;
    double best = error(measure(tract, model, x));
    for (double step : {.012, .004, .001}) {
      for (int pass = 0; pass < 4; ++pass) {
        Shape winner = x;
        for (int j : {VocalTract::JA, VocalTract::LP, VocalTract::LD,
                      VocalTract::TCX, VocalTract::TCY, VocalTract::TBY}) {
          const auto &p = tract.params[j];
          for (int sign : {-1,1}) {
            Shape trial = x;
            trial[j] += sign*step*(p.max-p.min);
            if (trial[j]<p.min || trial[j]>p.max) continue;
            double e = error(measure(tract, model, trial));
            if (e < best) { best=e; winner=trial; }
          }
        }
        if (winner == x) break;
        x = winner;
      }
    }
  }
  std::cout << "t,error_log,min_area_cm2,F1,F2,F3";
  for (auto &p : tract.params) std::cout << "," << p.abbr;
  std::cout << "\n" << std::setprecision(12);
  for (int i = 0; i <= 512; ++i) {
    int k = std::min(i/32,15);
    double t = (i-32*k)/32.;
    Shape x;
    for (int j = 0; j < int(x.size()); ++j)
      x[j] = knots[k][j]+t*(knots[k+1][j]-knots[k][j]);
    auto m = measure(tract, model, x);
    std::cout << i/512. << "," << error(m) << "," << m.area;
    for (double f : m.f) std::cout << "," << f;
    for (double v : x) std::cout << "," << v;
    std::cout << "\n";
  }
}
