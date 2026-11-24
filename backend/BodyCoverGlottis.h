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

#ifndef __BODY_COVER_GLOTTIS_H__
#define __BODY_COVER_GLOTTIS_H__

#include "Glottis.h"
#include "LaryngealPosture.h"

// ****************************************************************************
/// Triangular body-cover model of the vocal folds (TBCM) controlled by the five
/// intrinsic laryngeal muscles. Self-oscillating: the fundamental frequency and
/// the voice quality follow from muscle activity, lung pressure and vocal tract.
///
/// References:
/// Story, Titze (1995): Voice simulation with a body-cover model of the vocal
///   folds. JASA 97(2).
/// Titze, Story (2002): Rules for controlling low-dimensional vocal fold models
///   with muscle activation. JASA 112(3).
/// Titze (2002): Regulating glottal airflow in phonation. JASA 111(1).
/// Galindo et al. (2017): Modeling the pathophysiology of phonotraumatic vocal
///   hyperfunction with a triangular glottal model. JSLHR 60(9).
/// Alzamendi et al. (2022): see LaryngealPosture.
// ****************************************************************************

class BodyCoverGlottis : public Glottis
{
public:
  enum ControlParamIndex
  {
    FREQUENCY,
    PRESSURE,
    ACT_LCA,
    ACT_IA,
    ACT_PCA,
    ACT_CT,
    ACT_TA,
    FLUTTER,
    NUM_CONTROL_PARAMS
  };

  enum StaticParamIndex
  {
    REST_LENGTH,
    REST_THICKNESS,
    MUCOSA_DEPTH,
    LIGAMENT_DEPTH,
    MUSCLE_DEPTH,
    COVER_SHEAR_MODULUS,
    BODY_SHEAR_MODULUS,
    CONVERGENCE,
    POSTERIOR_SCALE,
    EPILARYNX_AREA,
    INLET_LENGTH,
    POSTURE_SPEED,
    F0_CONTROL,
    MAX_STRAIN,
    ASPIRATION_STRENGTH,
    ASPIRATION_CUTOFF,
    BACKGROUND_NOISE_LEVEL,
    BACKGROUND_NOISE_CUTOFF,
    NUM_STATIC_PARAMS
  };

  enum DerivedParamIndex
  {
    DISP_LOWER,
    DISP_UPPER,
    DISP_BODY,
    STRAIN,
    CURRENT_LENGTH,
    THICKNESS_LOWER,
    THICKNESS_UPPER,
    VOCAL_PROCESS_X,
    AREA_LOWER,
    AREA_UPPER,
    POSTERIOR_AREA,
    CONTACT_AREA,
    NATURAL_F0,
    MEASURED_F0,
    NUM_DERIVED_PARAMS
  };

  BodyCoverGlottis();

  string getName();
  void resetMotion();
  void incTime(const double timeIncrement_s, const double pressure_dPa[]);
  void calcGeometry();
  void getTubeData(double *length_cm, double *area_cm2);
  int getApertureParamIndex();
  double getAspirationStrength_dB();
  double getAspirationCutoff_Hz();
  double getBackgroundNoiseLevel_dB();
  double getBackgroundNoiseCutoff_Hz();
  bool hasRapidClosure() { return true; }

private:
  /// Mechanical parameters of the three masses for the current posture (SI).
  struct Mechanics
  {
    double strain, length, thickness[2], depthCover, depthBody;
    double mass[3], k[3], kc;       // lower, upper, body
    double restX[2];                // adduction of lower and upper edge at the vocal process
    double posteriorArea;
  };

  /// State of one fold edge (lower or upper mass).
  struct Edge
  {
    double alpha;          // fraction of the length in contact
    double area;           // open area of both sides
    double contactMean;    // mean displacement of the contacting part (<= 0)
    double contactHalf;    // half range of the displacement in that part
  };

  void getActivation(double activation[]);
  void updateMechanics(double dt_s, double lungPressure_Pa);
  void calcMechanics(const LaryngealPosture &p, double strain, double sMus, double sLig,
    double sMuc, double actTA, Mechanics &m) const;
  /// Lowest eigenfrequency of the three coupled masses.
  static double getNaturalF0(const Mechanics &m);
  static Edge getEdge(double displacement, double restX, double length);
  void calcPressures(const Edge edge[], double Ps, double Pe, double P[]) const;
  void measureF0(double dt);

  LaryngealPosture posture;
  Mechanics mech;
  double x[3], v[3];       // displacement from the rest position (m), velocity
  double time_s;
  bool started;
  int postureCounter;
  double lastActivation[LaryngealPosture::NUM_MUSCLES];
  double lastTarget_Hz;
  // F0 measurement and control
  double controlStrain;
  double meanX, meanAbs, prevX, lastCrossing_s, measuredF0, f0Correction;
};

#endif
