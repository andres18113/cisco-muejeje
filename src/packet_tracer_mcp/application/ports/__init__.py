"""Puertos backend-neutral para capacidades que requieren adaptadores externos."""

from .phone_control import PhoneControlPort
from .voice_call_operation import VoiceCallOperationPort

__all__ = ["PhoneControlPort", "VoiceCallOperationPort"]
