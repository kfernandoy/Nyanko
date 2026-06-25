_detection_paused = False


def set_detection_paused(paused: bool) -> None:
    global _detection_paused
    _detection_paused = paused


def is_detection_paused() -> bool:
    return _detection_paused
