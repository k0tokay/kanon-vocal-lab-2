// Runs a sustained vowel with any glottis model and measures the voice source.
// Build: see Makefile. Each line on stdin is one condition:
//   duration_s  ctrl0 ctrl1 ... [| staticIndex=value ...]   ('p' pressure ramp of 20 ms)
// Output per line: F0, flow mean/min/max, CQ, MFDR, H1-H2, SPL-like level, posture values.
#include "BodyCoverGlottis.h"
#include "TriangularGlottis.h"
#include "GeometricGlottis2025.h"
#include "Synthesizer.h"
#include "VocalTract.h"
#include "TdsModel.h"
#include <cstdio>
#include <iostream>
#include <sstream>
#include <cmath>
#include <complex>
using namespace std;

static double harm(const vector<double>& y, double f)
{
  complex<double> s = 0; int n = (int)y.size();
  for (int i = 0; i < n; i++) { double w = 0.5 - 0.5*cos(2*M_PI*i/n); s += w*y[i]*polar(1.0, -2*M_PI*f*i/48000.0); }
  return 20*log10(abs(s) + 1e-12);
}

int main(int argc, char** argv)
{
  if (argc < 4) { fprintf(stderr, "probe speaker vowel model(bcg|tri|geo) [wavprefix]\n"); return 1; }
  VocalTract* vt = new VocalTract();
  try { vt->readFromXml(argv[1]); vt->calculateAll(); } catch (string s) { printf("%s\n", s.c_str()); return 1; }
  int si = vt->getShapeIndex(argv[2]);
  if (si < 0) { fprintf(stderr, "no shape\n"); return 1; }
  for (int i = 0; i < VocalTract::NUM_PARAMS; i++) { vt->params[i].x = vt->shapes[si].param[i]; }
  vt->calculateAll();
  Tube tube; vt->getTube(&tube);
  string line; int count = 0;
  while (getline(cin, line))
  {
    if (line.empty()) { continue; }
    Glottis* g; string m = argv[3];
    if (m == "bcg") { g = new BodyCoverGlottis(); } else if (m == "tri") { g = new TriangularGlottis(); } else { g = new GeometricGlottis2025(); }
    string a = line, b; size_t bar = line.find('|');
    if (bar != string::npos) { a = line.substr(0, bar); b = line.substr(bar + 1); }
    istringstream ia(a), ib(b); double dur; ia >> dur; vector<double> c; double q; while (ia >> q) { c.push_back(q); }
    string t; while (ib >> t) { int k; double val; if (sscanf(t.c_str(), "%d=%lf", &k, &val) == 2) { g->staticParams[k].x = val; } }
    while (c.size() < g->controlParams.size()) { c.push_back(g->controlParams[c.size()].neutral); }
    TdsModel tds; Synthesizer syn; syn.init(g, vt, &tds);
    for (size_t k = 0; k < c.size(); k++) { g->controlParams[k].x = c[k]; }
    g->resetMotion();
    int N = (int)(dur*48000); vector<double> U, P, A; bool bad = false;
    vector<double> p = c;
    for (int i = 0; i < N && !bad; i++)
    {
      p[1] = c[1]*min(1.0, i/960.0);
      double out = syn.addSample(p.data(), &tube);
      double flow, inflow;
      tds.getSectionFlow(Tube::UPPER_GLOTTIS_SECTION, inflow, flow);
      U.push_back(flow); P.push_back(out); A.push_back(g->derivedParams.size() > 8 ? g->derivedParams[8].x : 0);
      if (!isfinite(flow) || fabs(flow) > 1e5) { bad = true; }
    }
    double f0 = 0, r0 = 0;
    vector<double> u;
    if (!bad) { u.assign(U.end() - 9600, U.end()); double mean = 0; for (double z : u) { mean += z/u.size(); }
      double e = 0; for (int i = 0; i < 4800; i++) { e += (u[i]-mean)*(u[i]-mean); }
      if (sqrt(e/4800) > 1.0) {
        vector<double> nc(1000, 0.0); double best = 0;
        for (int l = 40; l < 900; l++) { double s = 0, e2 = 0; for (int i = 0; i < 4800; i++) { s += (u[i]-mean)*(u[i+l]-mean); e2 += (u[i+l]-mean)*(u[i+l]-mean); } nc[l] = s/sqrt(e*e2 + 1e-9); best = max(best, nc[l]); }
        for (int l = 41; l < 899; l++) { if (nc[l] > 0.93*best && nc[l] >= nc[l-1] && nc[l] >= nc[l+1]) { double d = (nc[l+1]-nc[l-1])/(2*(2*nc[l]-nc[l-1]-nc[l+1])+1e-12); f0 = 48000.0/(l+d); r0 = nc[l]; break; } } } }
    printf("%s :", line.c_str());
    if (bad) { printf(" DIVERGED"); }
    else if (f0 == 0 || r0 < 0.5) { double mean = 0; for (double z : u) { mean += z/u.size(); } printf(" NOVOICE U %.0f", mean); }
    else
    {
      int per = (int)(8000*f0/48000); int L = (int)lround(per*48000/f0); vector<double> w(u.end() - L, u.end());
      double mn = 1e9, mx = -1e9, mean = 0; for (double z : w) { mn = min(mn, z); mx = max(mx, z); mean += z/L; }
      double cq = 0, mfdr = 0; vector<double> du(L, 0.0);
      for (int i = 0; i < L; i++) { if (w[i] < mn + 0.1*(mx-mn)) { cq += 1.0/L; } if (i > 0) { du[i] = (w[i]-w[i-1])*48000; mfdr = max(mfdr, -du[i]); } }
      double rms = 0; for (int i = N - 9600; i < N; i++) { rms += P[i]*P[i]/9600; }
      printf(" F0 %.1f r %.2f Umean %.0f Umin %.0f Umax %.0f CQ %.2f MFDR %.0f H1H2 %.1f H1H2k %.1f lev %.1f", f0, r0, mean, mn, mx, cq, mfdr/1000, harm(du, f0)-harm(du, 2*f0), harm(du, f0)-harm(du, round(2000/f0)*f0), 10*log10(rms+1e-12));
    }
    if (m == "bcg") { printf(" eps %.3f vp %.3f mm pgo %.2f mm2 nf0 %.0f mf0 %.1f", g->derivedParams[BodyCoverGlottis::STRAIN].x, 10*g->derivedParams[BodyCoverGlottis::VOCAL_PROCESS_X].x, 100*g->derivedParams[BodyCoverGlottis::POSTERIOR_AREA].x, g->derivedParams[BodyCoverGlottis::NATURAL_F0].x, g->derivedParams[BodyCoverGlottis::MEASURED_F0].x); }
    printf("\n"); fflush(stdout);
    if (argc > 4) { char fn[512]; snprintf(fn, 512, "%s%02d.f64", argv[4], count); FILE* f = fopen(fn, "wb"); fwrite(P.data(), 8, P.size(), f); fclose(f); }
    count++; delete g;
  }
}
