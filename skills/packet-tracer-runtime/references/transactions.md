# Runtime transactions

Mutation sequence:

typed action -> bounded convergence -> independent read-back -> behavior -> restore/cleanup.

Report CLEAN, DIRTY, RESTORED or RESTORE_FAILED. Build inverse operations before dispatching a disposable mutation and always attempt restore in finally.
