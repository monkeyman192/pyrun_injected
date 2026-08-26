from __future__ import annotations


class InjectionError(Exception):
    """Generic exception raised when there is an excpetion in the injected code.
    This will not subclass from the actual exception raised in any way since it may be a custom exception type
    which we won't have knowledge of here."""

    pre_message = "An unknown exception ocurred: 0x{value:X}"

    def __init__(self, message: str | None, value: str | int | None):
        if message is None:
            message = ""
        super().__init__(message)
        self.message = message
        self.value = value

    def __str__(self):
        if self.message:
            return self.pre_message.format(value=self.value) + "\n" + self.message
        else:
            return self.pre_message.format(value=self.value)


class FileInjectionError(InjectionError):
    pre_message = "There was an exception running the file {value}:"


class StringInjectionError(InjectionError):
    pre_message = "The string provided at index {value} had the following exception:"
