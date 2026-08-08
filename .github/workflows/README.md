# Continuous integration

`ci.yml` runs the locked Python 3.12 lint/type/test and schema/example-validation gates, then
builds and tests the current ROS workspace on Ubuntu 24.04 with ROS 2 Jazzy.

Isaac Sim remains out of normal CI. Dependency/license/security gates and dedicated GPU simulation
jobs belong to later implementation tasks once those dependency surfaces exist.
