"""Clerk organization directory. Membership is always read from Clerk live."""

from dataclasses import dataclass

from clerk_backend_api import Clerk
from fastapi import HTTPException

from voice_api.core.config import get_settings


@dataclass(frozen=True)
class JoinedOrganization:
    clerk_org_id: str
    name: str
    role: str


@dataclass(frozen=True)
class OrganizationMember:
    user_id: str
    role: str
    email: str | None
    first_name: str | None
    last_name: str | None


class ClerkOrganizationDirectory:
    def __init__(self, secret_key: str):
        self.secret_key = secret_key

    @staticmethod
    def _text(value: object) -> str | None:
        return value if isinstance(value, str) else None

    async def verified_profile(self, user_id: str) -> dict[str, str | None]:
        """Return Clerk's verified primary email and required display-name fields."""
        try:
            async with Clerk(bearer_auth=self.secret_key) as clerk:
                user = await clerk.users.get_async(user_id=user_id)
        except Exception as exc:
            raise HTTPException(503, "Clerk profile lookup unavailable") from exc
        email = next(
            (
                item.email_address
                for item in user.email_addresses
                if item.id == user.primary_email_address_id
                and item.verification is not None
                and getattr(item.verification.status, "value", item.verification.status)
                == "verified"
            ),
            None,
        )
        return {
            "email": email,
            "first_name": self._text(user.first_name),
            "last_name": self._text(user.last_name),
        }

    async def create_organization(self, user_id: str, name: str) -> dict[str, str]:
        """Create an org in Clerk and make the signed-in user its creator/admin."""
        try:
            async with Clerk(bearer_auth=self.secret_key) as clerk:
                organization = await clerk.organizations.create_async(
                    request={"name": name, "created_by": user_id}
                )
        except Exception as exc:
            raise HTTPException(502, "Clerk organization creation failed") from exc
        return {"id": organization.id, "name": organization.name}

    async def delete_organization(self, org_id: str) -> None:
        """Compensate a failed local provisioning transaction."""
        try:
            async with Clerk(bearer_auth=self.secret_key) as clerk:
                await clerk.organizations.delete_async(organization_id=org_id)
        except Exception as exc:
            raise HTTPException(502, "Clerk organization cleanup failed") from exc

    async def joined(self, user_id: str) -> list[JoinedOrganization]:
        results: list[JoinedOrganization] = []
        try:
            async with Clerk(bearer_auth=self.secret_key) as clerk:
                offset = 0
                while True:
                    page = await clerk.users.get_organization_memberships_async(
                        user_id=user_id, limit=100, offset=offset
                    )
                    results.extend(
                        JoinedOrganization(
                            clerk_org_id=item.organization.id,
                            name=item.organization.name,
                            role=item.role,
                        )
                        for item in page.data
                    )
                    offset += len(page.data)
                    if offset >= page.total_count or not page.data:
                        return results
        except Exception as exc:
            raise HTTPException(503, "Clerk organization lookup unavailable") from exc

    async def membership(self, org_id: str, user_id: str) -> OrganizationMember | None:
        try:
            async with Clerk(bearer_auth=self.secret_key) as clerk:
                page = await clerk.organization_memberships.list_async(
                    organization_id=org_id, user_id=[user_id], limit=1
                )
        except Exception as exc:
            raise HTTPException(503, "Clerk membership lookup unavailable") from exc
        for item in page.data:
            public = item.public_user_data
            if public and public.user_id == user_id:
                return OrganizationMember(
                    user_id=user_id,
                    role=item.role,
                    email=self._text(getattr(public, "identifier", None)),
                    first_name=self._text(getattr(public, "first_name", None)),
                    last_name=self._text(getattr(public, "last_name", None)),
                )
        return None

    async def members(self, org_id: str) -> list[OrganizationMember]:
        results: list[OrganizationMember] = []
        try:
            async with Clerk(bearer_auth=self.secret_key) as clerk:
                offset = 0
                while True:
                    page = await clerk.organization_memberships.list_async(
                        organization_id=org_id, limit=100, offset=offset
                    )
                    for item in page.data:
                        public = item.public_user_data
                        if public:
                            results.append(
                                OrganizationMember(
                                    user_id=public.user_id,
                                    role=item.role,
                                    email=self._text(getattr(public, "identifier", None)),
                                    first_name=self._text(getattr(public, "first_name", None)),
                                    last_name=self._text(getattr(public, "last_name", None)),
                                )
                            )
                    offset += len(page.data)
                    if offset >= page.total_count or not page.data:
                        return results
        except Exception as exc:
            raise HTTPException(503, "Clerk member lookup unavailable") from exc

    async def invitations(self, org_id: str) -> list[dict]:
        results: list[dict] = []
        try:
            async with Clerk(bearer_auth=self.secret_key) as clerk:
                offset = 0
                while True:
                    page = await clerk.organization_invitations.list_async(
                        organization_id=org_id, limit=100, offset=offset
                    )
                    results.extend(
                        {
                            "id": item.id,
                            "email_address": item.email_address,
                            "role": item.role,
                            "status": item.status or "pending",
                        }
                        for item in page.data
                    )
                    offset += len(page.data)
                    if offset >= page.total_count or not page.data:
                        return results
        except Exception as exc:
            raise HTTPException(503, "Clerk invitation lookup unavailable") from exc

    async def invite(self, org_id: str, inviter_id: str, email: str, role: str) -> dict:
        try:
            async with Clerk(bearer_auth=self.secret_key) as clerk:
                item = await clerk.organization_invitations.create_async(
                    organization_id=org_id,
                    inviter_user_id=inviter_id,
                    email_address=email,
                    role=role,
                    notify=True,
                )
        except Exception as exc:
            raise HTTPException(502, "Clerk invitation failed") from exc
        return {
            "id": item.id,
            "email_address": item.email_address,
            "role": item.role,
            "status": item.status or "pending",
        }

    async def revoke(self, org_id: str, invitation_id: str, requester_id: str) -> None:
        try:
            async with Clerk(bearer_auth=self.secret_key) as clerk:
                await clerk.organization_invitations.revoke_async(
                    organization_id=org_id,
                    invitation_id=invitation_id,
                    requesting_user_id=requester_id,
                )
        except Exception as exc:
            raise HTTPException(502, "Clerk invitation revocation failed") from exc

    async def change_role(self, org_id: str, user_id: str, role: str) -> None:
        try:
            async with Clerk(bearer_auth=self.secret_key) as clerk:
                await clerk.organization_memberships.update_async(
                    organization_id=org_id, user_id=user_id, role=role
                )
        except Exception as exc:
            raise HTTPException(502, "Clerk role update failed") from exc

    async def remove_member(self, org_id: str, user_id: str) -> None:
        try:
            async with Clerk(bearer_auth=self.secret_key) as clerk:
                await clerk.organization_memberships.delete_async(
                    organization_id=org_id, user_id=user_id
                )
        except Exception as exc:
            raise HTTPException(502, "Clerk membership removal failed") from exc


def get_clerk_organization_directory() -> ClerkOrganizationDirectory:
    secret = get_settings().clerk_secret_key
    if not secret:
        raise HTTPException(503, "Clerk authentication is not configured")
    return ClerkOrganizationDirectory(secret)
