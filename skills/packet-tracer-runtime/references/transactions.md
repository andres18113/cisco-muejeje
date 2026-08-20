# Runtime transactions

Read this reference before an approved disposable mutation or any operation whose failure can leave a changed workspace.

Capture the relevant baseline and determine the compensating or cleanup path before dispatch. Apply the typed mutation, observe bounded convergence and independent read-back, then restore or clean up in the failure path as well as the success path. Verify the resulting state instead of treating an attempted restore as successful.

Use the current application result and runtime evidence models for exact state vocabulary. If restoration is unavailable, ambiguous, or fails, stop dependent work and report the residual state explicitly.
