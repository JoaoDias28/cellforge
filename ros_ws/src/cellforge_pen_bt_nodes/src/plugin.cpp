#include <behaviortree_cpp/bt_factory.h>

#include "cellforge_pen_bt_nodes/pen_nodes.hpp"

BT_REGISTER_NODES(factory) { cellforge_pen_bt_nodes::registerPenNodes(factory); }
