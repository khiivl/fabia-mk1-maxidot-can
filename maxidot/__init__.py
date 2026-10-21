# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 the maxidot-fis contributors

"""maxidot - show your own text on the Škoda Fabia Mk1 MaxiDot display from a CAN adapter, no radio needed."""
from .font import encode
from .link import ROW, FisLink, content_payload
from .slcan import find_adapter

__all__ = ["FisLink", "content_payload", "encode", "find_adapter", "ROW"]
__version__ = "0.1.0"
