// Refit only the tongue-tip tier of an otherwise fixed /a4a/ score.
#include "GesturalScore.h"
#include "GeometricGlottis2019.h"
int main(int argc,char **argv) {
  if (argc!=4) return 1;
  static VocalTract tract;
  tract.readFromXml(argv[1]);
  static GeometricGlottis2019 glottis;
  GesturalScore score(&tract,&glottis);
  bool inRange;
  if (!score.loadGesturesXml(argv[2],inRange) || !inRange) return 2;
  score.addClosingGesture(GesturalScore::TONGUE_TIP_GESTURE,"tt-alveolar-closure",
                          0.295,0.305,0.008,0.008,false);
  return score.saveGesturesXml(argv[3]) ? 0 : 3;
}
