# -*- coding: utf-8 -*-
import logging
import sys

_LOGGER_INITIALIZED = False


def _get_utf8_stdout():
    """安全获取 UTF-8 行缓冲的 stdout，不创建会在 GC 时误关底层句柄的临时 TextIOWrapper"""
    stream = sys.stdout
    if stream is not None and hasattr(stream, "reconfigure"):
        try:
            stream.reconfigure(encoding="utf-8", line_buffering=True)
        except Exception:
            pass
    return stream


def setup_logger(log_file_path="mzzb_score.log"):
    """
    配置并返回日志记录器（幂等安全，不会在重复调用时截断日志或关闭标准输出句柄）
    """
    global _LOGGER_INITIALIZED
    root_logger = logging.getLogger()

    if not _LOGGER_INITIALIZED:
        console_handler = logging.StreamHandler(_get_utf8_stdout())
        file_handler = logging.FileHandler(log_file_path, mode="w", encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        console_handler.setFormatter(formatter)
        file_handler.setFormatter(formatter)

        root_logger.setLevel(logging.INFO)
        root_logger.addHandler(file_handler)
        root_logger.addHandler(console_handler)
        _LOGGER_INITIALIZED = True

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)

    return root_logger


def setup_interactive_logger():
    """
    设置交互式 logger，用于用户交互场景（如 Twitter 配置）
    """
    interactive_logger = logging.getLogger("interactive")
    interactive_logger.setLevel(logging.INFO)

    if interactive_logger.handlers:
        return interactive_logger

    console_handler = logging.StreamHandler(_get_utf8_stdout())
    console_formatter = logging.Formatter("%(message)s")
    console_handler.setFormatter(console_formatter)

    file_handler = logging.FileHandler("mzzb_score.log", mode="a", encoding="utf-8")
    file_formatter = logging.Formatter("%(asctime)s - INTERACTIVE - %(message)s")
    file_handler.setFormatter(file_formatter)

    interactive_logger.addHandler(console_handler)
    interactive_logger.addHandler(file_handler)
    interactive_logger.propagate = False

    return interactive_logger


# 全局日期错误列表
date_error = []
