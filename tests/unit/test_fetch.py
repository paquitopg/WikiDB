import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from wikidb.fetch import FetchFailed, fetch_listing

CSV = "mail,affectation\nmarie.curie@finances.gouv.fr,2BLF\n".encode("utf-8")
NOW = datetime(2026, 10, 15, 5, 0, tzinfo=timezone.utc)


class Handler(BaseHTTPRequestHandler):
    status, body, seen_agent = 200, CSV, None

    def do_GET(self):
        Handler.seen_agent = self.headers.get("User-Agent")
        self.send_response(Handler.status)
        self.end_headers()
        self.wfile.write(Handler.body)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    Handler.status, Handler.body = 200, CSV
    yield f"http://127.0.0.1:{httpd.server_address[1]}/csvd/annuaire.csv"
    httpd.shutdown()


class FakeS3:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body):
        self.objects[(Bucket, Key)] = Body


def test_listing_is_downloaded_with_the_curl_agent_and_stored_under_a_dated_key(server):
    s3 = FakeS3()
    key = fetch_listing(server, s3, "hr", "listings/", NOW)
    assert key == "listings/annuaire-20261015T050000Z.csv"
    assert s3.objects[("hr", key)] == CSV
    assert Handler.seen_agent.startswith("curl/")


def test_a_non_200_answer_stores_nothing(server):
    Handler.status = 503
    s3 = FakeS3()
    with pytest.raises(FetchFailed, match="503"):
        fetch_listing(server, s3, "hr", "listings/", NOW)
    assert s3.objects == {}


def test_a_file_without_the_directory_columns_stores_nothing(server):
    Handler.body = b"<html>maintenance</html>"
    s3 = FakeS3()
    with pytest.raises(FetchFailed, match="columns"):
        fetch_listing(server, s3, "hr", "listings/", NOW)
    assert s3.objects == {}


def test_latin1_listing_is_stored_as_utf8(server):
    Handler.body = "mail,affectation\nhélène@finances.gouv.fr,2BLF\n".encode("iso-8859-1")
    s3 = FakeS3()
    key = fetch_listing(server, s3, "hr", "listings/", NOW)
    assert "hélène".encode("utf-8") in s3.objects[("hr", key)]
