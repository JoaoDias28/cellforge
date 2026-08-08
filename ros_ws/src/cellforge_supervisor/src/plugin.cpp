#include <behaviortree_cpp/bt_factory.h>

#include "cellforge_supervisor/supervisor_nodes.hpp"

BT_REGISTER_NODES(factory) { cellforge_supervisor::registerSupervisorNodes(factory); }
