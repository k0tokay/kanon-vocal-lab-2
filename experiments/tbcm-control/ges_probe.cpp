// Synthesizes a gestural score like vtlGesturalScoreToAudio and logs the state
// of the glottis for every sample (float32, NCOL columns, row-major).
//   ges_probe speaker.speaker in.ges out.f32 [sK=value ...]
// sK=value sets static parameter K of the selected glottis.
// Columns: audio, glottal flow (cm^3/s), f0, pressure, LCA, IA, PCA, CT, TA,
// strain, vocal process x (cm), lower area, upper area, posterior area, contact area (cm^2),
// natural f0, measured f0 (Hz).
#include "VocalTractLabApi.cpp"
#include <cstdio>

int main(int argc, char **argv)
{
  if (argc < 4) { fprintf(stderr, "ges_probe speaker ges out.f32 [sK=v ...]\n"); return 1; }
  if (vtlInitialize(argv[1]) != 0) { return 1; }
  Glottis *g = glottises[selectedGlottis];
  for (int a = 4; a < argc; a++)
  {
    int k; double v;
    if (sscanf(argv[a], "s%d=%lf", &k, &v) == 2) { g->staticParams[k].x = v; }
  }
  GesturalScore *score = new GesturalScore(vocalTract, g);
  bool inRange = true;
  if (!score->loadGesturesXml(string(argv[2]), inRange)) { fprintf(stderr, "cannot read ges\n"); return 2; }
  score->calcCurves();

  const int N = Synthesizer::NUM_CHUNCK_SAMPLES;
  int numFrames = score->getDuration_pt() / N + 2;
  int np = (int)g->controlParams.size();
  vector<double> tp(VocalTract::NUM_PARAMS), gp(Glottis::MAX_CONTROL_PARAMS), prevG(Glottis::MAX_CONTROL_PARAMS), cur(Glottis::MAX_CONTROL_PARAMS);
  Synthesizer syn;
  syn.init(g, vocalTract, tdsModel);
  g->resetMotion();
  Tube prevTube, newTube, tube;
  FILE *f = fopen(argv[3], "wb");
  const int NCOL = 17;
  float row[NCOL];
  for (int i = 0; i < numFrames; i++)
  {
    double pos = (double)i*N / AUDIO_SAMPLING_RATE_HZ;
    score->getParams(pos, tp.data(), gp.data());
    for (int k = 0; k < VocalTract::NUM_PARAMS; k++) { vocalTract->params[k].x = tp[k]; }
    vocalTract->calculateAll();
    vocalTract->getTube(&newTube);
    if (i == 0) { prevTube = newTube; prevG = gp; continue; }
    for (int s = 0; s < N; s++)
    {
      double r = (double)s / N;
      tube.interpolate(&prevTube, &newTube, r);
      for (int k = 0; k < np; k++) { cur[k] = (1 - r)*prevG[k] + r*gp[k]; }
      double out = syn.addSample(cur.data(), &tube, NULL);
      double in, outflow;
      tdsModel->getSectionFlow(Tube::UPPER_GLOTTIS_SECTION, in, outflow);
      row[0] = (float)out; row[1] = (float)in;
      for (int k = 0; k < 7; k++) { row[2 + k] = (float)g->controlParams[k].x; }
      const int D[8] = { 3, 7, 8, 9, 10, 11, 12, 13 };
      for (int k = 0; k < 8; k++) { row[9 + k] = (float)g->derivedParams[D[k]].x; }
      fwrite(row, sizeof(float), NCOL, f);
    }
    prevTube = newTube; prevG = gp;
  }
  fclose(f);
  return 0;
}
