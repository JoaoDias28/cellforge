> Follow `AGENTS.md`. Create an ExecPlan when this task becomes eligible. Do not implement unrelated later tasks.

# TASK-034 — First real hardware adapters

## Goal
Integrate the selected physical robot, gripper, fixture I/O, camera, and laser after software qualification is complete.

## Prerequisites
- Task 033 is merged and its signed qualification evidence is valid;
- exact manufacturers/models, firmware, protocols, driver licenses, and maintenance status;
- documented independent safety architecture and approved commissioning controls.

## Deliverables
- production component packages and documented vendor-interface hardware adapters;
- generic contract-suite, calibration, bench, commissioning, and acceptance evidence;
- explicit uncertain-outcome handling for the process machine;
- deployment target profile tied to exact hardware and safety-review evidence.

## Acceptance
- every adapter passes bench tests on real equipment;
- physical tests run only under approved commissioning and independent safety controls;
- no component is production-qualified from simulation evidence;
- functional-safety verification remains independent and is recorded separately.
