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

#ifndef __LARYNGEAL_POSTURE_H__
#define __LARYNGEAL_POSTURE_H__

// ****************************************************************************
/// Posture of the larynx as a function of the activation of the five intrinsic
/// laryngeal muscles: arytenoid translation and rotation (cricoarytenoid joint)
/// and cricoid translation and rotation (cricothyroid joint), with one modified
/// Kelvin model per muscle or tissue.
///
/// References:
/// Titze, Hunter (2007): A two-dimensional biomechanical model of vocal fold
///   posturing. JASA 121(4), 2254-2260.
/// Titze (2006): The myoelastic aerodynamic theory of phonation, chapters 2, 3.
/// Alzamendi et al. (2022): Triangular body-cover model of the vocal folds with
///   coordinated activation of the five intrinsic laryngeal muscles. JASA 151.
///
/// All quantities are in SI units and refer to the adult male larynx of these
/// papers (vocal fold length 16 mm). Other sizes are obtained by geometric
/// similarity in the glottis class: strains and stresses are kept, lengths are
/// scaled.
// ****************************************************************************

class LaryngealPosture
{
public:
  enum Tissue { LCA, IA, PCA, CT, TA, LIGAMENT, MUCOSA, NUM_TISSUES };
  static const int NUM_MUSCLES = 5;
  static const double REFERENCE_LENGTH_M;

  LaryngealPosture();
  void reset();
  /// Advances the posture by one time step.
  void step(double dt_s, const double activation[NUM_MUSCLES]);
  /// Brings the posture to the equilibrium for the given activations.
  void settle(const double activation[NUM_MUSCLES]);

  /// Longitudinal strain of the vocal fold.
  double getStrain() const;
  /// Lateral distance of the vocal process from the midline.
  double getVocalProcessX() const;
  double getVocalProcessY() const;
  double getArytenoidAngle() const { return theta; }
  /// Area of the cartilaginous (posterior) glottal opening.
  double getPosteriorArea() const { return getPosteriorArea(getStrain()); }
  /// The same for another strain of the folds (other CT activity).
  double getPosteriorArea(double strain) const;
  double getStress(Tissue t) const { return stress[t]; }
  /// Stress of a tissue held at the given strain.
  static double getStaticStress(Tissue t, double strain, double activation);

private:
  double getAdductoryElongation() const;

  // Arytenoid displacement (xi, psi), rotation theta; cricoid translation zeta
  // and rotation omega; and their velocities.
  double xi, psi, theta, zeta, omega;
  double vXi, vPsi, vTheta, vZeta, vOmega;
  double stress[NUM_TISSUES];
  double activeStress[NUM_TISSUES];
  double prevStrain[NUM_TISSUES];
};

#endif
