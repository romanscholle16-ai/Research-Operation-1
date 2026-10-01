from __future__ import annotations

from app.research.limits import RetrievalLimits

SAMPLE_HTML = b"""<html><head><title>Sample Strategy</title><style>.x{color:red}</style></head>
<body>
<script>alert('should not appear in extracted text')</script>
<p>This strategy enters a long position when price confirms a breakout above resistance.</p>
<p>The stop loss is placed at 2 percent below the entry price.</p>
<p>Take profit is set at 4 percent above the entry price.</p>
<p>Recommended timeframe is 1h with no specific session filter.</p>
</body></html>"""


def make_fake_transport(response_map: dict[str, tuple]):
    """response_map: url -> (status, headers, body, final_url) OR an exception instance to raise."""

    def transport(url: str, user_agent: str, limits: RetrievalLimits):
        if url not in response_map:
            raise KeyError(f"no fake response configured for {url}")
        result = response_map[url]
        if isinstance(result, BaseException):
            raise result
        return result

    return transport


def allow_all_robots_transport_wrapping(inner):
    """Wrap a transport so any robots.txt URL raises (treated as 'allow all' by HttpSourceRetriever)."""

    def transport(url: str, user_agent: str, limits: RetrievalLimits):
        if url.endswith("/robots.txt"):
            raise OSError("no robots.txt in this fixture")
        return inner(url, user_agent, limits)

    return transport
