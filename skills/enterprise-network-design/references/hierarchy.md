# Hierarchy reference

Canonical order:

site -> building -> floor -> zone -> network role -> segment -> endpoint group.

Keep identity stable across plans. A site can contain multiple buildings and floors; a zone is a logical placement boundary, not automatically a VLAN. Record the reason for every aggregation or split.

Infrastructure roles include WAN edge, core, distribution, access, services and management. Endpoints remain grouped until hardware planning requires concrete counts.
