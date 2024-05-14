import pytest
from base64 import b64encode
from fastapi.exceptions import HTTPException

from models.user import User
from handler.database import db_user_handler
from handler.auth import auth_handler, oauth_handler
from handler.auth.base_handler import WRITE_SCOPES
from handler.auth.hybrid_auth import HybridAuthBackend


def test_verify_password():
    assert auth_handler.verify_password(
        "password", auth_handler.get_password_hash("password")
    )
    assert not auth_handler.verify_password(
        "password", auth_handler.get_password_hash("notpassword")
    )


def test_authenticate_user(admin_user: User):
    current_user = auth_handler.authenticate_user("test_admin", "test_admin_password")

    assert current_user
    assert current_user.id == admin_user.id


async def test_get_current_active_user_from_session(editor_user: User):
    class MockConnection:
        def __init__(self):
            self.session = {"iss": "romm:auth", "sub": editor_user.username}

    conn = MockConnection()
    current_user = await auth_handler.get_current_active_user_from_session(conn)

    assert current_user
    assert isinstance(current_user, User)
    assert current_user.id == editor_user.id


async def test_get_current_active_user_from_session_bad_username(editor_user: User):
    class MockConnection:
        def __init__(self):
            self.session = {"iss": "romm:auth", "sub": "not_real_username"}

    conn = MockConnection()

    try:
        await auth_handler.get_current_active_user_from_session(conn)
    except HTTPException as e:
        assert e.status_code == 403
        assert e.detail == "User not found"


async def test_get_current_active_user_from_session_disabled_user(editor_user: User):
    class MockConnection:
        def __init__(self):
            self.session = {"iss": "romm:auth", "sub": editor_user.username}
            self.headers = {}

    conn = MockConnection()

    db_user_handler.update_user(editor_user.id, {"enabled": False})

    try:
        await auth_handler.get_current_active_user_from_session(conn)
    except HTTPException as e:
        assert e.status_code == 403
        assert e.detail == "Inactive user"


def test_create_default_admin_user():
    auth_handler.create_default_admin_user()

    user = db_user_handler.get_user_by_username("test_admin")
    assert user.username == "test_admin"
    assert auth_handler.verify_password("test_admin_password", user.hashed_password)

    users = db_user_handler.get_users()
    assert len(users) == 1

    auth_handler.create_default_admin_user()

    users = db_user_handler.get_users()
    assert len(users) == 1


async def test_hybrid_auth_backend_session(editor_user: User):
    class MockConnection:
        def __init__(self):
            self.session = {"iss": "romm:auth", "sub": editor_user.username}

    backend = HybridAuthBackend()
    conn = MockConnection()

    creds, user = await backend.authenticate(conn)

    assert user.id == editor_user.id
    assert creds.scopes == editor_user.oauth_scopes
    assert creds.scopes == WRITE_SCOPES


async def test_hybrid_auth_backend_empty_session_and_headers(editor_user: User):
    class MockConnection:
        def __init__(self):
            self.session = {}
            self.headers = {}

    backend = HybridAuthBackend()
    conn = MockConnection()

    creds, user = await backend.authenticate(conn)

    assert not user
    assert creds.scopes == []


async def test_hybrid_auth_backend_bearer_auth_header(editor_user: User):
    access_token = oauth_handler.create_oauth_token(
        data={
            "sub": editor_user.username,
            "iss": "romm:oauth",
            "scopes": " ".join(editor_user.oauth_scopes),
            "type": "access",
        },
    )

    class MockConnection:
        def __init__(self):
            self.session = {}
            self.headers = {"Authorization": f"Bearer {access_token}"}

    backend = HybridAuthBackend()
    conn = MockConnection()

    creds, user = await backend.authenticate(conn)

    assert user.id == editor_user.id
    assert set(creds.scopes).issubset(editor_user.oauth_scopes)


async def test_hybrid_auth_backend_bearer_invalid_token(editor_user: User):
    class MockConnection:
        def __init__(self):
            self.session = {}
            self.headers = {"Authorization": "Bearer invalid_token"}

    backend = HybridAuthBackend()
    conn = MockConnection()

    with pytest.raises(HTTPException):
        await backend.authenticate(conn)


async def test_hybrid_auth_backend_basic_auth_header(editor_user: User):
    token = b64encode("test_editor:test_editor_password".encode()).decode()

    class MockConnection:
        def __init__(self):
            self.session = {}
            self.headers = {"Authorization": f"Basic {token}"}

    backend = HybridAuthBackend()
    conn = MockConnection()

    creds, user = await backend.authenticate(conn)

    assert user.id == editor_user.id
    assert creds.scopes == WRITE_SCOPES
    assert set(creds.scopes).issubset(editor_user.oauth_scopes)


async def test_hybrid_auth_backend_basic_auth_header_unencoded(editor_user: User):
    class MockConnection:
        def __init__(self):
            self.session = {}
            self.headers = {"Authorization": "Basic test_editor:test_editor_password"}

    backend = HybridAuthBackend()
    conn = MockConnection()

    with pytest.raises(HTTPException):
        await backend.authenticate(conn)


async def test_hybrid_auth_backend_invalid_scheme():
    class MockConnection:
        def __init__(self):
            self.session = {}
            self.headers = {"Authorization": "Some invalid_scheme"}

    backend = HybridAuthBackend()
    conn = MockConnection()

    creds, user = await backend.authenticate(conn)

    assert not user
    assert creds.scopes == []


async def test_hybrid_auth_backend_with_refresh_token(editor_user: User):
    refresh_token = oauth_handler.create_oauth_token(
        data={
            "sub": editor_user.username,
            "iss": "romm:oauth",
            "scopes": " ".join(editor_user.oauth_scopes),
            "type": "refresh",
        },
    )

    class MockConnection:
        def __init__(self):
            self.session = {}
            self.headers = {"Authorization": f"Bearer {refresh_token}"}

    backend = HybridAuthBackend()
    conn = MockConnection()

    creds, user = await backend.authenticate(conn)

    assert not user
    assert creds.scopes == []


async def test_hybrid_auth_backend_scope_subset(editor_user: User):
    scopes = editor_user.oauth_scopes[:3]
    access_token = oauth_handler.create_oauth_token(
        data={
            "sub": editor_user.username,
            "iss": "romm:oauth",
            "scopes": " ".join(scopes),
            "type": "access",
        },
    )

    class MockConnection:
        def __init__(self):
            self.session = {}
            self.headers = {"Authorization": f"Bearer {access_token}"}

    backend = HybridAuthBackend()
    conn = MockConnection()

    creds, user = await backend.authenticate(conn)

    assert user.id == editor_user.id
    assert set(creds.scopes).issubset(editor_user.oauth_scopes)
    assert set(creds.scopes).issubset(scopes)
