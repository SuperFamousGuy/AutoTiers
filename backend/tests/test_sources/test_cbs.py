import pytest
import respx
from httpx import Response
from app.data.sources.cbs import CBSFetcher


def test_cbs_fetcher_name():
    assert CBSFetcher.name == "cbs"


@pytest.mark.asyncio
async def test_cbs_fetcher_handles_network_failure_gracefully(test_db):
    with respx.mock(base_url="https://www.cbssports.com") as router:
        router.get(url__regex=r"/fantasy/football/projections/.*").mock(return_value=Response(500))
        fetcher = CBSFetcher()
        result = await fetcher.fetch(test_db)
        assert result.success is False
        assert result.rows_upserted == 0


@pytest.mark.asyncio
async def test_cbs_fetcher_handles_empty_html_gracefully(test_db):
    """If the page returns 200 but with no parseable table, return failed with warning."""
    with respx.mock(base_url="https://www.cbssports.com") as router:
        router.get(url__regex=r"/fantasy/football/projections/.*").mock(
            return_value=Response(200, text="<html><body><h1>Loading...</h1></body></html>"),
        )
        fetcher = CBSFetcher()
        result = await fetcher.fetch(test_db)
        assert result.success is False
        assert "JS-rendered" in (result.error or "") or "client-side rendered" in (result.error or "") or "investigation" in (result.error or "")
