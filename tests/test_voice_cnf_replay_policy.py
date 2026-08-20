"""Lo que la reproducción controlada de `create cnf-files` obliga a corregir.

`TD-VOICE-001` clasificaba el replay de `create cnf-files` como UNKNOWN sobre
base UNMEASURED, con `INDEPENDENT_READBACK` entre sus contenciones y la acción
declarando `OperationSemantics.REPLACE`. La reproducción controlada sobre PT
`9.0.1.0858` / `2811` midió las tres cosas y ninguna sobrevivió intacta:

```text
show telephony-service      % Invalid input detected  -- no existe en esta imagen
show ephone                 válido y VACÍO
getProcess(...)             9 candidatos, sólo `VlanManager` responde
device members              146 enumerados, ninguno de telefonía
ambas pasadas               salida idéntica en todo observable
```

De ahí salen tres correcciones, y cada una es una afirmación que se retira:

1. la base ya no es UNMEASURED -- se midió, y lo que se estableció es que este
   backend no publica observador;
2. `INDEPENDENT_READBACK` era **falso**: no hay relectura independiente que
   pueda existir. Declarar una contención que no existe es peor que no tener
   ninguna;
3. `REPLACE` afirma que reaplicar sustituye el estado anterior, y eso es
   exactamente lo que nadie pudo observar. `EXECUTE_ONCE` es lo que la
   evidencia sostiene.
"""

from __future__ import annotations

from src.packet_tracer_mcp.domain.enterprise.models.execution import OperationSemantics
from src.packet_tracer_mcp.domain.enterprise.models.voice_plan import (
    GeneratePhoneConfigurationFiles,
    VoiceCapabilityDimension,
    VoicePhase,
)
from src.packet_tracer_mcp.domain.enterprise.mutation_replay import (
    EvidenceBasis,
    ReplayClassification,
    ReplayContainment,
    policy_for_action_type,
)


def _action() -> GeneratePhoneConfigurationFiles:
    return GeneratePhoneConfigurationFiles(
        id="cnf", phase=VoicePhase.PHONE_BOOTSTRAP,
        call_control_id="cc", host_device_id="d", host_device_name="R",
        host_model="2811", site_id="s",
        required_capability=VoiceCapabilityDimension.TFTP_PHONE_BOOTSTRAP,
    )


def _policy():
    return policy_for_action_type(GeneratePhoneConfigurationFiles)


def test_the_declared_semantics_no_longer_assert_more_than_was_measured():
    """`REPLACE` afirmaba una sustitución que nadie observó."""
    assert _action().operation is OperationSemantics.EXECUTE_ONCE


def test_the_basis_records_that_a_controlled_repeat_actually_happened():
    policy = _policy()

    assert policy.basis is not EvidenceBasis.UNMEASURED
    assert policy.basis is EvidenceBasis.MEASURED_CONTROLLED_REPEAT_UNOBSERVABLE


def test_the_product_treats_it_as_unsafe_rather_than_merely_unknown():
    """Medir y no poder observar no es lo mismo que no haber mirado."""
    policy = _policy()

    assert policy.classification is ReplayClassification.TREAT_AS_REPLAY_UNSAFE


def test_the_independent_readback_containment_is_withdrawn():
    """No existe relectura independiente; declararla sería inventar un control."""
    policy = _policy()

    assert ReplayContainment.INDEPENDENT_READBACK not in policy.containment


def test_the_containments_that_do_exist_are_kept():
    policy = _policy()

    assert ReplayContainment.CAPABILITY_GATE in policy.containment
    assert ReplayContainment.NO_BLIND_RETRY in policy.containment


def test_it_is_never_classified_safe_on_a_containment_that_cannot_carry_it():
    policy = _policy()

    assert policy.classification is not ReplayClassification.REPLAY_SAFE


def test_the_evidence_names_the_backend_it_was_measured_on():
    policy = _policy()

    assert "9.0.1.0858" in policy.evidence
    assert "2811" in policy.evidence
