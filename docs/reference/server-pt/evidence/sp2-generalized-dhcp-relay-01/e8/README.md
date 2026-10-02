# SP-2 mixed product, episode 8 (UNSEALED, incomplete)

Executed commit `ece5fca0cf9b997aed185b86367cd00fa6e9cd6c`, tree `2c760bd2b9e1727e149efc56eece0833c15f879f`; build `9.0.1.0858`, file channel, stage `SP2-MIXED-PRODUCT` profile v1. Attempt `ccc1b252c0751f2e26a053db26f32493`; campaign `SERVER-PT-SP2-GENERALIZED-DHCP-RELAY-01`.

**This archive is not a campaign seal.** The episode closed with cleanup `verified_clean`, but the attempt store has no `source-ref-product-record.json`: the executed CLI recognized only two older product measurement names and silently skipped the SP-2 product citation. The pointer was not fabricated afterwards and no consumed store, ledger or record was changed. `UNSEALED.json` names the missing reference, its cause and the hash of every original checked before copying.

Qualification `stopped`; primary failure `sp2_mixed_product_not_verified`; operations `492`. All eleven selected clients stayed in DHCP mode on APIPA/16 addresses with no gateway or resolver (`native_client_unassigned_in_window`), so no lease, pool attribution, serving, capacity or service result follows from this run. Final empty lease-table prefixes are raw observations, not universal absence or exhaustion.

Lead helper scripts are stored as `.py.txt` (see `archive-path-map.json`); `store/` is the campaign store copied as found, `record/` and `product/` hold the qualification and product records.
