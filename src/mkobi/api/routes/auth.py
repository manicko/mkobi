"""Authentication and registration routes.

This module provides endpoints for:
- Registering new users
- User login (authentication)
- JWT token refresh
- User logout
- Creating registration requests

All endpoints return standardized JSON responses.
"""

from hashlib import sha256
from ipaddress import ip_address
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from mkobi.api.deps import (
    get_auth_service,
    get_current_user_dependency,
    get_redis_client_dependency,
    require_admin_role,
    get_db_dependency,
)
from mkobi.api.schemas.responses import (
    admin_responses,
    auth_protected_responses,
    auth_public_responses,
    error_503,
)
from mkobi.db.repositories.user_repo import UserRepository
from mkobi.config import get_config
from mkobi.core.logging_config import get_logger
from mkobi.core import redis_client
from mkobi.core.security import (
    AsyncRateLimiter,
    COOKIE_NAME,
    RevocationStoreUnavailableError,
    create_access_token,
    create_refresh_token,
    decode_token,
    validate_refresh_token,
    delete_secure_cookie,
    set_secure_cookie,
    revoke_token,
    revoke_refresh_token,
    revoke_all_user_tokens,
    is_refresh_token_revoked,
    is_user_tokens_revoked,
)
from mkobi.models.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    RegistrationRequestCreate,
    RegistrationRequestResponse,
    SuccessResponse,
    Token,
    TokenWithUser,
)
from mkobi.models.enums import ErrorCode, RegistrationStatus
from mkobi.models.user import UserRead
from mkobi.services.auth_service import AuthService
from mkobi.utils.exceptions import AppException

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

# Sentinel peer used when the request has no usable client address. It still
# rate-limits, so a malformed or absent peer cannot become a bypass.
_UNKNOWN_PEER = "unknown"


def _rate_limit_keys(
    site: str, peer: str | None, identifier: str
) -> tuple[str, str]:
    """Derive the dual rate-limit keys (per-peer, per-identifier) for a site.

    Every auth rate-limit site enforces two bounds at *different* thresholds: a
    per-peer bound that a botnet cannot escape by rotating accounts, and a
    per-identifier bound that stops one user's failures from locking out a whole
    NAT or gateway. The peer ceiling is deliberately a multiple (10x) of the
    identifier bound at each site, so a shared-egress population tolerates ten
    times one user's failures before the peer bound engages. This helper is the
    single place the key format is defined so the dual bound is uniform across
    ``_handle_login``, ``refresh``, and ``register_request``.

    Scope: only the auth routes use this helper. ``api/routes/client_errors.py``
    and ``api/routes/upload.py`` derive IP rate-limit keys the same way but
    belong to another phase (C04-9) and are deliberately **not** migrated here;
    this helper does not cover them.

    Args:
        site: Rate-limit site name, for example ``"login"``.
        peer: Client peer address, or None when it is unavailable.
        identifier: The bound subject, always a digest of the submitted value
            (an email for the account sites, the presented cookie for refresh).
            The raw value is never placed in a key.

    Returns:
        tuple[str, str]: The per-peer key followed by the per-identifier key.
    """
    resolved_peer = peer if peer else _UNKNOWN_PEER
    return f"{site}:{resolved_peer}", f"{site}:id:{identifier}"


def _identifier_digest(value: str) -> str:
    """Return a key-safe digest of a rate-limit identifier.

    The digest keeps a submitted credential or account address out of the Redis
    key namespace while still giving each distinct value its own bucket. A
    truncated SHA-256 is used rather than the raw value so no email address or
    cookie is written into a rate-limit key, the same rule the ``refresh`` site
    applies to the presented session cookie.
    """
    return sha256(value.encode("utf-8")).hexdigest()[:32]


def _resolve_client_ip(request: Request) -> str:
    """Resolve the client peer to a string safe for a rate-limit key.

    ``ip_address`` raises ``ValueError`` on a non-IP peer, which would surface
    as a 500 where a 429 is intended and let a malformed peer bypass the limit.
    Fall back to the sentinel instead; the request is still rate-limited under
    the shared fallback bucket.
    """
    if not request.client:
        return _UNKNOWN_PEER
    try:
        return str(ip_address(request.client.host))
    except ValueError:
        logger.warning("Unparseable client peer: %s", request.client.host)
        return _UNKNOWN_PEER


async def _enforce_dual_rate_limit(
    rate_limiter: AsyncRateLimiter,
    site: str,
    peer: str,
    identifier: str,
    max_attempts: int,
    peer_max_attempts: int,
    ttl: int,
    detail: str,
) -> None:
    """Enforce both the per-peer and per-identifier bounds for a site.

    ``max_attempts`` bounds a single identifier (the security control that stops
    credential guessing at one account); ``peer_max_attempts`` is the coarser
    abuse ceiling for the peer as a whole. The peer ceiling is 10x the
    identifier bound so a shared egress address does not lock out ordinary
    users when one of them exhausts its own budget.

    Raises:
        AppException: With ``RATE_LIMIT_EXCEEDED`` if either bound is exceeded.
    """
    peer_key, identifier_key = _rate_limit_keys(site, peer, identifier)
    bounds = (
        (peer_key, peer_max_attempts),
        (identifier_key, max_attempts),
    )
    for key, limit in bounds:
        allowed, retry_after = await rate_limiter.check_rate_limit(
            key, max_attempts=limit, ttl=ttl
        )
        if not allowed:
            logger.warning("Rate limit exceeded for key: %s", key)
            raise AppException(
                code=ErrorCode.RATE_LIMIT_EXCEEDED,
                detail=detail,
                headers={"Retry-After": str(retry_after)} if retry_after else None,
            )


async def _handle_login(
    email: str,
    password: str,
    auth_service: AuthService,
    request: Request,
    response: Response,
    db: AsyncSession,
    redis_client: Any,
) -> TokenWithUser:
    """Common login logic and error handling."""
    # Apply rate limiting for login attempts with a dual bound: per peer (so a
    # botnet cannot spread by rotating accounts) and per submitted identifier
    # (so one user's failures cannot lock out a shared NAT). The identifier is a
    # digest of the submitted email, not the email itself, so no address is
    # written into a Redis key; this matches the refresh site's treatment of the
    # presented cookie. Hashing still prevents email enumeration via a rate
    # limit side-channel. Peer ceiling is 10x the identifier bound (50 vs 5)
    # so a shared egress address still serves other users after one exhausts
    # its own budget; the ratio, not three arbitrary numbers, keeps tuning
    # reviewable.
    client_ip = _resolve_client_ip(request)
    rate_limiter = AsyncRateLimiter(
        redis_client,
        fail_closed=get_config().rate_limiter_fail_closed,
    )
    await _enforce_dual_rate_limit(
        rate_limiter,
        site="login",
        peer=client_ip,
        identifier=_identifier_digest(email),
        max_attempts=5,
        peer_max_attempts=50,
        ttl=300,
        detail="Too many login attempts. Try again later.",
    )

    logger.info("Login attempt", extra={"email": email})

    token_data = await auth_service.login_user(email, password, db=db)

    if token_data is None:
        logger.warning("Login failed", extra={"email": email})
        raise AppException(
            code=ErrorCode.AUTHENTICATION_FAILED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.info("Login successful", extra={"email": email})

    # Create refresh token and set as httpOnly cookie
    user = token_data["user"]
    refresh_token = create_refresh_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role}
    )
    set_secure_cookie(
        response=response,
        key=COOKIE_NAME,
        value=refresh_token,
        max_age=get_config().jwt.refresh_token_expire_minutes * 60,
    )

    return TokenWithUser(
        access_token=token_data["access_token"],
        token_type="bearer",
        user=token_data["user"],
    )


@router.post(
    "/login",
    response_model=TokenWithUser,
    status_code=status.HTTP_200_OK,
    summary="User login",
    description="Authenticates user by email and password, returns JWT token with user data.",
    responses=auth_public_responses,
)
async def login(
    request: Request,
    response: Response,
    login_data: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db_dependency),
    redis_client: Any = Depends(get_redis_client_dependency),
) -> TokenWithUser:
    """User login endpoint."""
    return await _handle_login(
        email=login_data.email,
        password=login_data.password,
        auth_service=auth_service,
        request=request,
        response=response,
        db=db,
        redis_client=redis_client,
    )


@router.post(
    "/login/form",
    response_model=TokenWithUser,
    status_code=status.HTTP_200_OK,
    summary="User login (form)",
    description="Authentication via OAuth2 form. Calls common /login logic.",
    responses=auth_public_responses,
)
async def login_form(
    request: Request,
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db_dependency),
    redis_client: Any = Depends(get_redis_client_dependency),
) -> TokenWithUser:
    """Login endpoint via OAuth2 form."""
    return await _handle_login(
        email=form_data.username,
        password=form_data.password,
        auth_service=auth_service,
        request=request,
        response=response,
        db=db,
        redis_client=redis_client,
    )


@router.post(
    "/register",
    response_model=Token,
    status_code=status.HTTP_201_CREATED,
    summary="User registration (admin-only, deprecated for public)",
    description="Creates new user directly. Admin only. Public users should use /register-request instead.",
    responses=admin_responses,
)
async def register(
    register_data: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
    admin_user: UserRead = Depends(require_admin_role),
    db: AsyncSession = Depends(get_db_dependency),
) -> Token:
    """Admin-only user registration endpoint (deprecated for public use).

    Creates user directly and returns JWT access token.
    For public registration, use /auth/register-request instead.

    Args:
        register_data: Model with registration data.
        auth_service: Authentication service.
        admin_user: Current admin user (injected dependency).

    Returns:
        Token: Model with access_token and token_type.

    Raises:
        AppException 403: If user is not admin.
        AppException 422: Data validation error.
        AppException 500: Registration or token creation error.
    """
    logger.warning(
        "Deprecated /auth/register endpoint called. Use /auth/register-request for public registration.",
        extra={"email": register_data.email, "admin_user": admin_user.email},
    )

    try:
        user = await auth_service.register_user(
            email=register_data.email,
            password=register_data.password,
            db=db,
            role=register_data.role.value,
        )
    except ValueError as e:
        logger.warning(
            "Validation error during registration",
            extra={"email": register_data.email, "error": str(e)},
        )
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(
            "Registration error",
            extra={"email": register_data.email, "error": str(e)},
        )
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Registration error",
        ) from e

    try:
        access_token = auth_service.create_access_token(user.id, user.role)
    except Exception as e:
        logger.error(
            "Token creation error after registration",
            extra={"email": register_data.email, "error": str(e)},
        )
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Token creation error",
        ) from e

    logger.info("User registered successfully by admin", extra={"email": register_data.email, "admin": admin_user.email})
    return Token(access_token=access_token, token_type="bearer")


@router.post(
    "/refresh",
    response_model=Token,
    status_code=status.HTTP_200_OK,
    summary="Refresh token",
    description="Refreshes expired JWT access token using httpOnly refresh token cookie.",
    responses={**auth_public_responses, 503: error_503},
)
async def refresh(
    request: Request,
    response: Response,
    session: Annotated[AsyncSession, Depends(get_db_dependency)],
    redis_client: Any = Depends(get_redis_client_dependency),
) -> Token:
    """Token refresh endpoint.

    Accepts refresh token from httpOnly cookie,
    decodes it and issues new access token.

    Args:
        request: Request object to access cookies.
        response: FastAPI Response object to rotate the refresh cookie.
        session: Async database session.
        redis_client: Async Redis client for blacklist check.

    Returns:
        Token: Model with new access_token and token_type.

    Raises:
        AppException 401: Invalid, expired, or revoked token.
    """
    refresh_token_value = request.cookies.get(COOKIE_NAME)
    if not refresh_token_value:
        logger.warning("No refresh token in cookies")
        raise AppException(
            code=ErrorCode.AUTHENTICATION_FAILED,
            detail="Refresh token not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Apply rate limiting for refresh attempts with a dual bound: per peer and
    # per presented session. The session identifier is a digest of the cookie
    # value, not the value itself, so no credential is written into a Redis key.
    # Only requests that have a refresh token (actual auth attempts) are counted,
    # not routine navigation without cookies which wastes quota unnecessarily.
    # Peer ceiling is 10x the identifier bound (100 vs 10), the same ratio as
    # every other auth site, so a shared egress address does not lock out other
    # sessions when one refresh digest exhausts its own budget.
    client_ip = _resolve_client_ip(request)
    rate_limiter = AsyncRateLimiter(
        redis_client,
        fail_closed=get_config().rate_limiter_fail_closed,
    )
    await _enforce_dual_rate_limit(
        rate_limiter,
        site="refresh",
        peer=client_ip,
        identifier=_identifier_digest(refresh_token_value),
        max_attempts=10,
        peer_max_attempts=100,
        ttl=300,
        detail="Too many refresh attempts. Try again later.",
    )

    logger.info("Token refresh attempt")

    payload = validate_refresh_token(refresh_token_value)
    if payload is None:
        logger.warning("Invalid refresh token")
        raise AppException(
            code=ErrorCode.INVALID_TOKEN,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Check if refresh token is revoked
    jti = payload.get("jti")
    if jti:
        try:
            refresh_revoked = await is_refresh_token_revoked(redis_client, jti)
        except RevocationStoreUnavailableError as exc:
            logger.error("Revocation store unavailable during refresh: %s", exc)
            raise AppException(
                code=ErrorCode.SERVICE_UNAVAILABLE,
                detail="Authentication service is temporarily unavailable",
            ) from exc
        if refresh_revoked:
            logger.warning("Revoked refresh token used: jti=%s", jti)
            raise AppException(
                code=ErrorCode.TOKEN_REVOKED,
                detail="Refresh token has been revoked",
                headers={"WWW-Authenticate": "Bearer"},
            )

    user_id = payload.get("sub")
    if user_id is None:
        logger.warning("Token missing user_id")
        raise AppException(
            code=ErrorCode.INVALID_TOKEN,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = await UserRepository().get(UUID(user_id), session)
    if user is None:
        logger.warning("User not found during refresh", extra={"user_id": user_id})
        raise AppException(
            code=ErrorCode.AUTHENTICATION_FAILED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Reject refresh credentials issued at or before the user's revocation
    # marker. A token minted after it (for example, a fresh login following a
    # password change) is newer than the withdrawal and is allowed.
    issued_at = payload.get("iat")
    try:
        user_tokens_revoked = await is_user_tokens_revoked(
            redis_client, UUID(user_id), issued_at if isinstance(issued_at, int) else None
        )
    except RevocationStoreUnavailableError as exc:
        logger.error("Revocation store unavailable during refresh: %s", exc)
        raise AppException(
            code=ErrorCode.SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable",
        ) from exc
    if user_tokens_revoked:
        logger.warning("User tokens revoked: user_id=%s", user_id)
        delete_secure_cookie(response, COOKIE_NAME)
        raise AppException(
            code=ErrorCode.TOKEN_REVOKED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # The database row is co-authoritative with the marker on this path. This
    # check sits strictly after the marker branch so a deactivated-and-marked
    # user keeps receiving TOKEN_REVOKED byte-identically. The detail string
    # matches api/deps.py's inactive case so the two sites are indistinguishable
    # to a client. The refresh cookie is deliberately not cleared here; cookie
    # lifecycle is a separate decision.
    if not user.is_active:
        logger.warning("Refresh refused for deactivated user: user_id=%s", user_id)
        raise AppException(
            code=ErrorCode.AUTHENTICATION_FAILED,
            detail="User account is deactivated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"user_id": str(user.id), "email": user.email, "role": user.role}
    )

    # Rotate the refresh cookie on every successful refresh. Every check above
    # has passed, so this is the point after which the request cannot still be
    # refused. The presented token's jti is deliberately NOT revoked: reuse
    # detection would add a new server-side rejection path, and its false
    # positive (two tabs each refreshing concurrently) is a client concern that
    # belongs to the frontend's phase. Both tokens therefore stay valid until
    # their own TTL.
    rotated_refresh_token = create_refresh_token(
        data={"sub": str(user.id), "email": user.email, "role": user.role}
    )
    set_secure_cookie(
        response=response,
        key=COOKIE_NAME,
        value=rotated_refresh_token,
        max_age=get_config().jwt.refresh_token_expire_minutes * 60,
    )

    logger.info("Token refreshed successfully", extra={"user_id": user_id})
    return Token(access_token=access_token, token_type="bearer")


@router.get(
    "/me",
    response_model=UserRead,
    status_code=status.HTTP_200_OK,
    summary="Get current user data",
    description="Returns data of the currently authenticated user.",
    responses=auth_protected_responses,
)
async def get_current_user_info(
    current_user: UserRead = Depends(get_current_user_dependency),
) -> UserRead:
    """Endpoint to get current user information.

    Requires valid JWT token in Authorization header.

    Args:
        current_user: Currently authenticated user.

    Returns:
        UserRead: User model without password.
    """
    logger.info("Current user data request", extra={"email": current_user.email})
    return current_user


@router.post(
    "/logout",
    response_model=SuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="User logout",
    description="Logout current user by revoking tokens and clearing refresh token cookie.",
    responses=auth_protected_responses,
)
async def logout(
    request: Request,
    response: Response,
    current_user: Annotated[UserRead, Depends(get_current_user_dependency)],
    redis_client: Any = Depends(get_redis_client_dependency),
) -> SuccessResponse:
    """Logout endpoint.

    Revokes the current access token and refresh token cookie,
    then clears the refresh token cookie.

    Args:
        request: Request object to get tokens from header and cookies.
        response: FastAPI Response object to set/delete cookies.
        current_user: Currently authenticated user.
        redis_client: Async Redis client for token revocation.

    Returns:
        SuccessResponse: Success message.
    """
    logger.info("User logging out", extra={"email": current_user.email})

    # Revoke refresh token from cookie
    refresh_token_value = request.cookies.get(COOKIE_NAME)
    if refresh_token_value:
        refresh_payload = decode_token(refresh_token_value)
        if refresh_payload:
            refresh_jti = refresh_payload.get("jti")
            if refresh_jti:
                refresh_ttl = get_config().jwt.refresh_token_expire_minutes * 60
                await revoke_refresh_token(redis_client, refresh_jti, refresh_ttl)

    # Revoke access token from Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        access_token = auth_header[7:]  # Remove "Bearer " prefix
        access_payload = decode_token(access_token)
        if access_payload:
            access_jti = access_payload.get("jti")
            if access_jti:
                access_ttl = get_config().jwt.access_token_expire_minutes * 60
                await revoke_token(redis_client, access_jti, access_ttl)

    delete_secure_cookie(response, COOKIE_NAME)
    return SuccessResponse(message="Logged out successfully")


@router.post(
    "/change-password",
    response_model=SuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Change password",
    description="Change current user password. Requires current password verification.",
    responses=auth_protected_responses,
)
async def change_password(
    password_data: ChangePasswordRequest,
    current_user: UserRead = Depends(get_current_user_dependency),
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db_dependency),
    redis_client: Any = Depends(get_redis_client_dependency),
) -> SuccessResponse:
    """Password change endpoint.

    Validates new password confirmation and current password,
    then updates the password in the database.

    Args:
        password_data: Password change request data.
        current_user: Currently authenticated user.
        auth_service: Authentication service.
        redis_client: Async Redis client for token revocation.

    Returns:
        SuccessResponse: Success message.

    Raises:
        AppException 422: If password confirmation does not match.
        AppException 401: If current password is incorrect.
    """
    try:
        await auth_service.change_password(
            user_id=current_user.id,
            current_password=password_data.current_password,
            new_password=password_data.new_password,
            db=db,
        )
    except ValueError as e:
        logger.warning(
            "Password change failed",
            extra={"user_id": str(current_user.id), "error": str(e)},
        )
        raise AppException(
            code=ErrorCode.AUTHENTICATION_FAILED,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(
            "Password change error",
            extra={"user_id": str(current_user.id), "error": str(e)},
        )
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Password change error",
        ) from e

    # The service has committed the new password, so the old credential is now
    # stale. Revoke every outstanding token for this user. The marker is a
    # non-transactional Redis write and is therefore placed after the commit,
    # following the pattern in admin.py::update_user_active_admin_endpoint: a
    # revocation before the commit would leave a live marker on a password
    # change that could still roll back.
    settings = get_config()
    await revoke_all_user_tokens(
        redis_client=redis_client,
        user_id=current_user.id,
        access_ttl=settings.jwt.access_token_expire_minutes * 60,
        refresh_ttl=settings.jwt.refresh_token_expire_minutes * 60,
    )

    logger.info("Password changed successfully", extra={"user_id": str(current_user.id)})
    return SuccessResponse(message="Password changed successfully")


@router.post(
    "/register-request",
    response_model=RegistrationRequestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registration request",
    description="Creates registration request. Admin must approve the request.",
    responses=auth_public_responses,
)
async def register_request(
    request_data: RegistrationRequestCreate,
    request: Request,
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db_dependency),
) -> RegistrationRequestResponse:
    """Registration request creation endpoint.

    Saves request to database with PENDING status.
    Admin must approve or reject the request.

    Args:
        request_data: Request data (email).
        request: Request object to get IP.
        auth_service: Authentication service.

    Returns:
        RegistrationRequestResponse: Created request with id, email, and status.

    Raises:
        AppException 422: Request already exists.
    """
    # Get client IP address. An unparseable peer is recorded as absent rather
    # than raising: a malformed peer must not become a 500 (which would bypass
    # the rate limit). The rate-limit peer falls back to a sentinel.
    resolved_ip = _resolve_client_ip(request)
    client_ip: str | None = None if resolved_ip == _UNKNOWN_PEER else resolved_ip

    # Apply rate limiting for registration requests with a dual bound: per peer
    # and per submitted email. The email identifier is a digest, not the raw
    # address, so no email is written into a Redis key (matching the login and
    # refresh sites). The email bound is explicit rather than a fallback used
    # only when the peer is absent. Peer ceiling is 10x the identifier bound
    # (30 vs 3), the same ratio as every other auth site; the peer bound is an
    # abuse ceiling, not a ration on ordinary requests.
    rate_limiter = AsyncRateLimiter(
        redis_client.get_async_redis_client(),
        fail_closed=get_config().rate_limiter_fail_closed,
    )
    await _enforce_dual_rate_limit(
        rate_limiter,
        site="register-request",
        peer=resolved_ip,
        identifier=_identifier_digest(request_data.email),
        max_attempts=3,
        peer_max_attempts=30,
        ttl=3600,
        detail="Too many registration requests. Try again later.",
    )

    logger.info(
        "Registration request attempt",
        extra={"email": request_data.email, "ip": client_ip},
    )

    try:
        result = await auth_service.register_request(
            email=request_data.email,
            db=db,
            ip=client_ip,
        )
    except ValueError as e:
        logger.warning(
            "Validation error creating registration request",
            extra={"email": request_data.email, "error": str(e)},
        )
        raise AppException(
            code=ErrorCode.VALIDATION_ERROR,
            detail=str(e),
        ) from e
    except Exception as e:
        logger.error(
            "Error creating registration request",
            extra={"email": request_data.email, "error": str(e)},
        )
        raise AppException(
            code=ErrorCode.INTERNAL_ERROR,
            detail="Registration request error",
        ) from e

    logger.info(
        "Registration request created",
        extra={"email": request_data.email, "id": str(result["id"])},
    )
    return RegistrationRequestResponse(
        id=result["id"],
        email=request_data.email,
        status=RegistrationStatus(result["status"]),
    )