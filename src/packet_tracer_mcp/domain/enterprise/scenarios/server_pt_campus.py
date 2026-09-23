"""Parameterized Server-PT campus intent for governed HTTP-by-IP commissioning."""

from __future__ import annotations

import re

from ..models.intent import EnterpriseIntent

_MARKER = re.compile(r"COLD_HTTP_[0-9a-f]{32}\Z")


def server_pt_campus_intent(
    clients: int,
    marker: str,
    *,
    sites: int = 1,
) -> EnterpriseIntent:
    """Build the established static campus recipe with an attempt marker.

    `sites` partitions large offline scale cases. The governed LIVE profile
    chooses one site and 30 clients. Invalid counts or markers raise
    ``ValueError`` before any plan is compiled or effect is possible.
    """
    if isinstance(clients, bool) or not 1 <= clients <= 1000:
        raise ValueError("client count must be between 1 and 1000")
    if isinstance(sites, bool) or not 1 <= sites <= clients:
        raise ValueError("site count must be between 1 and client count")
    if _MARKER.fullmatch(marker) is None:
        raise ValueError("marker must name one 32-hex acceptance attempt")

    shares = [
        clients // sites + (1 if index < clients % sites else 0)
        for index in range(sites)
    ]
    built_sites = []
    for index, share in enumerate(shares):
        site_name = "HQ" if index == 0 else f"BR{index:02d}"
        web_name = "lab-web" if index == 0 else f"lab-web-{index:02d}"
        host = "www.lab.example" if index == 0 else f"www{index}.lab.example"
        built_sites.append(
            {
                "name": site_name,
                "type": "hq" if index == 0 else "branch",
                "endpoints": [
                    {
                        "role": "user_pc",
                        "count": share,
                        "addressing_preference": "static",
                    },
                    {
                        "role": "server",
                        "count": 1,
                        "addressing_preference": "static",
                        "segment_role": "data",
                    },
                ],
                "services": [
                    {
                        "name": web_name,
                        "service_type": "http",
                        "hostname": host,
                        "http_content": marker,
                    },
                ],
            }
        )
    return EnterpriseIntent.model_validate(
        {
            "name": "SAMPLE-LAB",
            "address_space": (
                "10.0.0.0/16" if sites > 1 or clients > 400 else "198.18.160.0/20"
            ),
            "sites": built_sites,
        }
    )
