# Published collection record

This directory preserves the successful 15 September attempt's plan and orchestration records. Files were moved here without editing their contents; original paths inside the records refer to the layout at collection time.

- [experiment.json](experiment.json): executable/input identities, full schedule, source hashes and completed stages.
- [preflight.json](preflight.json): recorded load, power, memory and thermal-warning probes before collection.
- [Frozen analysis contract](plan-sources/owner_state/CONTRACT.md): the 80-round expansion was declared before collection.
- [orchestrate.py.txt](orchestrate.py.txt): the exact collector used, preserved as a source record.
- [collect.log](collect.log) and [verify.log](verify.log): orchestration transcripts; individual proof logs are in the selected results directory.

For a new batch, use `python -m owner_state.collect` as described in [reproduction](../../REPRODUCING.md). The frozen collector is evidence, not the current command to run.
