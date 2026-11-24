# make -j8 : builds build/glottis_probe (not committed)
B = ../../backend
SRC = $(filter-out $(B)/SoundLib.cpp $(B)/VocalTractLabApi.cpp,$(wildcard $(B)/*.cpp))
OBJ = $(patsubst $(B)/%.cpp,build/%.o,$(SRC))
CXXFLAGS = -std=c++14 -O2 -w -I$(B)
build/glottis_probe: glottis_probe.cpp $(OBJ)
	$(CXX) $(CXXFLAGS) $^ -o $@
build/%.o: $(B)/%.cpp $(wildcard $(B)/*.h)
	@mkdir -p build
	$(CXX) $(CXXFLAGS) -c $< -o $@
