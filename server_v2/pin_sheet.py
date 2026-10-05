"""POST /api/v2/mobile/pin-sheet: read a photographed daily hole-location sheet.

The server only reads the sheet (the configured multimodal model, normally Gemini). Placing each
flag on the green is the app's job: it owns the same green outline and play axis its 前/后/左/右
edge readout uses, so the readout reproduces the sheet's numbers.
"""

from __future__ import annotations

import base64
import binascii
import logging

from fastapi import HTTPException

from ai_caddie.core.media import MediaUploadTooLarge, sniff_media_mime_type, validate_media_upload_constraints
from ai_caddie.llm.llm_providers import ProviderConfigurationError, redact_secret_text
from ai_caddie.llm.pin_sheet_vision import PinSheetImage, PinSheetReadError, read_pin_sheet

from .media import build_media_vision_provider
from .models import PinSheetRequest

ACCEPTED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}

logger = logging.getLogger(__name__)


def read_pin_sheet_response(request: PinSheetRequest) -> dict:
    images: list[PinSheetImage] = []
    for item in request.images:
        try:
            data = base64.b64decode(item.contentBase64, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(status_code=400, detail="image is not valid base64")
        sniffed = sniff_media_mime_type(data[:32])
        if sniffed not in ACCEPTED_IMAGE_TYPES:
            raise HTTPException(status_code=415, detail="the sheet photo must be JPEG, PNG or WebP")
        try:
            validate_media_upload_constraints(
                "photo", content_byte_size=len(data), mime_type=sniffed, content_sample=data[:32]
            )
        except MediaUploadTooLarge as exc:
            raise HTTPException(status_code=413, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        images.append(PinSheetImage(mime_type=sniffed, data=data))
    total_bytes = sum(len(image.data) for image in images)
    try:
        provider = build_media_vision_provider()
        result = read_pin_sheet(images, provider)
    except ProviderConfigurationError as exc:
        logger.warning("pin_sheet not_configured images=%s bytes=%s error=%s", len(images), total_bytes, redact_secret_text(exc))
        raise HTTPException(status_code=503, detail=f"pin sheet reading is not configured: {redact_secret_text(exc)}")
    except PinSheetReadError as exc:
        logger.warning("pin_sheet unreadable images=%s bytes=%s error=%s", len(images), total_bytes, exc)
        raise HTTPException(status_code=422, detail=f"could not read the sheet: {exc}")
    except Exception as exc:  # provider transport / runtime failure
        logger.warning(
            "pin_sheet provider_failed images=%s bytes=%s error=%s: %s",
            len(images), total_bytes, type(exc).__name__, redact_secret_text(exc),
        )
        raise HTTPException(status_code=502, detail=f"pin sheet reading failed: {redact_secret_text(exc)}")
    logger.info(
        "pin_sheet read images=%s bytes=%s holes=%s dated=%s",
        len(images), total_bytes, len(result.get("holes") or []), bool(result.get("date")),
    )
    return result
