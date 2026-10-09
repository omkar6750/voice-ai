# ADR-0051: Caller referrals are reviewed independently from Contacts

Status: Accepted

## Decision

The registered `save_referral` business tool captures caller-provided first/last name,
optional phone/email, organization, role and context in one operation. Ask for a name
and the best way to reach the person in one conversational question. If a phone or
email is supplied, read it back once and wait for confirmation before saving.
Incomplete referrals remain valid. Unknown details are never inferred.

Caller readback confirmation records transcription accuracy, not verified ownership
or outreach permission. Phone and email start unverified. Saving never calls or
messages the referral or creates a Contact. Admins review records and can explicitly
promote one with a verified international phone number to Contacts. Email-only
records remain reviewable. Existing contacts are linked by tenant and normalized
phone without overwriting their details.

Referrals are organization-owned. Nullable references to the original Contact,
source Run and promoted Contact use `ON DELETE SET NULL`; referral details survive
cleanup. Database triggers enforce matching organizations. Invocation IDs and hashes
make retries idempotent. The existing runtime broker records arguments, results,
timing and diagnostics for browser, modem, Twilio and text-test executions.

## Configuration

`POST /api/v1/referrals/tool` installs an idempotent, published tool definition for
the current organization. Bind it to the chosen agent nodes or shared tools using
the existing editor. Published agents are unchanged until explicitly configured
and republished. A short optional prompt instruction is:

“If they refer us to another person, ask once for their name and best contact method.
Accept phone, email, both or incomplete details. Read any supplied phone/email back
once and wait for confirmation, then call #save_referral with the known details.
Say it is saved only after the tool confirms success.”

The Referrals dashboard exposes read-only listing to Members and review, verification,
tool installation and promotion to Admins. Run tool evidence remains accessible from
the source conversation link.
