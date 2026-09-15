# Measurement method

Compare the same owner-binding relation under a direct state root, an RLP block hash and a hypothetical SSZ summary. All three use the selected `cse_dce` compiler, real Keccak/SHA computations, canonical RLP/MPT checks, witness Booleanity and public-input binding. The VM ISA and proof constraints are unchanged.

This is a concise description of the published method. The authoritative plan recorded before collection is the [frozen contract](collection/plan-sources/owner_state/CONTRACT.md), whose 80-round section governs the selected batch. The [experiment record](collection/experiment.json) includes its hash and the full schedule.

## Collection

Use one instrumented native executable, fixed generated programs and inputs, eleven Rayon workers and AC power. Require three consecutive CPU-idle snapshots of at least 90% before collection. Run no concurrent local benchmark, build or figure work during measurement. Record power, power settings, load and thermal warnings before and after each proof; CPU temperature and frequency are unmeasured.

Run one fresh-process warmup per anchor, then **80 rounds containing all three anchors**: 240 measured proofs and three warmups. Seed `20260911` selects randomized Williams rows and their reversals. Thirteen complete six-round cycles balance positions and ordered predecessor pairs; two further rows finish the schedule. Record the entire order before proving.

Stop only on completion, failed correctness/environment checks or explicit interruption, never on a timing result. Preserve every observation and any failed attempt. Verify one saved proof per anchor in fresh processes without witness files after collection.

## Analysis

The primary metric is complete `prove()` time, including execution, witness construction and return cleanup. Report every measured sample and the median per anchor. Use arithmetic means for exclusive phase stacks so they sum to the mean outer time. Program loading/assembly and verification have separate timers; witness loading and serialization are outside the primary timer.

Pair observations by round. Report geometric mean ratios for RLP/direct, SSZ/direct and the secondary SSZ/RLP comparison, with two-sided 95% Student-t intervals on the 80 log ratios (79 degrees of freedom; critical value `1.9904502102301282`). These exploratory, unadjusted, within-batch intervals assume approximately independent, normally distributed round log ratios. They do not establish equivalence or estimate variation across machines or batches.

Show chronological drift. The post-collection diagnostic finds autocorrelation and changing paired overheads, so reported intervals are explicitly **nominal** and their coverage is not established. Retain the predeclared analysis and every measurement.

Attribute hashing by exact retained instruction counts. Standalone hash execution diagnostics cover actual input lengths and include input/output constraints. Do not infer additive hash proving costs by subtracting these timings from complete proofs.
