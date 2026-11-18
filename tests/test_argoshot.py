import io
import json
import os
import unittest
import urllib.error
import urllib.request
from email.message import Message
from unittest import mock

from argoshot import Argoshot, ArgoshotError, build_query, parse_error, sign


class SignatureTest(unittest.TestCase):
    def test_server_vector(self):
        # The server's own test (jai-web-framework framework/Screenshots/tests/privacy/app.jai:194):
        # hmac_sha256("secret-of-the-customer-1234", "html=x&access_key=key-<tenant>"), lowercase hex.
        client = Argoshot("key-2", secret_key="secret-of-the-customer-1234")
        self.assertEqual(
            client.url(html="x"),
            "https://api.argoshot.com/take?html=x&access_key=key-2&signature=9488e5f178e81282b921f410775de15b0767f894504cd18bd66f35616d60ffd1",
        )

    def test_sorted_encoded_lists_numbers_booleans(self):
        client = Argoshot("AK_test", secret_key="SK_test")
        url = client.url(
            {
                "url": "https://example.com/a b?x=1&y=2",
                "format": "png",
                "full_page": True,
                "viewport_width": 1280,
                "device_scale_factor": 1.5,
                "hide_selectors": [".a", "#b .c"],
            }
        )
        self.assertEqual(
            url,
            "https://api.argoshot.com/take?device_scale_factor=1.5&format=png&full_page=true&hide_selectors=.a&hide_selectors=%23b%20.c&url=https%3A%2F%2Fexample.com%2Fa%20b%3Fx%3D1%26y%3D2&viewport_width=1280&access_key=AK_test&signature=1a6f9d69eae82c57575f031ba76325705f5c0ddc6b48380a6fa7964c8a497b1c",
        )

    def test_non_ascii_html(self):
        client = Argoshot("AK_test", secret_key="SK_test")
        self.assertEqual(
            client.url(html="<h1>Hi — café + &</h1>", format="png"),
            "https://api.argoshot.com/take?format=png&html=%3Ch1%3EHi%20%E2%80%94%20caf%C3%A9%20%2B%20%26%3C%2Fh1%3E&access_key=AK_test&signature=a1fb4eea53e2c394dce7ab32e31a26a2c8c85b8ebc53ac330ddb0cc441ee9eb7",
        )

    def test_unsigned_custom_base_none_skipped(self):
        client = Argoshot("AK_test", base_url="http://localhost:8080/")
        self.assertEqual(
            client.url(url="https://example.com", format="png", selector=None, access_key="other", signature="x"),
            "http://localhost:8080/take?format=png&url=https%3A%2F%2Fexample.com&access_key=AK_test",
        )

    def test_reserved_characters(self):
        self.assertEqual(build_query({"styles": "a{content:'!()*'}"}), "styles=a%7Bcontent%3A%27%21%28%29%2A%27%7D")

    def test_sign(self):
        self.assertEqual(sign("secret-of-the-customer-1234", "html=x&access_key=key-2"), "9488e5f178e81282b921f410775de15b0767f894504cd18bd66f35616d60ffd1")


class ErrorTest(unittest.TestCase):
    def test_api_error(self):
        body = json.dumps(
            {
                "is_successful": False,
                "error_code": "selector_not_found",
                "error_message": "Nothing matches the selector: #hero",
                "documentation_url": "https://argoshot.com/docs/errors/selector-not-found/",
            }
        )
        e = parse_error(400, body)
        self.assertEqual(e.code, "selector_not_found")
        self.assertEqual(e.message, "Nothing matches the selector: #hero")
        self.assertEqual(e.status, 400)
        self.assertEqual(e.documentation_url, "https://argoshot.com/docs/errors/selector-not-found/")

    def test_upgrade_retry_and_not_json(self):
        e = parse_error(402, '{"is_successful":false,"error_code":"free_tier_exhausted","error_message":"Used.","upgrade_url":"https://argoshot.com/pricing"}', "5")
        self.assertEqual(e.code, "free_tier_exhausted")
        self.assertEqual(e.upgrade_url, "https://argoshot.com/pricing")
        self.assertEqual(e.retry_after, 5)
        bad = parse_error(502, "<html>Bad gateway</html>")
        self.assertEqual(bad.code, "http_error")
        self.assertEqual(bad.status, 502)
        self.assertIn("HTTP 502", bad.message)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class TakeTest(unittest.TestCase):
    def test_get_signed_with_header(self):
        client = Argoshot("AK_test", secret_key="SK_test")
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b"\x89PNG")) as urlopen:
            self.assertEqual(client.take(url="https://example.com", format="png"), b"\x89PNG")
        request = urlopen.call_args[0][0]
        query = "format=png&url=https%3A%2F%2Fexample.com"
        self.assertEqual(request.full_url, f"https://api.argoshot.com/take?{query}&signature={sign('SK_test', query)}")
        self.assertEqual(request.get_method(), "GET")
        self.assertEqual(request.get_header("X-access-key"), "AK_test")

    def test_post_json_for_html(self):
        client = Argoshot("AK_test")
        with mock.patch("urllib.request.urlopen", return_value=FakeResponse(b"ok")) as urlopen:
            client.take({"html": "<h1>Hi</h1>", "format": "png", "async": False, "hide_selectors": [".x"]})
        request = urlopen.call_args[0][0]
        self.assertEqual(request.full_url, "https://api.argoshot.com/take")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(request.data), {"html": "<h1>Hi</h1>", "format": "png", "async": False, "hide_selectors": [".x"]})

    def test_error_raises(self):
        client = Argoshot("bad")
        headers = Message()
        err = urllib.error.HTTPError(
            "https://api.argoshot.com/take", 400, "Bad Request", headers,
            io.BytesIO(b'{"is_successful":false,"error_code":"access_key_invalid","error_message":"No such access key."}'),
        )
        with mock.patch("urllib.request.urlopen", side_effect=err):
            with self.assertRaises(ArgoshotError) as caught:
                client.take(url="https://example.com")
        self.assertEqual(caught.exception.code, "access_key_invalid")
        self.assertEqual(caught.exception.status, 400)


@unittest.skipUnless(os.environ.get("ARGOSHOT_KEY"), "set ARGOSHOT_KEY to run the live test")
class LiveTest(unittest.TestCase):
    def test_png(self):
        client = Argoshot(os.environ["ARGOSHOT_KEY"], secret_key=os.environ.get("ARGOSHOT_SECRET"))
        self.assertEqual(client.take(url="https://example.com", format="png")[:4], b"\x89PNG")


if __name__ == "__main__":
    unittest.main()
