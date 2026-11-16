"""medexplain: help patients read their own medical reports and visit transcripts.

Offline by default. The optional Claude explanation sends redacted text only after
the reader previews it and consents (see ``medexplain.ui``).
"""

from .analyze import Analysis, analyze_document
from .detect import DocType, detect_document_type
from .ingest import read_upload
from .redact import redact

__all__ = ["Analysis", "DocType", "analyze_document", "detect_document_type", "read_upload", "redact"]
__version__ = "0.1.0"
