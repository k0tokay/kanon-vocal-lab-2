# make : builds build/ges_probe and build/posture_map (not committed).
B = ../../backend
SRC = $(filter-out $(B)/SoundLib.cpp $(B)/VocalTractLabApi.cpp,$(wildcard $(B)/*.cpp))
OBJ = $(patsubst $(B)/%.cpp,build/obj/%.o,$(SRC))
CXXFLAGS = -std=c++14 -O2 -w -I$(B)
all: build/ges_probe build/posture_map
build/posture_map: posture_map.cpp $(OBJ) $(B)/VocalTractLabApi.cpp
	$(CXX) $(CXXFLAGS) posture_map.cpp $(OBJ) -o $@
build/ges_probe: ges_probe.cpp $(OBJ) $(B)/VocalTractLabApi.cpp
	$(CXX) $(CXXFLAGS) ges_probe.cpp $(OBJ) -o $@
build/obj/%.o: $(B)/%.cpp $(wildcard $(B)/*.h)
	@mkdir -p build/obj
	$(CXX) $(CXXFLAGS) -c $< -o $@
