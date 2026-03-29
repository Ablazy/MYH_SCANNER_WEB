from __future__ import annotations

from pathlib import Path
from typing import Any

import cv2


class WeChatQRScanner:
    def __init__(self) -> None:
        self._detector: Any | None = None
        self._init_error: str | None = None
        self._model_dir = self._resolve_model_dir()
        self._init_detector()

    def _resolve_model_dir(self) -> Path:
        repo_root = Path(__file__).resolve().parents[3]
        return repo_root / "ScanModel"

    def _init_detector(self) -> None:
        if not hasattr(cv2, "wechat_qrcode"):
            self._init_error = (
                "OpenCV build has no wechat_qrcode module. "
                "Please install opencv-contrib-python."
            )
            return

        model_paths = {
            "detect_prototxt": self._model_dir / "detect.prototxt",
            "detect_caffemodel": self._model_dir / "detect.caffemodel",
            "sr_prototxt": self._model_dir / "sr.prototxt",
            "sr_caffemodel": self._model_dir / "sr.caffemodel",
        }

        missing = [str(path) for path in model_paths.values() if not path.exists()]
        if missing:
            self._init_error = f"ScanModel files missing: {', '.join(missing)}"
            return

        try:
            self._detector = cv2.wechat_qrcode.WeChatQRCode(
                str(model_paths["detect_prototxt"]),
                str(model_paths["detect_caffemodel"]),
                str(model_paths["sr_prototxt"]),
                str(model_paths["sr_caffemodel"]),
            )
            if hasattr(self._detector, "setScaleFactor"):
                self._detector.setScaleFactor(0.4)
        except Exception as exc:  # noqa: BLE001
            self._init_error = f"failed to initialize WeChatQRCode: {exc}"
            self._detector = None

    @property
    def backend_name(self) -> str:
        return "opencv_wechat_qrcode"

    @property
    def model_dir(self) -> str:
        return str(self._model_dir)

    @property
    def is_ready(self) -> bool:
        return self._detector is not None

    @property
    def error_message(self) -> str | None:
        return self._init_error

    def ensure_ready(self) -> None:
        if self._detector is None:
            raise RuntimeError(self._init_error or "WeChatQRCode detector is not ready")

    def decode(self, frame: Any) -> list[str]:
        self.ensure_ready()
        assert self._detector is not None

        result = self._detector.detectAndDecode(frame)
        decoded = result[0] if isinstance(result, tuple) else result

        payloads: list[str] = []
        if isinstance(decoded, str):
            if decoded:
                payloads.append(decoded)
            return payloads

        if isinstance(decoded, (list, tuple)):
            for item in decoded:
                if isinstance(item, str) and item:
                    payloads.append(item)
            return payloads

        return payloads
