"""Twilio credential resolution, validation, and phone number synchronization."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client
from voice_runtime.telephony.twilio import TwilioCredentials

from voice_api.models import IntegrationConnection, IntegrationSecret
from voice_api.services.vault_service import CredentialVault, SecretScope, VaultError


async def resolve_twilio_credentials(
    session: AsyncSession,
    connection_id: str,
    *,
    require_enabled: bool = True,
    run_id: str | None = None,
) -> tuple[IntegrationConnection, TwilioCredentials]:
    connection = await session.get(IntegrationConnection, connection_id)
    if connection is None:
        raise HTTPException(404, "Twilio connection not found")
    if connection.provider != "twilio_voice":
        raise HTTPException(422, "Connection is not a Twilio Voice connection")
    if require_enabled and not connection.enabled:
        raise HTTPException(422, "Twilio connection is disabled")
    if connection.deleted_at is not None:
        raise HTTPException(422, "Twilio connection is deleted")

    if connection.credential_id:
        from voice_api.services.credential_service import credential_scope, lookup

        row = await lookup(session, connection.credential_id, lock=bool(run_id))
        if run_id:
            from voice_api.models import Run
            from voice_api.services.credential_lease_service import issue

            run = await session.get(Run, run_id)
            pinned = run.resolved_config.get("_resolved", {}).get("telephony_credential") if run else None
            if not pinned or pinned["credential_id"] != row.id or pinned["version"] != row.version:
                raise HTTPException(422, "Twilio run credential was changed or revoked")
            await issue(session, run_id, row)
        if row.provider != "twilio" or row.purpose != "twilio_voice" or row.status != "stored":
            raise HTTPException(422, "Twilio credential is unavailable")
        try:
            values = json.loads(CredentialVault.from_env().decrypt(row.ciphertext, row.key_id, scope=credential_scope(row)))
            if values["account_sid"] != (connection.config or {}).get("account_sid"):
                raise HTTPException(422, "Twilio credential Account SID does not match connection")
            return connection, TwilioCredentials(**values)
        except (VaultError, ValueError, KeyError, TypeError) as error:
            raise HTTPException(503, "Twilio credential is unavailable") from error

    from sqlalchemy import select

    secret = await session.scalar(
        select(IntegrationSecret).where(
            IntegrationSecret.connection_id == connection_id,
            IntegrationSecret.name == "auth_token",
        )
    )
    if secret is None:
        raise HTTPException(422, "Twilio connection is missing auth_token secret")

    try:
        auth_token = CredentialVault.from_env().decrypt(secret.ciphertext, secret.key_id,
            scope=SecretScope(secret.org_id, secret.id, connection.provider, secret.name, secret.version))
    except VaultError as error:
        raise HTTPException(503, "Failed to decrypt Twilio auth token") from error

    account_sid = str((connection.config or {}).get("account_sid", "")).strip()
    if not account_sid or not account_sid.startswith("AC"):
        raise HTTPException(422, "Invalid Twilio Account SID in connection config")

    from voice_api.api.v1.endpoints.integrations import secret_value

    # Webhook tokens remain readable; REST never substitutes one for a key.
    extras = {}
    for name in ("api_key_sid", "api_key_secret"):
        try:
            extras[name] = await secret_value(session, connection_id, name)
        except HTTPException as error:
            if error.status_code != 422:
                raise
    return connection, TwilioCredentials(account_sid=account_sid, auth_token=auth_token, **extras)


async def test_twilio_connection(credentials: TwilioCredentials) -> dict[str, Any]:
    client = Client(*credentials.rest_auth, account_sid=credentials.account_sid)
    try:
        account = await asyncio.to_thread(client.api.v2010.accounts(credentials.account_sid).fetch)
    except TwilioRestException as error:
        raise HTTPException(422, f"Twilio API error: {error.msg}") from error

    if account.status != "active":
        raise HTTPException(422, f"Twilio account is {account.status}")

    masked_sid = f"AC...{credentials.account_sid[-4:]}"
    if account.type != "Full":
        return {
            "status": "warning",
            "provider": "twilio_voice",
            "account_sid": masked_sid,
            "account_type": account.type,
            "message": "Connected, but Media Streams require an upgraded Twilio account. Trial accounts block <Stream>.",
            "phone_numbers": [],
        }

    try:
        numbers = await asyncio.to_thread(client.incoming_phone_numbers.list)
    except TwilioRestException as error:
        raise HTTPException(422, f"Failed to list Twilio phone numbers: {error.msg}") from error

    available_numbers = []
    for n in numbers:
        caps = getattr(n, "capabilities", {})
        voice_cap = (
            caps.get("voice", False) if isinstance(caps, dict) else getattr(caps, "voice", False)
        )
        if voice_cap:
            available_numbers.append(
                {
                    "sid": n.sid,
                    "phone_number": n.phone_number,
                    "friendly_name": n.friendly_name,
                    "voice": True,
                }
            )

    return {
        "status": "ok",
        "provider": "twilio_voice",
        "account_sid": masked_sid,
        "account_type": account.type,
        "phone_numbers": available_numbers,
    }


test_twilio_connection.__test__ = False


async def sync_twilio_phone_numbers(
    session: AsyncSession,
    connection_id: str,
) -> dict[str, Any]:
    connection, credentials = await resolve_twilio_credentials(
        session, connection_id, require_enabled=False
    )
    result = await test_twilio_connection(credentials)
    cfg = dict(connection.config or {})
    cfg["phone_numbers"] = result["phone_numbers"]
    cfg["account_type"] = result.get("account_type")
    connection.config = cfg
    flag_modified(connection, "config")
    await session.commit()
    return result


def validate_from_number(connection: IntegrationConnection, from_number: str) -> dict[str, Any]:
    phone_numbers = (connection.config or {}).get("phone_numbers", [])
    selected = next(
        (
            n
            for n in phone_numbers
            if n.get("phone_number") == from_number and n.get("voice", False)
        ),
        None,
    )
    if selected is None:
        raise HTTPException(
            422,
            "Selected From number does not belong to this Twilio connection or lacks voice capability",
        )
    return selected
