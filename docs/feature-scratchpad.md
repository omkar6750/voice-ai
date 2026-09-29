# Feature scratchpad

Not implied by the initial implementation:

- OCR for scanned PDFs and controlled website ingestion.
- Additional email/channel adapters; no generic inbox yet.
- Workspace membership and Clerk authentication.
- Advanced graph authoring and richer waterfall interaction.
- Operator-reviewed provider/model capability refresh.
- Contact-local greeting and explicit timezone confirmation for callbacks.
- Media replacement UX when an imported provider ID expires without a source.

## Twilio follow-ups after the offline integration batch

- [ ] Real account: deployed HTTPS/WSS signatures, account permissions, consented
  calls, audible goodbye/clear behavior, REST release and callbacks.
- [ ] PostgreSQL: concurrent dispatch, callback/claim/finalizer races, duplicate
  sockets, active lease refresh/expiry and process-restart release reconciliation.
- [ ] Operator reconciliation of an uncertain create with no known provider SID;
  never reset the attempt fence or blindly redial.
- [ ] Revisit the retained Full-account policy using current account capability
  checks; trial free-unit advertising alone does not prove custom TwiML works.
- [ ] Review the pinned Pipecat input-stop Adapter on every SDK upgrade.

Implementation and offline evidence are in ADR-0023 and the runtime architecture
ledger. Mocked tests do not complete these checks. Usage/pricing, typed node
actions, SIM7600 release and integration with updated main remain in that ledger.
