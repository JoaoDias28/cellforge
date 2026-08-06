# Continuous integration

`ci.yml` is the executable Task 001 workflow. It runs the locked Python 3.12 lint/type/test gate
and builds/tests the placeholder ROS 2 package on Ubuntu 24.04 with ROS 2 Jazzy.

Schema/example validation remains deliberately unwired until Task 003, and Isaac Sim remains out
of normal CI. Dependency/license/security gates and dedicated GPU simulation jobs belong to later
implementation tasks once those dependency surfaces exist.
