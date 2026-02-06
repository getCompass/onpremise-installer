#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Модуль для цветного вывода в консоль.
"""

import sys


class Colors:
    """Класс для управления цветами в терминале."""
    
    # ANSI коды цветов
    RESET = '\033[0m'
    BOLD = '\033[1m'
    
    # Основные цвета
    BLACK = '\033[30m'
    RED = '\033[31m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    CYAN = '\033[36m'
    WHITE = '\033[37m'
    
    # Яркие цвета
    BRIGHT_BLACK = '\033[90m'
    BRIGHT_RED = '\033[91m'
    BRIGHT_GREEN = '\033[92m'
    BRIGHT_YELLOW = '\033[93m'
    BRIGHT_BLUE = '\033[94m'
    BRIGHT_MAGENTA = '\033[95m'
    BRIGHT_CYAN = '\033[96m'
    BRIGHT_WHITE = '\033[97m'
    
    @staticmethod
    def is_tty() -> bool:
        """Проверяет, является ли вывод терминалом."""
        return sys.stdout.isatty()
    
    @staticmethod
    def colorize(text: str, color: str, bold: bool = False) -> str:
        """
        Добавляет цвет к тексту.
        
        Args:
            text: Текст для окрашивания
            color: ANSI код цвета
            bold: Делать текст жирным
        
        Returns:
            str: Окрашенный текст или оригинальный, если не терминал
        """
        if not Colors.is_tty():
            return text
        
        result = text
        if bold:
            result = Colors.BOLD + result
        result = color + result + Colors.RESET
        return result
    
    @staticmethod
    def info(text: str) -> str:
        """Информационное сообщение (синий)."""
        return Colors.colorize(text, Colors.CYAN)
    
    @staticmethod
    def success(text: str) -> str:
        """Успешное сообщение (зеленый)."""
        return Colors.colorize(text, Colors.GREEN, bold=True)
    
    @staticmethod
    def warning(text: str) -> str:
        """Предупреждение (желтый)."""
        return Colors.colorize(text, Colors.YELLOW)
    
    @staticmethod
    def error(text: str) -> str:
        """Ошибка (красный)."""
        return Colors.colorize(text, Colors.RED, bold=True)
    
    @staticmethod
    def step(text: str) -> str:
        """Шаг процесса (циан)."""
        return Colors.colorize(text, Colors.CYAN, bold=True)
    
    @staticmethod
    def highlight(text: str) -> str:
        """Выделение текста (яркий белый)."""
        return Colors.colorize(text, Colors.BRIGHT_WHITE, bold=True)


def print_info(text: str) -> None:
    """Выводит информационное сообщение."""
    print(Colors.info(f"[INFO] {text}"))


def print_success(text: str) -> None:
    """Выводит сообщение об успехе."""
    print(Colors.success(f"[SUCCESS] {text}"))


def print_warning(text: str) -> None:
    """Выводит предупреждение."""
    print(Colors.warning(f"[WARN] {text}"))


def print_error(text: str) -> None:
    """Выводит ошибку."""
    print(Colors.error(f"[ERROR] {text}"))


def print_step(text: str) -> None:
    """Выводит шаг процесса."""
    print(Colors.step(text))


def print_highlight(text: str) -> None:
    """Выводит выделенный текст."""
    print(Colors.highlight(text))

