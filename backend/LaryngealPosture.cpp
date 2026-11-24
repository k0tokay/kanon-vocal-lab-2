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

#include "LaryngealPosture.h"
#include <cmath>
#include <algorithm>

const double LaryngealPosture::REFERENCE_LENGTH_M = 0.016;

namespace
{
  // Kelvin model parameters. The stress-strain values are those of Table IV in
  // Alzamendi et al. (2022); areas, fiber lengths, direction cosines, moment
  // arms and time constants are those of Titze and Hunter (2007) and Titze
  // (2006) as used with that model.
  struct TissueData
  {
    double length, area;              // m, m^2
    double alpha, beta, gamma;        // direction cosines and moment arm (m)
    double sigma0, sigma2, B;         // Pa, Pa, -
    double eps1, eps2;
    double sigmaM, epsM, b;           // maximum active stress and its shape
    double ts;                        // series time constant (s)
  };

  const TissueData TISSUE[LaryngealPosture::NUM_TISSUES] =
  {
    { 14.4e-3, 21.2e-6, -0.198,  0.886,  3.915e-3, 3.0e3, 59.0e3,  4.0, -0.5, -0.06, 100e3, 0.4, 2.37, 0.06 },  // LCA
    {  9.3e-3, 12.2e-6, -0.697, -0.644, -3.30e-3,  2.0e3, 30.0e3,  3.5, -0.5, -0.06, 100e3, 0.4, 1.25, 0.06 },  // IA
    { 15.0e-3, 34.4e-6, -0.100, -0.950, -5.49e-3,  5.0e3, 55.0e3,  5.3, -0.5, -0.05, 100e3, 0.4, 1.86, 0.06 },  // PCA
    { 13.8e-3, 73.8e-6,  0.0,    0.0,    0.0,      2.2e3,  5.0e3,  7.0, -0.5, -0.06, 300e3, 0.0, 2.40, 0.08 },  // CT
    { 16.0e-3, 40.9e-6,  0.015,  0.990,  0.8e-3,   2.0e3,  1.5e3,  6.5, -0.5, -0.05, 150e3, 0.2, 1.07, 0.06 },  // TA
    { 16.0e-3,  6.1e-6,  0.0,    0.0,    0.0,      2.0e3,  1.4e3, 13.0, -0.5, -0.30, 0.0,   0.0, 0.0,  0.08 },  // Ligament
    { 16.0e-3,  5.0e-6,  0.0,    0.0,    0.0,      1.0e3, 20.0e3,  4.4, -0.5, -0.30, 0.0,   0.0, 0.0,  0.06 }   // Mucosa
  };

  const double TP = 0.1;              // parallel time constant (s)
  const double TA_ACTIVATION = 0.01;  // activation time constant (s)

  // Cricoarytenoid joint
  const double M_AC = 1.4e-3, I_AC = 1.6e-6;
  const double X_CAJ = 10.1e-3, Y_CAJ = -10.1e-3, X0_BAR = 4.0e-3;
  const double K_X = 60.0, K_Y = 200.0, KAPPA = 0.005;
  const double T_CAJ = 0.02;
  // Contact of the two vocal processes at the midline. The value makes them
  // overlap by some 0.1 mm for strong adduction.
  const double K_CONTACT = 3000.0;

  // Cricothyroid joint
  const double M_CC = 1.0e-2, I_CC = 1.0e-5;
  const double R_TA = 16.1e-3, R_CT = 11.1e-3, COS_PHI = 0.76;
  const double K_T = 500.0, K_R = 0.05;
  const double T_CTJ = 0.04;

  // Posterior wall of the cartilaginous glottis
  const double X_P2 = 3.2e-3, Y_P = -2.5e-3;

  // Stiffening factor of a joint beyond its free range.
  double stiffening(double x, double quad, double limit, double quart)
  {
    double ax = fabs(x);
    double r = 1.0 + quad*x*x;
    if (ax > limit) { r += quart*pow(ax - limit, 4); }
    return r;
  }

  double passiveStress(const TissueData &d, double e)
  {
    if (e < d.eps1) { return 0.0; }
    double s = -(d.sigma0 / d.eps1)*(e - d.eps1);
    if (e > d.eps2) { s += d.sigma2*(exp(d.B*(e - d.eps2)) - 1.0 - d.B*(e - d.eps2)); }
    return s;
  }

  double tangentModulus(const TissueData &d, double e)
  {
    if (e < d.eps1) { return 0.0; }
    double E = -d.sigma0 / d.eps1;
    if (e > d.eps2) { E += d.B*d.sigma2*(exp(d.B*(e - d.eps2)) - 1.0); }
    return E;
  }
}


LaryngealPosture::LaryngealPosture()
{
  reset();
}


void LaryngealPosture::reset()
{
  xi = psi = theta = zeta = omega = 0.0;
  vXi = vPsi = vTheta = vZeta = vOmega = 0.0;
  for (int i = 0; i < NUM_TISSUES; i++)
  {
    stress[i] = passiveStress(TISSUE[i], 0.0);
    activeStress[i] = 0.0;
    prevStrain[i] = 0.0;
  }
}


void LaryngealPosture::step(double dt, const double activation[NUM_MUSCLES])
{
  int i;

  // ****************************************************************
  // Strain of the muscles and tissues.
  // ****************************************************************

  double strain[NUM_TISSUES];
  strain[TA] = strain[LIGAMENT] = strain[MUCOSA] = getStrain();
  // Cricothyroid: shortens when the cricoid rotates and slides back.
  strain[CT] = -(zeta / COS_PHI + R_CT*omega) / TISSUE[CT].length;
  // Muscles on the arytenoid: only the rotation counts (0.7: see README).
  for (i = LCA; i <= PCA; i++)
  {
    strain[i] = -0.7*TISSUE[i].gamma*theta / TISSUE[i].length;
  }

  // ****************************************************************
  // Stress in the muscles and tissues (implicit Euler).
  // ****************************************************************

  double force[NUM_TISSUES];
  for (i = 0; i < NUM_TISSUES; i++)
  {
    const TissueData &d = TISSUE[i];
    double target = 0.0;
    if (i < NUM_MUSCLES)
    {
      double q = strain[i] - d.epsM;
      double a = std::min(1.0, std::max(0.0, activation[i]));
      target = a*d.sigmaM*std::max(0.0, 1.0 - d.b*q*q);
    }
    activeStress[i] += (target - activeStress[i])*dt / (TA_ACTIVATION + dt);
    double rate = (strain[i] - prevStrain[i]) / dt;
    prevStrain[i] = strain[i];
    double rhs = activeStress[i] + passiveStress(d, strain[i]) + tangentModulus(d, strain[i])*TP*rate;
    stress[i] += (rhs - stress[i])*dt / (d.ts + dt);
    force[i] = d.area*stress[i];
  }

  // ****************************************************************
  // Cricoarytenoid joint.
  // ****************************************************************

  double fx = 0.0, fy = 0.0, torque = 0.0;
  for (i = 0; i < NUM_TISSUES; i++)
  {
    fx += TISSUE[i].alpha*force[i];
    fy += TISSUE[i].beta*force[i];
    torque += TISSUE[i].gamma*force[i];
  }

  double x02 = getVocalProcessX();
  if (x02 < 0.0)
  {
    double fc = -K_CONTACT*x02;
    fx += fc;
    torque += fc*((X_CAJ - X0_BAR)*sin(theta) + Y_CAJ*cos(theta));
  }

  fx -= K_X*stiffening(xi, 2e5, 3e-3, 2e13)*xi;
  fy -= K_Y*stiffening(psi, 2e5, 3e-3, 2e13)*psi;
  torque -= KAPPA*stiffening(theta, 10.0, 0.3, 1e4)*theta;

  // Semi-implicit Euler with implicit damping.
  vXi = (vXi + dt*fx / M_AC) / (1.0 + dt*K_X*T_CAJ / M_AC);
  vPsi = (vPsi + dt*fy / M_AC) / (1.0 + dt*K_Y*T_CAJ / M_AC);
  vTheta = (vTheta + dt*torque / I_AC) / (1.0 + dt*KAPPA*T_CAJ / I_AC);
  xi += dt*vXi;
  psi += dt*vPsi;
  theta += dt*vTheta;

  // ****************************************************************
  // Cricothyroid joint.
  // ****************************************************************

  double tension = force[TA] + force[LIGAMENT] + force[MUCOSA];
  double ft = COS_PHI*force[CT] - tension;
  double tr = R_CT*force[CT] - R_TA*tension;
  ft -= K_T*(1.0 + 30.0*fabs(omega) / 3.14159265)*stiffening(zeta, 1e6, 1.5e-3, 2e14)*zeta;
  tr -= K_R*(1.0 + 1500.0*fabs(zeta))*stiffening(omega, 40.0, 0.2, 2e5)*omega;
  vZeta = (vZeta + dt*ft / M_CC) / (1.0 + dt*K_T*T_CTJ / M_CC);
  vOmega = (vOmega + dt*tr / I_CC) / (1.0 + dt*K_R*T_CTJ / I_CC);
  zeta += dt*vZeta;
  omega += dt*vOmega;
}


void LaryngealPosture::settle(const double activation[NUM_MUSCLES])
{
  const double DT = 0.0002;
  for (int i = 0; i < 4000; i++) { step(DT, activation); }
  vXi = vPsi = vTheta = vZeta = vOmega = 0.0;
}


double LaryngealPosture::getAdductoryElongation() const
{
  return -(Y_CAJ*(1.0 - cos(theta)) - (X_CAJ - X0_BAR)*sin(theta) + psi);
}


double LaryngealPosture::getStrain() const
{
  return (getAdductoryElongation() + zeta + R_TA*omega) / REFERENCE_LENGTH_M;
}


double LaryngealPosture::getVocalProcessX() const
{
  return X_CAJ - (X_CAJ - X0_BAR)*cos(theta) + Y_CAJ*sin(theta) + xi;
}


double LaryngealPosture::getVocalProcessY() const
{
  return -getAdductoryElongation() - (zeta + R_TA*omega);
}


double LaryngealPosture::getPosteriorArea(double strain) const
{
  // Half-width of the posterior wall follows the medial arytenoid shift.
  double xp = std::max(0.0, X_P2 + xi);
  return std::max(0.0, (xp + getVocalProcessX())*(-strain*REFERENCE_LENGTH_M - Y_P));
}


double LaryngealPosture::getStaticStress(Tissue t, double strain, double activation)
{
  const TissueData &d = TISSUE[t];
  double q = strain - d.epsM;
  return activation*d.sigmaM*std::max(0.0, 1.0 - d.b*q*q) + passiveStress(d, strain);
}
