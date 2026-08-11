# Codex task index

Execute tasks in order unless dependencies indicate safe parallel work.

| Task | Purpose | Depends on |
|---|---|---|
| 001 | repository bootstrap and CI | none |
| 002 | domain models and schema loader | 001 |
| 003 | component/cell/recipe schemas and validation | 002 |
| 004 | CLI project scaffold and validation commands | 002, 003 |
| 005 | component registry and capability resolver | 002, 003 |
| 006 | cell compiler and deterministic bundle manifest | 004, 005 |
| 007 | ROS interface package | 001 |
| 008 | device and skill SDK | 007 |
| 009 | mock adapters | 008 |
| 010 | state aggregator and trace model | 007, 008 |
| 011 | BehaviorTree.CPP supervisor | 007, 008, 010 |
| 012 | job gateway and recipe freeze | 003, 007, 011 |
| 013 | pen behavior tree and headless scenarios | 009, 011, 012 |
| 014 | Isaac Sim extension shell | 004 |
| 015 | studio project/scene round trip | 014, 003 |
| 016 | component browser and placement | 005, 015 |
| 017 | connection authoring and validation UI | 005, 015, 016 |
| 018 | simulation bridge and scenario control | 009, 014, 015 |
| 019 | MoveIt/MTC motion service | 007, 008 |
| 020 | simulated pen manipulation | 013, 018, 019 |
| 021 | bundle install/activate/rollback agent | 006, 012 |
| 022 | operator API and local UI | 010, 012, 021 |
| 023 | execution contracts and trace identity | 007, 010, 012, 022 |
| 024 | canonical pen runtime on BehaviorTree.CPP | 011, 013, 019, 023 |
| 025 | integrated offline runtime bringup | 009, 010, 012, 021, 022, 024 |
| 026 | installable signed bundle assembly | 006, 021, 025 |
| 027 | genuine Isaac Sim L2 runtime integration | 018, 019, 020, 024, 025, 026 |
| 028 | Studio spatial configuration and calibration | 015, 016, 017, 023 |
| 029 | Studio task and recipe authoring | 024, 028 |
| 030 | Studio deployment and evidence workflow | 026, 027, 029 |
| 031 | platform registry and artifact services | 005, 006, 023 |
| 032 | platform approvals, evidence, and result sync | 010, 012, 021, 022, 026, 031 |
| 033 | complete software release qualification | 025, 026, 027, 028, 029, 030, 031, 032 |
| 034 | first real hardware adapters | selected hardware, independent safety architecture, 033 |

Tasks 007 and 002 may proceed in parallel after Task 001. Tasks 014 and 009 may proceed in parallel after their dependencies.

Tasks 028 and 031 may proceed in parallel after their listed dependencies. Task 034 is blocked until
Task 033 is merged and the exact hardware and independent safety architecture are recorded. CPU,
mock, or synthetic-event evidence cannot substitute for the required Isaac Sim 6 L2 qualification.
