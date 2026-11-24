// ****************************************************************************
// This file is part of VocalTractLab.
// Copyright (C) 2025, Peter Birkholz, Dresden, Germany
// www.vocaltractlab.de
//
// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program. If not, see <http://www.gnu.org/licenses/>.
//
// ****************************************************************************

#include "BodyCoverGlottis.h"
#include <cmath>
#include <algorithm>

namespace
{
  const double TISSUE_DENSITY = 1040.0;     // kg/m^3
  // The quantities of the body-cover model in Galindo et al. (2017) /
  // Story and Titze (1995).
  const double ETA = 1.0e6;                 // 1/m^2, cubic stiffening
  const double ETA_CONTACT = 5.0e6;
  const double CONTACT_STIFFNESS = 3.0;     // relative to the edge spring
  const double ZETA[3] = { 0.1, 0.6, 0.15 };// lower, upper, body
  const double ZETA_CONTACT = 1.0;
  // Minimal difference between posterior and anterior edge position. It keeps
  // contact growing gradually when the vocal processes touch.
  const double MIN_HALF_SPREAD = 1.0e-5;    // m
  const int NUM_SUBSTEPS = 4;
  const int POSTURE_INTERVAL = 8;           // samples
}

BodyCoverGlottis::BodyCoverGlottis()
{
  int i;

  Parameter cp[NUM_CONTROL_PARAMS] =
  {
    { "f0", "f0", "Hz", 1, "Hz", 40.0, 1000.0, 220.0, 0.0 },
    { "Subglottal pressure", "pressure", "dPa", 1.0, "dPa", 0.0, 30000.0, 8000.0, 0.0 },
    { "LCA activation", "act_lca", "", 100, "%", 0.0, 1.0, 0.6, 0.0 },
    { "IA activation", "act_ia", "", 100, "%", 0.0, 1.0, 0.6, 0.0 },
    { "PCA activation", "act_pca", "", 100, "%", 0.0, 1.0, 0.0, 0.0 },
    { "CT activation", "act_ct", "", 100, "%", 0.0, 1.0, 0.2, 0.0 },
    { "TA activation", "act_ta", "", 100, "%", 0.0, 1.0, 0.25, 0.0 },
    { "Flutter", "flutter", "%", 1, "%", 0.0, 100.0, 25.0, 0.0 }
  };

  Parameter sp[NUM_STATIC_PARAMS] =
  {
    { "Rest length", "rest_length", "cm", 10, "mm", 0.3, 2.0, 1.0, 0.0 },
    { "Rest thickness", "rest_thickness", "cm", 10, "mm", 0.05, 0.8, 0.2, 0.0 },
    { "Mucosa depth", "mucosa_depth", "cm", 10, "mm", 0.02, 0.4, 0.15, 0.0 },
    { "Ligament depth", "ligament_depth", "cm", 10, "mm", 0.02, 0.4, 0.15, 0.0 },
    { "Muscle depth", "muscle_depth", "cm", 10, "mm", 0.05, 0.8, 0.3, 0.0 },
    { "Cover shear modulus", "cover_shear_modulus", "dPa", 0.1, "Pa", 500.0, 50000.0, 3000.0, 0.0 },
    { "Body shear modulus", "body_shear_modulus", "dPa", 0.1, "Pa", 500.0, 100000.0, 6000.0, 0.0 },
    { "Convergence", "convergence", "", 1, "", 0.0, 2.0, 0.0, 0.0 },
    { "Posterior opening scale", "posterior_scale", "", 1, "", 0.0, 2.0, 1.0, 0.0 },
    { "Epilarynx area", "epilarynx_area", "cm^2", 100, "mm^2", 0.05, 5.0, 0.5, 0.0 },
    { "Inlet length", "inlet_length", "cm", 10, "mm", 0.0, 0.5, 0.06, 0.0 },
    { "Posture speed", "posture_speed", "", 1, "", 0.2, 20.0, 1.0, 0.0 },
    { "F0 control", "f0_control", "", 1, "", 0.0, 1.0, 1.0, 0.0 },
    { "Maximal strain", "max_strain", "", 100, "%", 0.0, 0.6, 0.3, 0.0 },
    { "Aspiration strength", "aspiration_strength", "dB", 1, "dB", -60.0, 0.0, -40.0, 0.0 },
    { "Aspiration cutoff", "aspiration_cutoff", "Hz", 1, "Hz", 300.0, 8000.0, 1000.0, 0.0 }
  };

  Parameter dp[NUM_DERIVED_PARAMS] =
  {
    { "Lower displacement", "lower_disp", "cm", 10, "mm", -0.5, 0.5, 0.0, 0.0 },
    { "Upper displacement", "upper_disp", "cm", 10, "mm", -0.5, 0.5, 0.0, 0.0 },
    { "Body displacement", "body_disp", "cm", 10, "mm", -0.5, 0.5, 0.0, 0.0 },
    { "Strain", "strain", "", 100, "%", -0.5, 0.5, 0.0, 0.0 },
    { "Cord length", "cord_length", "cm", 10, "mm", 0.0, 3.0, 0.0, 0.0 },
    { "Lower thickness", "lower_thickness", "cm", 10, "mm", 0.0, 2.0, 0.0, 0.0 },
    { "Upper thickness", "upper_thickness", "cm", 10, "mm", 0.0, 2.0, 0.0, 0.0 },
    { "Vocal process position", "vocal_process_x", "cm", 10, "mm", -1.0, 1.0, 0.0, 0.0 },
    { "Lower area", "lower_area", "cm^2", 100, "mm^2", 0.0, 4.0, 0.0, 0.0 },
    { "Upper area", "upper_area", "cm^2", 100, "mm^2", 0.0, 4.0, 0.0, 0.0 },
    { "Posterior area", "posterior_area", "cm^2", 100, "mm^2", 0.0, 4.0, 0.0, 0.0 },
    { "Contact area", "contact_area", "cm^2", 100, "mm^2", 0.0, 2.0, 0.0, 0.0 },
    { "Natural f0", "natural_f0", "Hz", 1, "Hz", 0.0, 2000.0, 0.0, 0.0 },
    { "Measured f0", "measured_f0", "Hz", 1, "Hz", 0.0, 2000.0, 0.0, 0.0 }
  };

  for (i = 0; i < NUM_CONTROL_PARAMS; i++) { cp[i].x = cp[i].neutral; controlParams.push_back(cp[i]); }
  for (i = 0; i < NUM_STATIC_PARAMS; i++)  { sp[i].x = sp[i].neutral; staticParams.push_back(sp[i]); }
  for (i = 0; i < NUM_DERIVED_PARAMS; i++) { derivedParams.push_back(dp[i]); }

  Shape s;
  s.name = "default";
  for (i = 0; i < NUM_CONTROL_PARAMS; i++) { s.controlParam.push_back(controlParams[i].neutral); }
  shapes.push_back(s);

  resetMotion();
  calcGeometry();
}


string BodyCoverGlottis::getName()
{
  return string("Triangular body-cover glottis");
}


void BodyCoverGlottis::resetMotion()
{
  for (int i = 0; i < 3; i++) { x[i] = v[i] = 0.0; }
  for (int i = 0; i < LaryngealPosture::NUM_MUSCLES; i++) { lastActivation[i] = -1.0; }
  lastTarget_Hz = -1.0;
  controlStrain = 0.0;
  time_s = 0.0;
  started = false;
  postureCounter = 0;
  meanX = meanAbs = prevX = 0.0;
  lastCrossing_s = -1.0;
  measuredF0 = 0.0;
  f0Correction = 0.0;
}


void BodyCoverGlottis::getActivation(double activation[])
{
  activation[LaryngealPosture::LCA] = controlParams[ACT_LCA].x;
  activation[LaryngealPosture::IA]  = controlParams[ACT_IA].x;
  activation[LaryngealPosture::PCA] = controlParams[ACT_PCA].x;
  activation[LaryngealPosture::CT]  = controlParams[ACT_CT].x;
  activation[LaryngealPosture::TA]  = controlParams[ACT_TA].x;
}


// ****************************************************************************
/// Rules of Titze and Story (2002) with the stresses and the strain of the
/// posture model instead of the original static rules.
// ****************************************************************************

void BodyCoverGlottis::calcMechanics(const LaryngealPosture &p, double e, double sMus, double sLig,
  double sMuc, double actTA, Mechanics &m) const
{
  const double L0 = 0.01*staticParams[REST_LENGTH].x;
  const double T0 = 0.01*staticParams[REST_THICKNESS].x;
  const double Dmuc = 0.01*staticParams[MUCOSA_DEPTH].x;
  const double Dlig = 0.01*staticParams[LIGAMENT_DEPTH].x;
  const double Dmus = 0.01*staticParams[MUSCLE_DEPTH].x;
  const double muC = 0.1*staticParams[COVER_SHEAR_MODULUS].x;
  const double muB = 0.1*staticParams[BODY_SHEAR_MODULUS].x;
  const double scale = L0 / LaryngealPosture::REFERENCE_LENGTH_M;
  const double PI2 = M_PI*M_PI;

  double L = L0*(1.0 + e);
  double T = T0 / (1.0 + 0.8*e);
  double z = (1.0 + actTA) / 3.0;            // relative height of the node
  double Db = (actTA*Dmus + 0.5*Dlig) / (1.0 + 0.2*e);
  double Dc = (Dmuc + 0.5*Dlig) / (1.0 + 0.2*e);

  double sBody = (0.5*sLig*Dlig + sMus*Dmus) / Db;
  double sCover = (0.5*sLig*Dlig + sMuc*Dmuc) / Dc;

  double shear = 2.0*muC*L*T / Dc;
  double string = PI2*sCover*Dc*T / L;

  m.strain = e;
  m.length = L;
  m.depthCover = Dc;
  m.depthBody = Db;
  m.thickness[0] = z*T;
  m.thickness[1] = (1.0 - z)*T;
  m.k[0] = (shear + string)*z;
  m.k[1] = (shear + string)*(1.0 - z);
  m.k[2] = 2.0*muB*L*T / Db + PI2*sBody*Db*T / L;
  m.kc = std::max(0.0, (0.5*muC*L*Dc / T / (1.0 / 3.0 - z*(1.0 - z)) - shear)*z*(1.0 - z));
  m.mass[0] = TISSUE_DENSITY*L*T*Dc*z;
  m.mass[1] = TISSUE_DENSITY*L*T*Dc*(1.0 - z);
  m.mass[2] = TISSUE_DENSITY*L*T*Db;

  double x02 = scale*p.getVocalProcessX();
  double xc = staticParams[CONVERGENCE].x*T*(0.05 - 0.15*actTA);
  m.restX[0] = x02 + xc;
  m.restX[1] = x02;
  m.posteriorArea = staticParams[POSTERIOR_SCALE].x*scale*scale*p.getPosteriorArea(e);
}


// ****************************************************************************
/// Mechanical parameters for the current posture. With the F0 control, the
/// strain (that is, the activity of CT) is chosen so that the folds vibrate
/// with the F0 given as control parameter; all else follows from the muscles.
// ****************************************************************************

void BodyCoverGlottis::updateMechanics(double dt, double lungPressure_Pa)
{
  double ta = controlParams[ACT_TA].x;

  if (staticParams[F0_CONTROL].x < 0.5)
  {
    calcMechanics(posture, posture.getStrain(), posture.getStress(LaryngealPosture::TA),
      posture.getStress(LaryngealPosture::LIGAMENT), posture.getStress(LaryngealPosture::MUCOSA), ta, mech);
    return;
  }

  // Flutter according to Klatt and Klatt (1990); see the other glottis models.
  double f0 = controlParams[FREQUENCY].x;
  f0 += (controlParams[FLUTTER].x / 100.0)*(f0 / 100.0)*(sin(2.0*M_PI*12.7*time_s) +
    sin(2.0*M_PI*7.1*time_s) + sin(2.0*M_PI*4.7*time_s));

  // The vibration is faster than the small-signal eigenfrequency, the more so
  // the higher the pressure. Coefficients fitted for a length of 10 mm.
  double ratio = 0.01 / (0.01*staticParams[REST_LENGTH].x);
  double f = f0*exp(f0Correction);
  double f2 = f*f - 35.0*ratio*ratio*std::max(0.0, lungPressure_Pa - 450.0);
  double target = sqrt(std::max(f2, 0.25*f*f));

  double lo = -0.42, hi = staticParams[MAX_STRAIN].x;
  for (int i = 0; i < 12; i++)
  {
    double e = 0.5*(lo + hi);
    Mechanics m;
    calcMechanics(posture, e, LaryngealPosture::getStaticStress(LaryngealPosture::TA, e, ta),
      LaryngealPosture::getStaticStress(LaryngealPosture::LIGAMENT, e, 0.0),
      LaryngealPosture::getStaticStress(LaryngealPosture::MUCOSA, e, 0.0), ta, m);
    if (getNaturalF0(m) < target) { lo = e; } else { hi = e; }
  }
  double e = 0.5*(lo + hi);
  const double TAU = 0.004;
  controlStrain = (dt > 0.0) ? controlStrain + (e - controlStrain)*dt / (TAU + dt) : e;
  e = controlStrain;
  calcMechanics(posture, e, LaryngealPosture::getStaticStress(LaryngealPosture::TA, e, ta),
    LaryngealPosture::getStaticStress(LaryngealPosture::LIGAMENT, e, 0.0),
    LaryngealPosture::getStaticStress(LaryngealPosture::MUCOSA, e, 0.0), ta, mech);
}


double BodyCoverGlottis::getNaturalF0(const Mechanics &m)
{
  // Symmetric 3x3 matrix M^-1/2 K M^-1/2, smallest eigenvalue in closed form.
  double a = (m.k[0] + m.kc) / m.mass[0];
  double b = (m.k[1] + m.kc) / m.mass[1];
  double c = (m.k[0] + m.k[1] + m.k[2]) / m.mass[2];
  double d = -m.kc / sqrt(m.mass[0]*m.mass[1]);
  double e = -m.k[1] / sqrt(m.mass[1]*m.mass[2]);
  double f = -m.k[0] / sqrt(m.mass[0]*m.mass[2]);
  double q = (a + b + c) / 3.0;
  double p = sqrt(((a - q)*(a - q) + (b - q)*(b - q) + (c - q)*(c - q) + 2.0*(d*d + e*e + f*f)) / 6.0);
  if (p <= 0.0) { return sqrt(std::max(0.0, q)) / (2.0*M_PI); }
  double A = (a - q) / p, B = (b - q) / p, C = (c - q) / p, D = d / p, E = e / p, F = f / p;
  double r = 0.5*(A*(B*C - E*E) - D*(D*C - E*F) + F*(D*E - B*F));
  r = std::min(1.0, std::max(-1.0, r));
  double smallest = q + 2.0*p*cos(acos(r) / 3.0 + 2.0*M_PI / 3.0);
  return sqrt(std::max(0.0, smallest)) / (2.0*M_PI);
}


// ****************************************************************************
/// Triangular edge between the anterior commissure and the vocal process.
/// With the processes pressed together (restX < 0) the edges are parallel.
// ****************************************************************************

BodyCoverGlottis::Edge BodyCoverGlottis::getEdge(double displacement, double restX, double length)
{
  Edge e;
  double half = std::max(0.5*restX, MIN_HALF_SPREAD);
  double center = displacement + 0.5*restX;
  double lo = center - half, hi = center + half;   // anterior and posterior end
  double a = (lo >= 0.0) ? 0.0 : ((hi <= 0.0) ? 1.0 : -lo / (2.0*half));
  e.alpha = a;
  if (a >= 1.0)
  {
    e.area = 0.0;
    e.contactMean = center;
    e.contactHalf = half;
  }
  else
  {
    e.area = 2.0*length*(1.0 - a)*(a > 0.0 ? 0.5*hi : center);
    e.contactMean = (a > 0.0) ? 0.5*lo : 0.0;
    e.contactHalf = fabs(e.contactMean);
  }
  return e;
}


// ****************************************************************************
/// Mean pressures on the faces of the lower and the upper mass, Titze (2002).
// ****************************************************************************

void BodyCoverGlottis::calcPressures(const Edge edge[], double Ps, double Pe, double P[]) const
{
  const double SEPARATION = 1.05;
  const double EPS = 1.0e-10;       // m^2
  double al = edge[0].area, au = edge[1].area;
  double Tl = mech.thickness[0], Tu = mech.thickness[1], T = Tl + Tu;

  if ((al <= EPS) && (au <= EPS)) { P[0] = P[1] = 0.0; return; }
  if (au <= EPS) { P[0] = Ps; P[1] = 0.0; return; }
  if (al <= EPS) { P[0] = 0.0; P[1] = Pe; return; }

  double Ae = 1.0e-4*staticParams[EPILARYNX_AREA].x;
  double ad = std::max(0.0, std::min(SEPARATION*al, au));
  double r = std::min(1.0, ad / Ae);
  double Pkd = (Ps - Pe) / (1.0 - 2.0*r*(1.0 - r));
  double an = al + Tl*(au - al) / T;

  if (al >= au)
  {
    P[0] = Ps - Pkd*au*au / (al*an);
    P[1] = Ps - Pkd*au / an;
  }
  else
  {
    double zd = std::min(T, std::max(0.0, (ad - al)*T / (au - al)));
    if (zd > Tl)
    {
      P[0] = Ps - Pkd*ad*ad / (al*an);
      P[1] = Ps - Pkd*(T - zd + (ad / an)*(zd - Tl)) / Tu;
    }
    else
    {
      P[0] = Ps - Pkd*(Tl - zd + (ad / al)*zd) / Tl;
      P[1] = Ps - Pkd;
    }
  }
}


void BodyCoverGlottis::incTime(const double dt, const double pressure_dPa[])
{
  double Ps = 0.1*pressure_dPa[0];
  double Pe = 0.1*pressure_dPa[3];
  double activation[LaryngealPosture::NUM_MUSCLES];
  int i, n;

  if (!started)
  {
    calcGeometry();      // settles the posture
    started = true;
  }

  // ****************************************************************
  // Posture and mechanical parameters change slowly.
  // ****************************************************************

  if (postureCounter == 0)
  {
    getActivation(activation);
    double step = dt*POSTURE_INTERVAL*staticParams[POSTURE_SPEED].x;
    int num = std::max(1, (int)ceil(step / 0.0002));
    for (i = 0; i < num; i++) { posture.step(step / num, activation); }
    updateMechanics(dt*POSTURE_INTERVAL, 0.1*controlParams[PRESSURE].x);
  }
  postureCounter = (postureCounter + 1) % POSTURE_INTERVAL;

  // ****************************************************************
  // Motion of the three masses (semi-implicit Euler).
  // ****************************************************************

  double h = dt / NUM_SUBSTEPS;
  for (n = 0; n < NUM_SUBSTEPS; n++)
  {
    Edge edge[2];
    double P[2], f[3], d[3];
    for (i = 0; i < 2; i++) { edge[i] = getEdge(x[i], mech.restX[i], mech.length); }
    calcPressures(edge, Ps, Pe, P);

    f[2] = -mech.k[2]*x[2]*(1.0 + ETA*x[2]*x[2]);
    d[2] = 2.0*ZETA[2]*sqrt(mech.mass[2]*mech.k[2]);

    // Pressure on the inferior, sloped face of the lower mass, as in the
    // triangular glottis of VTL. It blows closed folds apart, for which the
    // pressures on the medial surface alone are not sufficient.
    double inlet = 0.25*0.01*staticParams[INLET_LENGTH].x*mech.length*(Ps + (edge[0].alpha < 1.0 ? P[0] : Ps));

    double coupling = mech.kc*(x[0] - x[1]);
    for (i = 0; i < 2; i++)
    {
      const Edge &e = edge[i];
      double q = x[i] - x[2];
      double elastic = -mech.k[i]*q*(1.0 + ETA*q*q);
      double m = e.contactMean;
      double contact = -CONTACT_STIFFNESS*mech.k[i]*e.alpha*
        (m + ETA_CONTACT*m*(m*m + e.contactHalf*e.contactHalf));
      double drive = P[i]*(1.0 - e.alpha)*mech.length*mech.thickness[i] + (i == 0 ? inlet : 0.0);
      f[i] = elastic + contact + drive + (i == 0 ? -coupling : coupling);
      f[2] -= elastic;
      d[i] = 2.0*(ZETA[i] + ZETA_CONTACT*e.alpha)*sqrt(mech.mass[i]*mech.k[i]);
    }

    // Damping is implicit, with the body velocity of the previous step.
    double vb = v[2];
    for (i = 0; i < 2; i++)
    {
      v[i] = (v[i] + h / mech.mass[i]*(f[i] + d[i]*vb)) / (1.0 + h*d[i] / mech.mass[i]);
    }
    double db = d[0] + d[1] + d[2];
    v[2] = (v[2] + h / mech.mass[2]*(f[2] + d[0]*v[0] + d[1]*v[1])) / (1.0 + h*db / mech.mass[2]);
    for (i = 0; i < 3; i++) { x[i] += h*v[i]; }
  }

  time_s += dt;
  measureF0(dt);
}


// ****************************************************************************
/// Period between two upward mean crossings of the lower mass.
// ****************************************************************************

void BodyCoverGlottis::measureF0(double dt)
{
  const double TAU = 0.02;
  meanX += (x[0] - meanX)*dt / TAU;
  double y = x[0] - meanX;
  meanAbs += (fabs(y) - meanAbs)*dt / TAU;
  if ((prevX < 0.0) && (y >= 0.0))
  {
    double t = time_s - dt*y / (y - prevX + 1e-30);
    if ((lastCrossing_s > 0.0) && (meanAbs > 2.0e-6))
    {
      double f = 1.0 / (t - lastCrossing_s);
      if ((f > 30.0) && (f < 2000.0))
      {
        measuredF0 = f;
        // Slow correction of the remaining error of the F0 prediction.
        double error = log(controlParams[FREQUENCY].x / f);
        if (fabs(error) < 0.45)
        {
          f0Correction += 0.12*error;
          f0Correction = std::min(0.5, std::max(-0.5, f0Correction));
        }
      }
    }
    lastCrossing_s = t;
  }
  prevX = y;
  if (time_s - lastCrossing_s > 0.05) { measuredF0 = 0.0; }
}


void BodyCoverGlottis::calcGeometry()
{
  int i;

  // Before the motion starts, the posture is in equilibrium.
  if (!started)
  {
    double a[LaryngealPosture::NUM_MUSCLES];
    bool changed = false;
    getActivation(a);
    for (i = 0; i < LaryngealPosture::NUM_MUSCLES; i++)
    {
      if (a[i] != lastActivation[i]) { changed = true; }
      lastActivation[i] = a[i];
    }
    if (changed)
    {
      posture.reset();
      posture.settle(a);
    }
    if (changed || (controlParams[FREQUENCY].x != lastTarget_Hz))
    {
      lastTarget_Hz = controlParams[FREQUENCY].x;
      updateMechanics(0.0, 0.1*controlParams[PRESSURE].x);
    }
  }

  Edge e[2];
  for (i = 0; i < 2; i++) { e[i] = getEdge(x[i], mech.restX[i], mech.length); }

  derivedParams[DISP_LOWER].x = 100.0*x[0];
  derivedParams[DISP_UPPER].x = 100.0*x[1];
  derivedParams[DISP_BODY].x = 100.0*x[2];
  derivedParams[STRAIN].x = mech.strain;
  derivedParams[CURRENT_LENGTH].x = 100.0*mech.length;
  derivedParams[THICKNESS_LOWER].x = 100.0*mech.thickness[0];
  derivedParams[THICKNESS_UPPER].x = 100.0*mech.thickness[1];
  derivedParams[VOCAL_PROCESS_X].x = 100.0*mech.restX[1];
  derivedParams[POSTERIOR_AREA].x = 1.0e4*mech.posteriorArea;
  derivedParams[AREA_LOWER].x = 1.0e4*(e[0].area + mech.posteriorArea);
  derivedParams[AREA_UPPER].x = 1.0e4*(e[1].area + mech.posteriorArea);
  derivedParams[CONTACT_AREA].x = 1.0e4*mech.length*
    (e[0].alpha*mech.thickness[0] + e[1].alpha*mech.thickness[1]);
  derivedParams[NATURAL_F0].x = getNaturalF0(mech);
  derivedParams[MEASURED_F0].x = measuredF0;
}


void BodyCoverGlottis::getTubeData(double *length_cm, double *area_cm2)
{
  length_cm[0] = derivedParams[THICKNESS_LOWER].x;
  length_cm[1] = derivedParams[THICKNESS_UPPER].x;
  area_cm2[0] = derivedParams[AREA_LOWER].x;
  area_cm2[1] = derivedParams[AREA_UPPER].x;
}


int BodyCoverGlottis::getApertureParamIndex()
{
  return ACT_PCA;
}


double BodyCoverGlottis::getAspirationStrength_dB()
{
  return staticParams[ASPIRATION_STRENGTH].x;
}


double BodyCoverGlottis::getAspirationCutoff_Hz()
{
  return staticParams[ASPIRATION_CUTOFF].x;
}
