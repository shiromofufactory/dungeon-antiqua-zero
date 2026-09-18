"""Incremental, deterministic automatic battle planning without Pyxel."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

if __package__:
    from .auto_battle_model import (
        CASE_COUNT,
        DISCOUNT,
        FORECAST_TURNS,
        AutoActionEvaluation,
        AutoBattleDecision,
        AutoBattleSnapshot,
    )
    from .auto_battle_simulation import PRIORITY_RECOVERY_ACTIONS, BattleForecast
    from .battle_commands import BattleCommand
else:
    from auto_battle_model import (
        CASE_COUNT,
        DISCOUNT,
        FORECAST_TURNS,
        AutoActionEvaluation,
        AutoBattleDecision,
        AutoBattleSnapshot,
    )
    from auto_battle_simulation import PRIORITY_RECOVERY_ACTIONS, BattleForecast
    from battle_commands import BattleCommand


VALUE_NAMES = (
    "victory",
    "defeat",
    "deaths",
    "health",
    "ability",
    "kills",
    "damage",
    "information",
)
VALUE_WEIGHTS = (2000, -2000, -600, 45, 35, 80, 20, 1)


def round_score(score: float) -> float:
    return float(
        Decimal(str(score)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    )


class AutoBattlePlanner:
    """Every yield bounds one simulation step; no wall-clock-dependent pruning."""

    def __init__(self, snapshot: AutoBattleSnapshot) -> None:
        self.snapshot = snapshot
        self.result: AutoBattleDecision | None = None
        self.completed_units = 0
        self._iterator = self._calculate()

    def advance(self, units: int = 1) -> AutoBattleDecision | None:
        for _ in range(units):
            if self.result is not None:
                break
            try:
                next(self._iterator)
                self.completed_units += 1
            except StopIteration as completed:
                self.result = completed.value
                break
        return self.result

    def _forecast(self, case, cache):
        forecast = BattleForecast(self.snapshot, case)
        forecast.expected_cache = cache
        forecast.command_cache = self._command_cache
        forecast.timeline_cache = self._timeline_cache
        return forecast

    def _calculate(self):
        snapshot = self.snapshot
        excluded = []
        current = BattleForecast(snapshot, 0)
        actions = current.candidates(snapshot.active_number, excluded)
        recovery = current.recovery_action(snapshot.active_number, actions)
        if recovery is not None:
            action, stage = recovery
            return AutoBattleDecision(
                action,
                (),
                tuple(excluded),
                case_count=0,
                forecast_turns=0,
                reason="recovery_" + stage,
            )
        # Recovery is decided from current allies, never ranked by sampled risk.
        simulation_actions = []
        for action in actions:
            if (
                action.spell_key
                and current.spells[action.spell_key].action in PRIORITY_RECOVERY_ACTIONS
            ):
                excluded.append((action.spell_key, "recovery_not_needed"))
            else:
                simulation_actions.append(action)
        actions = tuple(simulation_actions)
        self._command_cache = {}
        self._timeline_cache = {}
        cache = {}
        weights = {}
        for spec in snapshot.combatants:
            if not spec.enemy or not spec.alive:
                continue
            harm = 0.0
            for case in range(CASE_COUNT):
                forecast = self._forecast(case, cache)
                actor = forecast.actors[spec.number]
                # This isolated hand has its own head, without other actors acting.
                entries = list(forecast.order.entries)
                head = next(e for e in entries if e.actor == spec.number)
                entries.remove(head)
                forecast.order = type(forecast.order)((head, *entries))
                before = {
                    n: (a.hp, a.actionable)
                    for n, a in forecast.actors.items()
                    if not a.spec.enemy and a.is_alive
                }
                if not forecast.prepare_turn(actor):
                    forecast.enemy_turn(actor)
                damage = sum(
                    max(0, hp - forecast.actors[n].hp) / forecast.actors[n].max_hp
                    for n, (hp, _) in before.items()
                )
                disabled = sum(
                    was and not forecast.actors[n].actionable
                    for n, (_, was) in before.items()
                )
                # Death is counted as HP loss, not a newly applied status.
                disabled -= sum(
                    was and not forecast.actors[n].is_alive
                    for n, (_, was) in before.items()
                )
                harm += damage + 0.25 * disabled
                yield
            weights[spec.number] = 1 + max(0, min(2, harm / CASE_COUNT))
        evaluations = []
        discounts = tuple(DISCOUNT**t for t in range(FORECAST_TURNS + 1))
        denominator = CASE_COUNT * sum(discounts)
        for action in actions:
            totals = [0.0] * len(VALUE_NAMES)
            cost = defeat = deaths = current_cost = gauge = 0.0
            focus_valid = True
            for case in range(CASE_COUNT):
                forecast = self._forecast(case, cache)
                start = forecast.values(weights)
                c, g = forecast.execute(snapshot.active_number, action)
                current_cost += c
                gauge += g
                cost += c
                for t, discount in enumerate(discounts):
                    if t:
                        cost += discount * forecast.step(weights)
                    values = forecast.values(weights)
                    for i, (value, initial) in enumerate(zip(values, start)):
                        totals[i] += discount * (value - initial)
                    yield
                defeat += forecast.defeated
                deaths += len(forecast.died)
                if (
                    action.command is BattleCommand.FOCUS
                    and not forecast.focus_completed
                ):
                    focus_valid = False
            components = tuple(
                (name, total / denominator) for name, total in zip(VALUE_NAMES, totals)
            )
            cost /= CASE_COUNT
            score = (
                sum(value * w for (_, value), w in zip(components, VALUE_WEIGHTS))
                - cost
            )
            first_types = 0
            if action.command is BattleCommand.SPELL:
                spell = next(s for s in snapshot.spells if s.key == action.spell_key)
                first_types = int(spell.type.value not in snapshot.used_spell_types)
            evaluations.append(
                AutoActionEvaluation(
                    action,
                    components,
                    cost,
                    score,
                    round_score(score),
                    defeat / CASE_COUNT,
                    deaths / CASE_COUNT,
                    current_cost / CASE_COUNT,
                    gauge / CASE_COUNT,
                    first_types,
                    "focus_beyond_horizon" if not focus_valid else "",
                )
            )
        eligible = [e for e in evaluations if not e.exclusion]
        if not eligible:
            raise RuntimeError("auto battle must have a legal defensive fallback")

        best = min(eligible, key=lambda e: e.selection_key(snapshot))
        return AutoBattleDecision(best.action, tuple(evaluations), tuple(excluded))


def decide_auto_battle(snapshot: AutoBattleSnapshot) -> AutoBattleDecision:
    planner = AutoBattlePlanner(snapshot)
    while planner.result is None:
        planner.advance(256)
    return planner.result
