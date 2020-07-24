CXX      := -c++
CXXFLAGS := -Wall -Wextra -Werror
LDFLAGS  := -L/opt/local/lib -lstdc++ -lm
BUILD    := ./build
OBJ_DIR  := .
APP_DIR  := .
TARGET   := zmq_sub_client
INCLUDE  := -I/opt/local/include/
SRC      := $(wildcard *.cpp)

OBJECTS  := $(SRC:%.cpp=$(OBJ_DIR)/%.o)

all: $(APP_DIR)/$(TARGET)

$(OBJ_DIR)/%.o: %.cpp
	@mkdir -p $(@D)
	$(CXX) $(CXXFLAGS) $(INCLUDE) -c $< -o $@

$(APP_DIR)/$(TARGET): $(OBJECTS)
	@mkdir -p $(@D)
	$(CXX) $(CXXFLAGS) -o $(APP_DIR)/$(TARGET) $^ $(LDFLAGS)


.PHONY: all clean debug release

debug: CXXFLAGS += -DDEBUG -g
debug: all

release: CXXFLAGS += -O2
release: all

clean:
	-@rm -rvf $(OBJ_DIR)/*
	-@rm -rvf $(APP_DIR)/*
