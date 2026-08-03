"""Asignación pura y estable de extensiones E7."""

from __future__ import annotations

import re

from ..models.voice_plan import ExtensionRange


_NATURAL_PART = re.compile(r"(\d+)")


def natural_identity_key(value: str) -> tuple[tuple[int, object], ...]:
    """Orden semántico estable: phone-2 precede a phone-10."""
    return tuple(
        (1, int(part)) if part.isdigit() else (0, part.casefold())
        for part in _NATURAL_PART.split(value)
        if part
    )


class ExtensionAllocationError(ValueError):
    def __init__(self, code: str, message: str, subject: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.subject = subject


class ExtensionAllocator:
    """No conoce Packet Tracer; asigna sólo identidades telefónicas actuales."""

    def allocate(
        self,
        phone_ids_by_site: dict[str, list[str]],
        ranges: dict[str, ExtensionRange],
        explicit_extensions: dict[str, str],
    ) -> dict[str, str]:
        known_phones = {
            phone_id for phone_ids in phone_ids_by_site.values() for phone_id in phone_ids
        }
        unknown = sorted(set(explicit_extensions) - known_phones, key=natural_identity_key)
        if unknown:
            raise ExtensionAllocationError(
                "PHONE_ENDPOINT_MISSING",
                "Explicit extensions reference unknown phone endpoints: " + ", ".join(unknown),
                unknown[0],
            )

        allocated: dict[str, str] = {}
        owners: dict[str, str] = {}
        for site_id in sorted(phone_ids_by_site, key=natural_identity_key):
            extension_range = ranges[site_id]
            self._validate_range(site_id, extension_range)
            reserved = set(extension_range.reserved)
            for phone_id in sorted(phone_ids_by_site[site_id], key=natural_identity_key):
                explicit = explicit_extensions.get(phone_id)
                if explicit is None:
                    continue
                if not explicit.isascii() or not explicit.isdigit():
                    raise ExtensionAllocationError(
                        "EXTENSION_INVALID",
                        f"Extension {explicit!r} for {phone_id} must contain ASCII digits only.",
                        phone_id,
                    )
                numeric = int(explicit)
                if not extension_range.start <= numeric <= extension_range.end or numeric in reserved:
                    raise ExtensionAllocationError(
                        "EXTENSION_INVALID",
                        f"Extension {explicit} for {phone_id} is outside its allowed range.",
                        phone_id,
                    )
                if explicit in owners:
                    raise ExtensionAllocationError(
                        "EXTENSION_COLLISION",
                        f"Extension {explicit} is assigned to both {owners[explicit]} and {phone_id}.",
                        explicit,
                    )
                allocated[phone_id] = explicit
                owners[explicit] = phone_id

        for site_id in sorted(phone_ids_by_site, key=natural_identity_key):
            extension_range = ranges[site_id]
            available = (
                str(number)
                for number in range(extension_range.start, extension_range.end + 1)
                if number not in set(extension_range.reserved) and str(number) not in owners
            )
            for phone_id in sorted(phone_ids_by_site[site_id], key=natural_identity_key):
                if phone_id in allocated:
                    continue
                try:
                    extension = next(available)
                except StopIteration as exc:
                    raise ExtensionAllocationError(
                        "EXTENSION_RANGE_EXHAUSTED",
                        f"Extension range for site {site_id!r} cannot fit all current phones.",
                        site_id,
                    ) from exc
                allocated[phone_id] = extension
                owners[extension] = phone_id
        return allocated

    @staticmethod
    def _validate_range(site_id: str, extension_range: ExtensionRange) -> None:
        if (
            extension_range.start < 1
            or extension_range.end < extension_range.start
            or len(str(extension_range.start)) != len(str(extension_range.end))
            or any(
                value < extension_range.start or value > extension_range.end
                for value in extension_range.reserved
            )
        ):
            raise ExtensionAllocationError(
                "EXTENSION_RANGE_INVALID",
                f"Extension range for site {site_id!r} is invalid.",
                site_id,
            )
