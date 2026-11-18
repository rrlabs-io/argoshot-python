# argoshot

The official Python client for [Argoshot](https://argoshot.com), the screenshot API: screenshots, PDFs and signed
`og:image` URLs of any web page or HTML. **Free to start.** Docs: https://argoshot.com/docs

Standard library only (no dependencies), Python 3.8+, typed.

## Install

```sh
pip install argoshot
```

Get your access key (and secret key, for signed URLs) from the dashboard's API keys page.

## Screenshot to a file

```python
import os
from argoshot import Argoshot

client = Argoshot(os.environ["ARGOSHOT_ACCESS_KEY"])

png = client.take(url="https://example.com", format="png", full_page=True, block_cookie_banners=True)
with open("example.png", "wb") as f:
    f.write(png)
```

## Signed og:image URL

`url()` builds a `GET /take` link for `<img src>` or `<meta property="og:image">`. With a secret key it is signed
(HMAC-SHA256 of the query string), so nobody can change its options. Set the key to **signed requests only** in the
dashboard before you put its links in public pages.

```python
client = Argoshot(os.environ["ARGOSHOT_ACCESS_KEY"], secret_key=os.environ["ARGOSHOT_SECRET_KEY"])

og_image = client.url(
    url="https://example.com/blog/my-post",
    viewport_width=1200,
    viewport_height=630,
    format="png",
    cache=True,
    cache_ttl=86400,
)
# <meta property="og:image" content="{{ og_image }}">
```

## HTML to PNG

When `html` (or `markdown`) is given, `take()` sends a JSON `POST` instead of a long query string.

```python
card = client.take(
    html='<div style="font: 64px system-ui; padding: 80px">Hello from Argoshot</div>',
    format="png",
    viewport_width=1200,
    viewport_height=630,
)
with open("card.png", "wb") as f:
    f.write(card)
```

## Options

Options are the API's own names (https://argoshot.com/docs/options), as keyword arguments or a dict; lists are lists:
`hide_selectors=[".banner", "#chat"]`. Pass names that are Python keywords in the dict:
`client.take({"url": "https://example.com", "async": True, "webhook_url": "https://you.example/hook"})`.
`argoshot.TakeOptions` types the common ones.

## Errors

A failed request raises `ArgoshotError` with the API's `code` (e.g. `selector_not_found`, `screenshots_limit_reached`),
`message`, HTTP `status`, `documentation_url`, and `upgrade_url` / `retry_after` when the API gives them.
All codes: https://argoshot.com/docs/errors

```python
from argoshot import ArgoshotError

try:
    client.take(url="https://example.com", selector="#missing", error_on_selector_not_found=True)
except ArgoshotError as e:
    print(e.code, e.message)
```

## Usage

```python
print(client.usage())  # {"total": ..., "available": ..., "used": ..., ...}
```

## Configuration

```python
Argoshot(access_key, secret_key=None, base_url="https://api.argoshot.com", timeout=120.0)
```

Note: a key set to *signed requests only* cannot send JSON `POST` requests (the API refuses them), so
`take(html=...)` needs a key that permits unsigned requests.

## Licence

MIT
