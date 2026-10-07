class ScrapeError(RuntimeError):
    """Base error for controlled acquisition failures."""


class SourceBlockedError(ScrapeError):
    """The public source explicitly blocked the request (403/CAPTCHA/robots)."""


class SourceUnavailableError(ScrapeError):
    """The source could not be reached within the configured policy."""


class SourceChangedError(ScrapeError):
    """The source loaded, but the adapter readiness contract no longer matched."""
