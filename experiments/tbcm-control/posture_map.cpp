// Static posture of the TBCM of a speaker for given control parameters, without sound.
//   posture_map speaker.speaker < lines
// Each line: f0 pressure LCA IA PCA CT TA
// Output per line: strain, vocal process position (mm, < 0 = pressed), posterior
// opening (mm^2), natural F0 (Hz), and the open area at rest (mm^2, both edges'
// mean plus the posterior opening).
#include "VocalTractLabApi.cpp"
#include <cstdio>
#include <iostream>
#include <sstream>

int main(int argc, char **argv)
{
  if (argc < 2) { fprintf(stderr, "posture_map speaker < lines\n"); return 1; }
  if (vtlInitialize(argv[1]) != 0) { return 1; }
  if (selectedGlottis != BODY_COVER_GLOTTIS) { fprintf(stderr, "TBCM not selected\n"); return 1; }
  Glottis *g = glottises[selectedGlottis];
  string line;
  while (getline(cin, line))
  {
    istringstream is(line);
    double c[7];
    int n = 0;
    while (n < 7 && is >> c[n]) { n++; }
    if (n < 7) { continue; }
    for (int k = 0; k < 7; k++) { g->controlParams[k].x = c[k]; }
    g->resetMotion();
    g->calcGeometry();
    double vp = 10*g->derivedParams[BodyCoverGlottis::VOCAL_PROCESS_X].x;
    double len = 10*g->derivedParams[BodyCoverGlottis::CURRENT_LENGTH].x;
    double pgo = 100*g->derivedParams[BodyCoverGlottis::POSTERIOR_AREA].x;
    double open = pgo + (vp > 0 ? 0.5*vp*len : 0.0);    // triangle between the commissure and the processes
    printf("%.5f %.4f %.4f %.1f %.4f\n", g->derivedParams[BodyCoverGlottis::STRAIN].x, vp, pgo,
      g->derivedParams[BodyCoverGlottis::NATURAL_F0].x, open);
    fflush(stdout);
  }
  return 0;
}
