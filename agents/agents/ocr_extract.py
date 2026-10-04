"""OCR provider boundary.

Never return fixture data as if it came from a user's uploaded document. A real
provider adapter must be configured before extraction is enabled.
"""


class OCRProviderUnavailable(RuntimeError):
    pass


def ocr_document_agent(*_args, **_kwargs):
    raise OCRProviderUnavailable(
        "Document extraction is unavailable because no OCR provider adapter is configured."
    )
