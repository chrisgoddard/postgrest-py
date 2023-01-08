from unittest.mock import patch

import pytest
from httpx import BasicAuth, Headers

from postgrest import SyncPostgrestClient
from postgrest.exceptions import APIError


@pytest.fixture
def postgrest_client():
    with SyncPostgrestClient("https://example.com") as client:
        yield client


class TestConstructor:
    def test_simple(self, postgrest_client: SyncPostgrestClient):
        session = postgrest_client.session

        assert session.base_url == "https://example.com"
        headers = Headers(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Accept-Profile": "public",
                "Content-Profile": "public",
            }
        )
        assert session.headers.items() >= headers.items()

    @pytest.mark.asyncio
    def test_custom_headers(self):
        with SyncPostgrestClient(
            "https://example.com", schema="pub", headers={"Custom-Header": "value"}
        ) as client:
            session = client.session

            assert session.base_url == "https://example.com"
            headers = Headers(
                {
                    "Accept-Profile": "pub",
                    "Content-Profile": "pub",
                    "Custom-Header": "value",
                }
            )
            assert session.headers.items() >= headers.items()


class TestAuth:
    def test_auth_token(self, postgrest_client: SyncPostgrestClient):
        postgrest_client.auth("s3cr3t")
        session = postgrest_client.session

        assert session.headers["Authorization"] == "Bearer s3cr3t"

    def test_auth_basic(self, postgrest_client: SyncPostgrestClient):
        postgrest_client.auth(None, username="admin", password="s3cr3t")
        session = postgrest_client.session

        assert isinstance(session.auth, BasicAuth)
        assert session.auth._auth_header == BasicAuth("admin", "s3cr3t")._auth_header


def test_schema(postgrest_client: SyncPostgrestClient):
    postgrest_client.schema("private")
    session = postgrest_client.session
    subheaders = {
        "accept-profile": "private",
        "content-profile": "private",
    }

    assert subheaders.items() < dict(session.headers).items()


@pytest.mark.asyncio
def test_params_purged_after_execute(postgrest_client: SyncPostgrestClient):
    assert len(postgrest_client.session.params) == 0
    with pytest.raises(APIError):
        postgrest_client.from_("test").select("a", "b").eq("c", "d").execute()
    assert len(postgrest_client.session.params) == 0


@pytest.mark.asyncio
def test_response_status_code_outside_ok(postgrest_client: SyncPostgrestClient):
    with pytest.raises(APIError) as exc_info:
        postgrest_client.from_("test").select("a", "b").eq(
            "c", "d"
        ).execute()  # gives status_code = 400
    exc_response = exc_info.value.json()
    assert not exc_response.get("success")
    assert isinstance(exc_response.get("errors"), list)
    assert (
        isinstance(exc_response["errors"][0], dict)
        and "code" in exc_response["errors"][0]
    )
    assert exc_response["errors"][0].get("code") == 400


@pytest.mark.asyncio
def test_response_maybe_single(postgrest_client: SyncPostgrestClient):
    with patch(
        "postgrest._sync.request_builder.SyncSingleRequestBuilder.execute",
        side_effect=APIError(
            {"message": "mock error", "code": "400", "hint": "mock", "details": "mock"}
        ),
    ):
        client = (
            postgrest_client.from_("test").select("a", "b").eq("c", "d").maybe_single()
        )
        assert "Accept" in client.headers
        assert client.headers.get("Accept") == "application/vnd.pgrst.object+json"
        with pytest.raises(APIError) as exc_info:
            client.execute()
        assert isinstance(exc_info, pytest.ExceptionInfo)
        exc_response = exc_info.value.json()
        assert isinstance(exc_response.get("message"), str)
        assert "code" in exc_response and int(exc_response["code"]) == 204
