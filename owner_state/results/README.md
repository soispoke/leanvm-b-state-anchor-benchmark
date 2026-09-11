# Measurement and validation records

The selected timing collection is **[collect-20260911T071527362410Z](collect-20260911T071527362410Z/report.json)**: six fresh-process warmups and 48 measured proofs, eight per condition. Every measured sample is retained. The [evidence manifest](../evidence.json) selects the reports and records artifact hashes; the [full report](../README.md) explains the statement, pairing and limitations.

| Record | Role | Included in primary timing estimates? |
| --- | --- | --- |
| [generate-20260910T110951804563Z](generate-20260910T110951804563Z/report.json) | Generate baseline and optimized programs | No, generation only |
| [negative-20260910T111102894820Z](negative-20260910T111102894820Z/report.json) | 85 malformed-witness VM rejection checks | No, validation only |
| [collect-20260910T111335722920Z](collect-20260910T111335722920Z/report.json) | AC-to-battery transition during measured proof 1 | No, entire attempt excluded |
| [collect-20260910T111752157149Z](collect-20260910T111752157149Z/report.json) | AC-to-battery transition during measured proof 16 | No, entire attempt excluded |
| [collect-20260910T121326694990Z](collect-20260910T121326694990Z/report.json) | Stopped at the user's request after 20 completed measured proofs | No, entire attempt excluded |
| [collect-20260911T071527362410Z](collect-20260911T071527362410Z/report.json) | Complete restarted collection under recorded AC power | Yes, all 48 measured proofs |
| [verify-20260911T072735093299Z](verify-20260911T072735093299Z/report.json) | Six saved proofs verified in fresh processes without witness files | No, verification only |

Raw logs and reports from interrupted attempts remain unchanged. Their completed cryptographic checks do not make an interrupted timing batch eligible for the primary analysis. The selected batch starts with its own warmups and the same predeclared workload schedule.

The selected [200 standalone hash execution diagnostics](../diagnostics/20260911-final/report.json) use the same native executable as the complete proof collection. Earlier diagnostic batches under `../diagnostics/` and the smoke-proof log under `../screening/` are retained as exploratory records. Standalone hash times are not additive proof-construction costs.
