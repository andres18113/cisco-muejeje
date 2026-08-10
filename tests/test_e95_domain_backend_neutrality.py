"""El dominio no puede saber que existe Packet Tracer.

Stage 3A3 metio tres perfiles de Packet Tracer dentro de
`domain/enterprise/models/link_performance.py`, cuyo propio docstring decia que
ahi no hay nombres de modelo ni strings de IOS. El perfil serial de Stage 3A2
llevaba mas tiempo alli por el mismo descuido.

Estos tests recorren el arbol de sintaxis en vez de confiar en una lectura: una
frontera que solo se comprueba a ojo se vuelve a cruzar.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
DOMAIN = REPO / "src" / "packet_tracer_mcp" / "domain"
LINK_PERFORMANCE = DOMAIN / "enterprise" / "models" / "link_performance.py"
PLANNER = DOMAIN / "enterprise" / "services" / "link_performance_planner.py"
INTEGRATION = DOMAIN / "enterprise" / "services" / "link_performance_integration.py"

LINK_POLICY_MODULES = (LINK_PERFORMANCE, PLANNER, INTEGRATION)

# Marcas de un backend concreto. No se buscan subcadenas sueltas: `2911` como
# numero suelto aparece en cualquier sitio, asi que se comparan literales.
BACKEND_MODEL_LITERALS = frozenset({
    "2911", "3560-24PS", "3650-24PS", "2960-24TT", "PC-PT", "HWIC-2T",
})
BACKEND_VERSION_LITERALS = frozenset({"9.0.1.0858", "8.2.0", "9.0.1"})
FORBIDDEN_IMPORT_TOKENS = ("infrastructure", "adapters", "catalog", "ios", "bridge")

# Comandos de IOS: viven en el renderer/trusted boundary, no en la politica.
IOS_COMMAND_LITERALS = frozenset({
    "speed 10", "speed 100", "speed 1000", "speed auto",
    "duplex full", "duplex half", "duplex auto",
    "show interfaces", "clock rate", "no shutdown", "configure terminal",
})


def _string_literals(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.value for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def _imported_modules(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.append("." * (node.level or 0) + (node.module or ""))
    return modules


def _domain_modules() -> list[pathlib.Path]:
    return sorted(DOMAIN.rglob("*.py"))


PACKAGE_ROOT = REPO / "src" / "packet_tracer_mcp"


def _resolved_import_targets(path: pathlib.Path) -> list[tuple[str, pathlib.Path | None]]:
    """Resuelve cada import relativo a una ruta real del paquete.

    Buscar la subcadena "execution" daba falsos positivos: el propio dominio
    tiene un `models/execution.py`, que no es la capa de ejecucion.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    targets: list[tuple[str, pathlib.Path | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            targets.extend((alias.name, None) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            name = "." * (node.level or 0) + (node.module or "")
            if not node.level:
                targets.append((name, None))
                continue
            base = path.parent
            for _ in range(node.level - 1):
                base = base.parent
            resolved = base.joinpath(*(node.module or "").split(".")) if node.module else base
            targets.append((name, resolved))
    return targets


def _escapes_the_domain(path: pathlib.Path) -> list[str]:
    offenders: list[str] = []
    for name, resolved in _resolved_import_targets(path):
        if resolved is not None:
            try:
                resolved.relative_to(DOMAIN)
            except ValueError:
                offenders.append(f"{name} -> {resolved.relative_to(PACKAGE_ROOT.parent).as_posix()}")
            continue
        if any(token in name.casefold() for token in ("infrastructure", "adapters")):
            offenders.append(name)
    return offenders


class TestLinkPolicyCarriesNoBackendKnowledge:
    @pytest.mark.parametrize("path", LINK_POLICY_MODULES, ids=lambda p: p.name)
    def test_no_device_model_appears_as_a_literal(self, path):
        found = BACKEND_MODEL_LITERALS.intersection(_string_literals(path))

        assert not found, f"{path.name} names backend hardware: {sorted(found)}"

    @pytest.mark.parametrize("path", LINK_POLICY_MODULES, ids=lambda p: p.name)
    def test_no_backend_version_appears_as_a_literal(self, path):
        found = BACKEND_VERSION_LITERALS.intersection(_string_literals(path))

        assert not found, f"{path.name} pins a backend version: {sorted(found)}"

    @pytest.mark.parametrize("path", LINK_POLICY_MODULES, ids=lambda p: p.name)
    def test_no_ios_command_is_built_here(self, path):
        found = IOS_COMMAND_LITERALS.intersection(_string_literals(path))

        assert not found, f"{path.name} builds IOS commands: {sorted(found)}"

    @pytest.mark.parametrize("path", LINK_POLICY_MODULES, ids=lambda p: p.name)
    def test_nothing_outside_the_domain_is_imported(self, path):
        offenders = _escapes_the_domain(path)

        assert not offenders, f"{path.name} imports outside the domain: {offenders}"


class TestTheWholeDomainStaysNeutral:
    def test_no_domain_module_pins_a_packet_tracer_version(self):
        offenders = [
            path.relative_to(REPO).as_posix()
            for path in _domain_modules()
            if BACKEND_VERSION_LITERALS.intersection(_string_literals(path))
        ]

        assert offenders == [], f"Domain modules pinning a backend version: {offenders}"

    def test_the_link_policy_never_reaches_the_runtime(self):
        """Acotado a la politica de enlace: el resto del dominio arrastra deuda previa."""
        offenders = {
            path.name: _escapes_the_domain(path)
            for path in LINK_POLICY_MODULES
            if _escapes_the_domain(path)
        }

        assert offenders == {}, f"Link policy reaching outside the domain: {offenders}"

    def test_the_pre_existing_catalog_coupling_did_not_grow(self):
        """Deuda heredada, medida en vez de ignorada: no debe aumentar.

        Siete modulos del dominio ya importaban el catalogo antes de E9.5, tres
        de ellos desde dentro de una funcion, que es por lo que una busqueda de
        imports de nivel superior los pasaba por alto. No se corrigen aqui
        -- estan fuera de esta etapa -- pero la lista queda fijada para que
        ninguno nuevo se sume sin que salte.
        """
        coupled = sorted(
            path.relative_to(DOMAIN).as_posix()
            for path in _domain_modules()
            if any("catalog" in name.casefold() for name, _ in _resolved_import_targets(path))
        )

        assert coupled == [
            "rules/cable_rules.py",
            "rules/device_rules.py",
            "rules/nat_rules.py",
            "rules/switch_security_rules.py",
            "rules/vlan_rules.py",
            "services/auto_fixer.py",
            "services/orchestrator.py",
        ], f"Domain modules coupled to the catalog: {coupled}"


class TestTheProfilesLiveInInfrastructure:
    def test_the_ethernet_profiles_resolve_from_the_catalog(self):
        from src.packet_tracer_mcp.infrastructure.catalog.link_mode_capabilities import (
            PT_2911_GIGABIT_LINK_MODE,
            PT_3560_FASTETHERNET_LINK_MODE,
            PT_3560_GIGABIT_LINK_MODE,
        )

        for profile in (PT_2911_GIGABIT_LINK_MODE, PT_3560_FASTETHERNET_LINK_MODE,
                        PT_3560_GIGABIT_LINK_MODE):
            assert profile.backend_version == "9.0.1.0858"
            assert profile.device_model

    def test_the_serial_profile_moved_out_of_the_domain_too(self):
        """Mismo descuido, otra etapa: tambien vivia en el dominio."""
        from src.packet_tracer_mcp.domain.enterprise.models import link_performance
        from src.packet_tracer_mcp.infrastructure.catalog.link_mode_capabilities import (
            PT_2911_HWIC2T_SERIAL_CLOCK,
        )

        assert PT_2911_HWIC2T_SERIAL_CLOCK.device_model == "2911"
        assert not hasattr(link_performance, "PT_2911_HWIC2T_SERIAL_CLOCK")

    def test_the_domain_still_exposes_the_generic_capability_type(self):
        from src.packet_tracer_mcp.domain.enterprise.models.link_performance import (
            EthernetLinkModeCapability,
        )

        assert EthernetLinkModeCapability().device_model == ""
