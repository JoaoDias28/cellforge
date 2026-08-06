# Testing strategy

## 1. Test pyramid

### Pure unit tests

- schema models;
- validators;
- frame/port linking;
- compatibility resolver;
- recipe approval rules;
- bundle hashing;
- fault mapping;
- behavior-tree helper nodes.

### Contract tests

Run the same suite against every adapter implementation:

- readiness;
- valid command;
- invalid command;
- busy rejection;
- timeout;
- cancellation;
- communication loss;
- restart reconciliation;
- stable fault mapping.

### ROS integration tests

- action/service/topic contracts;
- lifecycle/startup order;
- behavior-tree execution;
- state aggregation;
- trace propagation;
- cancellation propagation.

### Scene and simulation tests

- USD loads without errors;
- component instance IDs match `cell.yaml`;
- required frames exist;
- collision geometry present;
- scenario outcomes;
- deterministic seed replay;
- bounded performance.

### Hardware-in-the-loop tests

- real protocol communication;
- I/O handshake;
- robot trajectory execution at commissioning settings;
- machine program selection;
- failure and restart behavior.

### Production acceptance

- cycle capability;
- process quality;
- traceability;
- fault recovery;
- operator workflow;
- independent safety validation evidence.

## 2. CI gates

Pull requests must run:

- formatting and static analysis;
- Python and C++ unit tests;
- schema validation for all examples;
- package/license scan;
- ROS build and tests in supported container;
- headless domain/compiler tests.

Isaac Sim tests may run on a dedicated GPU runner. PRs that affect scene/simulation behavior require that check before release even when normal contributors cannot run it locally.

## 3. Required reference scenarios

Pen engraving MVP:

1. nominal pass;
2. no pen;
3. pose outside limit;
4. fixture not seated;
5. laser not ready;
6. laser cycle timeout;
7. inspection text mismatch;
8. operator cancel before process starts;
9. communication loss after process start, outcome unknown;
10. unhealthy safety status prevents job acceptance.

## 4. Golden traces

For selected scenarios, store normalized expected event sequences. Exclude nondeterministic timestamps while preserving order, state, command IDs, result codes, and required evidence.

## 5. Performance budgets

Budgets are defined per cell and skill. The platform should detect regressions rather than impose one global cycle-time value.
