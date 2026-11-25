"""Plain HTTP GET for the platforms without an official API openlive can use (Kick, YouTube)."""
import json
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import __version__

UA = f"openlive/{__version__}"


class NetError(Exception):
    def __init__(self, msg, status=0):
        super().__init__(msg)
        self.status = status


def fetch(url, headers=None, timeout=15):
    """GET → (text, final_url)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace"), r.geturl()
    except urllib.error.HTTPError as e:
        raise NetError(f"HTTP {e.code}", e.code) from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise NetError(f"network: {getattr(e, 'reason', e)}") from None


def fetch_json(url, headers=None, timeout=15):
    text, _ = fetch(url, {"Accept": "application/json", **(headers or {})}, timeout)
    try:
        return json.loads(text)
    except ValueError:
        raise NetError("bad JSON") from None


def parallel(fn, items, workers=8):
    """[(item, result_or_exception)] in input order."""
    def run(it):
        try:
            return it, fn(it)
        except Exception as e:  # one broken channel never stops the rest
            return it, e
    with ThreadPoolExecutor(max_workers=workers) as ex:
        return list(ex.map(run, items))
