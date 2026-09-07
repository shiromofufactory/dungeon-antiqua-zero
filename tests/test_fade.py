from __future__ import annotations

import unittest

from app.rendering.fade import (
    DEFAULT_FADE_FRAME_COUNT,
    FadeEvent,
    FadePhase,
    FadeThroughBlack,
)


class FadeThroughBlackTest(unittest.TestCase):
    def test_fades_out_and_in_over_six_frames_each_by_default(self) -> None:
        fade = FadeThroughBlack()
        frame_count = DEFAULT_FADE_FRAME_COUNT
        self.assertEqual(frame_count, 6)

        fade.start()
        fade_out_rates = []
        fade_out_events = []
        for _frame in range(frame_count):
            fade_out_events.append(fade.update())
            fade_out_rates.append(fade.visible_rate)

        self.assertEqual(
            fade_out_rates,
            [1.0 - frame / frame_count for frame in range(1, frame_count + 1)],
        )
        self.assertEqual(fade_out_events[-1], FadeEvent.COVERED)
        self.assertEqual(
            fade_out_events[:-1],
            [FadeEvent.NONE] * (frame_count - 1),
        )
        self.assertIs(fade.phase, FadePhase.FADING_IN)

        fade_in_rates = []
        fade_in_events = []
        for _frame in range(frame_count):
            fade_in_events.append(fade.update())
            fade_in_rates.append(fade.visible_rate)

        self.assertEqual(
            fade_in_rates,
            [frame / frame_count for frame in range(1, frame_count + 1)],
        )
        self.assertEqual(fade_in_events[-1], FadeEvent.FINISHED)
        self.assertEqual(
            fade_in_events[:-1],
            [FadeEvent.NONE] * (frame_count - 1),
        )
        self.assertIs(fade.phase, FadePhase.IDLE)
        self.assertFalse(fade.is_active)

    def test_accepts_a_longer_duration_for_event_transitions(self) -> None:
        frame_count = 30
        fade = FadeThroughBlack(frame_count=frame_count)

        fade.start()
        for _frame in range(frame_count - 1):
            self.assertIs(fade.update(), FadeEvent.NONE)

        self.assertIs(fade.update(), FadeEvent.COVERED)
        self.assertEqual(fade.visible_rate, 0.0)
        self.assertEqual(fade.frame_count, frame_count)
        for _frame in range(frame_count - 1):
            self.assertIs(fade.update(), FadeEvent.NONE)

        self.assertIs(fade.update(), FadeEvent.FINISHED)
        self.assertEqual(fade.visible_rate, 1.0)

    def test_idle_update_does_nothing(self) -> None:
        fade = FadeThroughBlack()

        self.assertIs(fade.update(), FadeEvent.NONE)
        self.assertEqual(fade.visible_rate, 1.0)

    def test_can_start_directly_from_black_and_fade_in(self) -> None:
        fade = FadeThroughBlack()

        fade.start_fade_in()

        self.assertIs(fade.phase, FadePhase.FADING_IN)
        self.assertEqual(fade.visible_rate, 0.0)
        rates = []
        events = []
        for _frame in range(fade.frame_count):
            events.append(fade.update())
            rates.append(fade.visible_rate)
        self.assertEqual(
            rates,
            [frame / fade.frame_count for frame in range(1, fade.frame_count + 1)],
        )
        self.assertEqual(events[-1], FadeEvent.FINISHED)
        self.assertFalse(fade.is_active)

    def test_rejects_a_second_start_while_active(self) -> None:
        fade = FadeThroughBlack()
        fade.start()

        with self.assertRaisesRegex(RuntimeError, "already active"):
            fade.start()

        with self.assertRaisesRegex(RuntimeError, "already active"):
            fade.start_fade_in()

    def test_rejects_invalid_frame_counts(self) -> None:
        for frame_count in (True, 1.5, "8"):
            with self.subTest(frame_count=frame_count):
                with self.assertRaises(TypeError):
                    FadeThroughBlack(frame_count)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            FadeThroughBlack(0)


if __name__ == "__main__":
    unittest.main()
