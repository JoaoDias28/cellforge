> Follow `AGENTS.md`. Create an ExecPlan when the task spans more than a focused change. Do not implement unrelated later tasks.

# TASK-023 — First real hardware adapters

## Goal
Integrate the selected physical robot, gripper, fixture I/O, camera, and laser.

## Prerequisite decision
Before implementation, record exact manufacturers/models, firmware, protocols, driver licenses, and independent safety architecture in an ExecPlan and component packages.

## Deliverables

- production component packages;
- hardware adapters using documented vendor interfaces;
- generic contract-suite results;
- calibration procedures;
- bench and commissioning evidence templates;
- explicit uncertain-outcome handling for the laser;
- deployment target profile.

## Acceptance

- each adapter passes bench tests on real equipment;
- physical motion/process tests are executed only under approved commissioning controls;
- independent safety verification is recorded separately;
- no component is promoted to production-qualified based only on simulation.
