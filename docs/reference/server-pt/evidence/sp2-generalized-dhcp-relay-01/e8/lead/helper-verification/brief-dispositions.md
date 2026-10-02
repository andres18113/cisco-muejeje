### Prospective helper gate closure (pending independent review/publication)

Risk remains L under the existing prospective preparation/seal design at
`docs/engineering/change-briefs/server-pt-sp2-generalized-dhcp-relay.md:1900`.
This correction changes only ignored prospective helper bytes. Maintained
runtime/source, e7 originals/archive and consumed campaign accounting are
unchanged. The candidate is ready for independent helper review, not SP2 phase
acceptance and not authorization to skip fresh native preflight.

The five handoff findings have causal offline fixes:

- **Launch opening binding:** every launch requires an exit-zero opening
  receipt with exact path/hash, verified store index and the indexed opening
  equal to the prepared campaign/episode/attempt/authorization/source/tree,
  limits, stage/profile/channel/build, instance, targets and selected clients.
  Validation precedes lifecycle claim and is repeated before Start-Process.
  Maker explicitly retains episode/campaign/authorization IDs in the plan.
- **Required seal evidence:** promised qualification/product paths must exist
  and match exact indexed path/size/hash pointers. Qualification binds run,
  authorization/attempt/profile/channel/build/source/tree and owned launch.
  Exactly one stage-specific PRODUCT and FINAL measurement is required.
  Product binds summary/run/deployment/source and prepared manifest/topology/
  configuration/catalog hashes. All checks precede archive-stage creation.
  A measurement that actually did not run and promised no product may preserve
  that absence; a ran measurement cannot omit its product record/summary.
- **Cleanup identity:** closing requires complete typed census with exact
  episode/attempt/stage and timestamp. Seal binds that census's exact hash and
  closing identity. Attributed actual exit uses the maintained exit predicate,
  indexed launch/capture bytes and exact source/PID/path/incarnation. Missing
  exit remains unattributed; dirty cleanup remains `process_exited_dirty` with
  `cleanup_clean=false`. It does not alter the clean source identity or promote
  the failed/inconclusive product to acceptance.
- **Final inventory:** the reusable publication verifier rejects nonregular,
  linked/escaping, malformed or duplicate paths and verifies a fresh exact file
  set and every SHA-256. Seal calls it before and after the move and compares
  both inventories and manifest digests. Added and mutated final files reject.
- **Executed helper snapshot:** all ten command entry points require the
  caller-pinned snapshot digest and exclusive `lead/tools` execution. The
  exact eleven-file set includes authority/maker/seal and every other executed
  helper. Preparation and later helpers rehash retained verification summary
  and all twenty artifacts. Helpers run with checkout-local Python `-B` so
  unreviewed cached code cannot enter the exclusive tool inventory. The seal
  preserves every helper/artifact byte; `.py` evidence paths become `.py.txt`
  with an explicit archive path map. The snapshot is never regenerated or
  self-accepted by an executing helper.

The first causal run on byte-preserved original helpers had seven failures and
one positive pass in 4.11 seconds. Missing receipt/pin reached lifecycle claim;
missing qualification/PRODUCT-FINAL, incomplete census plus truthy unverified
exit, and both post-move mutation/addition incorrectly sealed. The first fixed
run retained one positive failure: fixture `read_text()` had normalized CRLF
in capture_text, unlike the maintained producer's exact decoded bytes. The
fixture was corrected to `read_bytes().decode()`; the production byte predicate
was preserved. That run's log/XML remain intact. Eight core cases then passed.

Final bounded offline verification has 114 passes, zero failures/errors/skips,
in 39.28 seconds. It executes real helper statements with temporary files;
only external Git/OS/campaign boundaries are substituted. It includes foreign
opening/authorization/product/closing identities, required evidence and pointer
hashes, all helper entry points/pins, complete verification retention, actual
exit and dirty cleanup, pre/post-move corruption, and real mixed/capacity makers
on temporary empty ledgers. Ruff, format, syntax and all twelve Python CRLF
checks pass. The exact eleven executed helper hashes were frozen before this
run and match at termination. No maintained Python changed, so the existing
ECE source full-suite/CI baseline is retained; no new broad source or native
result is claimed.

Proof, complete original/updated helper bytes, full diff and exact hashes are
retained under `data/services/sp2-governed/helper-closure-20260930T2100Z/`.
The final census proves unchanged clean source `ece5fca`/tree `2c760bd`, empty
process/mailbox/lock, no e8 IDs/plan and closed ledger: 1,591 operations and
3,426.06543 seconds spent; 17,409 operations and 17,573.93457 seconds ordinary
remaining. E7 remains 166 exact files with manifest
`7336fd2bad09ef51a7c7f7ef503d3e946e950db05bc967d14d517d399fa16ffd`.

**Deferred publication:** insert this disposition into the existing SP2 brief
with later native archive/public integration publication, preserving the
executed native source identity. This pending source documentation step is
explicit; the current execution source remains clean. Independent review must
approve the exact helper snapshot before prospective preparation. Then retain
the reviewed snapshot in exclusive lead/tools, supply its externally pinned
digest and repeat exact-source CI/import/ledger/process/mailbox preflight.
The old partial e8 snapshot is still unqualified and has not been overwritten.
