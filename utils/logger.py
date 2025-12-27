"""
로깅 유틸리티
=====================================
프로젝트 전역 로깅 설정
"""

import logging
import sys
from typing import Optional

# 로거 저장소
_loggers = {}


def setup_logger(
    name: str = "instagram_marketing",
    level: int = logging.INFO,
    log_file: Optional[str] = None,
) -> logging.Logger:
    """
    로거 설정 및 반환

    Args:
        name: 로거 이름
        level: 로그 레벨
        log_file: 파일 출력 경로 (선택)

    Returns:
        설정된 Logger 인스턴스
    """

    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 포맷 설정
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 파일 핸들러 (선택)
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _loggers[name] = logger
    return logger


def get_logger(name: str = "instagram_marketing") -> logging.Logger:
    """기존 로거 반환 또는 새로 생성"""

    if name in _loggers:
        return _loggers[name]

    return setup_logger(name)
