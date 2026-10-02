"""Tests for the timestamped user-level revocation marker.

The marker models credential rotation: credentials issued before the
revocation are rejected, credentials issued afterwards are allowed (so a
re-login after a password change yields a working session). Deactivation is
still guaranteed by the ``is_active`` checks on the token-issuing paths.

Tests cover:
- ``revoke_all_user_tokens`` stores a parseable epoch-millisecond timestamp
- a token whose ``iat`` predates the marker is rejected
- a token whose ``iat`` is newer than the marker is allowed
- a legacy non-integer marker value still rejects (fail closed)
- a credential with no ``iat`` is rejected (fail closed)
"""

from uuid import uuid4

from mkobi.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    is_user_tokens_revoked,
    revoke_all_user_tokens,
    validate_refresh_token,
)
from tests.conftest import MockRedis


async def _marker_value(redis_client, user_id):
    """Read the raw value stored under the user's revocation key."""
    return await redis_client.get(f"user_tokens_revoked:{user_id}")


class TestRevokeAllUserTokensMarker:
    """The writer stores a timestamp, not a literal."""

    async def test_revoke_all_user_tokens_writes_timestamp(self) -> None:
        redis_client = MockRedis()
        user_id = uuid4()

        await revoke_all_user_tokens(
            redis_client, user_id, access_ttl=900, refresh_ttl=604800
        )

        raw = await _marker_value(redis_client, user_id)
        assert raw is not None
        assert raw != "revoked"
        int(raw)  # must be a parseable integer, not an opaque literal

    async def test_revoke_all_user_tokens_ttl_is_max_of_both(self) -> None:
        redis_client = MockRedis()
        user_id = uuid4()

        await revoke_all_user_tokens(
            redis_client, user_id, access_ttl=900, refresh_ttl=604800
        )

        assert redis_client._ttls[f"user_tokens_revoked:{user_id}"] == 604800


class TestIsUserTokensRevokedOrdering:
    """The reader compares the token's iat against the marker."""

    async def test_is_user_tokens_revoked_credential_before_marker_rejected(
        self,
    ) -> None:
        redis_client = MockRedis()
        user_id = uuid4()
        await revoke_all_user_tokens(
            redis_client, user_id, access_ttl=900, refresh_ttl=604800
        )
        revoked_at = int(await _marker_value(redis_client, user_id))

        assert (
            await is_user_tokens_revoked(
                redis_client, user_id, issued_at=revoked_at - 1
            )
            is True
        )

    async def test_is_user_tokens_revoked_credential_at_marker_rejected(self) -> None:
        redis_client = MockRedis()
        user_id = uuid4()
        await revoke_all_user_tokens(
            redis_client, user_id, access_ttl=900, refresh_ttl=604800
        )
        revoked_at = int(await _marker_value(redis_client, user_id))

        assert (
            await is_user_tokens_revoked(redis_client, user_id, issued_at=revoked_at)
            is True
        )

    async def test_is_user_tokens_revoked_credential_after_marker_allowed(
        self,
    ) -> None:
        redis_client = MockRedis()
        user_id = uuid4()
        await revoke_all_user_tokens(
            redis_client, user_id, access_ttl=900, refresh_ttl=604800
        )
        revoked_at = int(await _marker_value(redis_client, user_id))

        assert (
            await is_user_tokens_revoked(
                redis_client, user_id, issued_at=revoked_at + 1
            )
            is False
        )

    async def test_is_user_tokens_revoked_absent_marker_allows(self) -> None:
        assert await is_user_tokens_revoked(MockRedis(), uuid4(), issued_at=1) is False


class TestIsUserTokensRevokedFailClosed:
    """Unrecognisable marker values and undatable tokens must reject."""

    async def test_is_user_tokens_revoked_legacy_non_integer_rejects(self) -> None:
        redis_client = MockRedis()
        user_id = uuid4()
        # A deployment that has not restarted still holds the old literal.
        redis_client._data[f"user_tokens_revoked:{user_id}"] = "revoked"

        assert (
            await is_user_tokens_revoked(redis_client, user_id, issued_at=10**15)
            is True
        )

    async def test_is_user_tokens_revoked_undatable_credential_rejects(self) -> None:
        redis_client = MockRedis()
        user_id = uuid4()
        await revoke_all_user_tokens(
            redis_client, user_id, access_ttl=900, refresh_ttl=604800
        )

        assert (
            await is_user_tokens_revoked(redis_client, user_id, issued_at=None) is True
        )


class TestMintedTokensCarryIat:
    """The comparison depends on the iat claim surviving encode/decode."""

    async def test_access_token_carries_int_iat(self) -> None:
        payload = decode_token(create_access_token({"user_id": "u", "email": "a@b.c"}))

        assert payload is not None
        assert isinstance(payload.get("iat"), int)

    async def test_refresh_token_carries_int_iat(self) -> None:
        payload = validate_refresh_token(
            create_refresh_token({"sub": "u", "email": "a@b.c"})
        )

        assert payload is not None
        assert isinstance(payload.get("iat"), int)
