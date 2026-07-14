from __future__ import annotations

import unittest

from orbitops.session import (
    CONTRACT_SEMANTICS,
    LANE_PRECEDENCE,
    CorrelationBasis,
    CorrelationDecision,
    CorrelationKind,
    EvidenceLane,
    SourceCompleteness,
    classify_source_completeness,
    classify_telemetry_alarm_match,
    correlation_rule,
    presentation_key,
)


class SessionCorrelationSemanticsTests(unittest.TestCase):
    def test_contract_matrix_covers_every_evidence_lane(self) -> None:
        self.assertEqual(set(CONTRACT_SEMANTICS), set(EvidenceLane))

        telemetry = CONTRACT_SEMANTICS[EvidenceLane.TELEMETRY]
        self.assertEqual(telemetry.readable_schema_versions, (1,))
        self.assertEqual(telemetry.packet_reference_field, "decoded_packet.sequence")
        self.assertIsNone(telemetry.session_identity_field)
        self.assertIsNone(telemetry.completion_marker)

        alarm = CONTRACT_SEMANTICS[EvidenceLane.ALARM]
        self.assertEqual(alarm.packet_reference_field, "packet_sequence")
        self.assertEqual(alarm.session_identity_field, "session_id")
        self.assertEqual(alarm.completion_marker, "run_summary")

        link = CONTRACT_SEMANTICS[EvidenceLane.LINK]
        self.assertEqual(link.readable_schema_versions, (1, 2))
        self.assertEqual(link.packet_reference_field, "packet_index")
        self.assertEqual(link.session_identity_field, "session_id")

    def test_telemetry_alarm_rule_is_conditional_and_has_no_shared_clock(self) -> None:
        rule = correlation_rule(EvidenceLane.TELEMETRY, EvidenceLane.ALARM)
        reverse = correlation_rule(EvidenceLane.ALARM, EvidenceLane.TELEMETRY)

        self.assertEqual(rule, reverse)
        self.assertEqual(rule.basis, CorrelationBasis.PACKET_SEQUENCE)
        self.assertEqual(
            rule.possible_kinds,
            (
                CorrelationKind.EXACT,
                CorrelationKind.AMBIGUOUS,
                CorrelationKind.IMPOSSIBLE,
            ),
        )
        self.assertFalse(rule.shared_clock)

    def test_link_cross_lane_rules_never_infer_packet_equivalence(self) -> None:
        for other_lane in (EvidenceLane.TELEMETRY, EvidenceLane.ALARM):
            with self.subTest(other_lane=other_lane):
                rule = correlation_rule(EvidenceLane.LINK, other_lane)
                self.assertEqual(rule.possible_kinds, (CorrelationKind.SEPARATE_LANE,))
                self.assertEqual(rule.basis, CorrelationBasis.NONE)
                self.assertFalse(rule.shared_clock)

    def test_same_lane_rule_preserves_source_order_only(self) -> None:
        for lane in EvidenceLane:
            with self.subTest(lane=lane):
                rule = correlation_rule(lane, lane)
                self.assertEqual(rule.possible_kinds, (CorrelationKind.ORDERED_ONLY,))
                self.assertEqual(rule.basis, CorrelationBasis.SOURCE_ORDER)

    def test_complete_interrupted_and_empty_source_states_are_explicit(self) -> None:
        self.assertEqual(
            classify_source_completeness(
                EvidenceLane.LINK,
                2,
                summary_present=True,
            ),
            SourceCompleteness.COMPLETE,
        )
        self.assertEqual(
            classify_source_completeness(EvidenceLane.ALARM, 1),
            SourceCompleteness.INCOMPLETE,
        )
        self.assertEqual(
            classify_source_completeness(EvidenceLane.TELEMETRY, 1),
            SourceCompleteness.UNKNOWN,
        )
        self.assertEqual(
            classify_source_completeness(EvidenceLane.TELEMETRY, 0),
            SourceCompleteness.INCOMPLETE,
        )
        with self.assertRaises(ValueError):
            classify_source_completeness(
                EvidenceLane.TELEMETRY,
                1,
                summary_present=True,
            )
        with self.assertRaises(ValueError):
            classify_source_completeness(
                EvidenceLane.LINK,
                0,
                summary_present=True,
            )

    def test_unique_packet_sequence_is_an_exact_match(self) -> None:
        decision = classify_telemetry_alarm_match((4, 5, 6), 5)

        self.assertEqual(decision.kind, CorrelationKind.EXACT)
        self.assertEqual(decision.basis, CorrelationBasis.PACKET_SEQUENCE)
        self.assertEqual(decision.candidate_record_indices, (1,))

    def test_missing_packet_sequence_is_impossible_from_loaded_evidence(self) -> None:
        decision = classify_telemetry_alarm_match((4, 5, 6), 7)

        self.assertEqual(decision.kind, CorrelationKind.IMPOSSIBLE)
        self.assertEqual(decision.candidate_record_indices, ())

    def test_duplicate_or_wrapped_sequence_is_visibly_ambiguous(self) -> None:
        decision = classify_telemetry_alarm_match((7, 8, 7), 7)

        self.assertEqual(decision.kind, CorrelationKind.AMBIGUOUS)
        self.assertEqual(decision.candidate_record_indices, (0, 2))

    def test_invalid_packet_sequences_are_rejected(self) -> None:
        cases = (
            ((True,), 1, TypeError),
            ((-1,), 1, ValueError),
            ((0x1_0000_0000,), 1, ValueError),
            ((1,), False, TypeError),
            ((1,), -1, ValueError),
        )
        for telemetry_sequences, alarm_sequence, exception in cases:
            with (
                self.subTest(
                    telemetry_sequences=telemetry_sequences,
                    alarm_sequence=alarm_sequence,
                ),
                self.assertRaises(exception),
            ):
                classify_telemetry_alarm_match(telemetry_sequences, alarm_sequence)

    def test_decision_invariants_reject_misleading_candidates(self) -> None:
        cases = (
            (CorrelationKind.EXACT, (), ValueError),
            (CorrelationKind.AMBIGUOUS, (0,), ValueError),
            (CorrelationKind.SEPARATE_LANE, (0,), ValueError),
            (CorrelationKind.EXACT, (-1,), ValueError),
            (CorrelationKind.AMBIGUOUS, (2, 1), ValueError),
        )
        for kind, candidates, exception in cases:
            with (
                self.subTest(kind=kind, candidates=candidates),
                self.assertRaises(exception),
            ):
                CorrelationDecision(
                    kind=kind,
                    basis=CorrelationBasis.PACKET_SEQUENCE,
                    candidate_record_indices=candidates,
                )

    def test_presentation_precedence_is_stable_but_not_temporal(self) -> None:
        self.assertEqual(
            LANE_PRECEDENCE,
            (EvidenceLane.TELEMETRY, EvidenceLane.ALARM, EvidenceLane.LINK),
        )
        keys = [presentation_key(lane, 0) for lane in reversed(LANE_PRECEDENCE)]
        self.assertEqual(sorted(keys), [(0, 0), (1, 0), (2, 0)])
        with self.assertRaises(TypeError):
            presentation_key(EvidenceLane.TELEMETRY, True)
        with self.assertRaises(ValueError):
            presentation_key(EvidenceLane.TELEMETRY, -1)


if __name__ == "__main__":
    unittest.main()
