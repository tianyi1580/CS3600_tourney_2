from __future__ import annotations

from dataclasses import dataclass

from game.enums import CARPET_POINTS_TABLE, Direction

from .bitboard_state import (
    BitboardState,
    collect_chain_entries,
    count_exits_with_masks,
    index_to_loc,
    landing_exit_profile_after_carpet,
    shortest_turn_distances,
)


@dataclass(frozen=True, slots=True)
class EntryInfo:
    entry_idx: int
    direction: Direction
    chain_len: int
    landing_idx: int
    value: float
    player_dist: int | None
    opp_dist: int | None
    zone: str
    player_same_axis: bool
    opp_same_axis: bool
    landing_exits: int
    landing_space_exits: int


@dataclass(frozen=True, slots=True)
class VoronoiSnapshot:
    """Root-only spatial ownership snapshot for Yolanda6."""

    entries: tuple[EntryInfo, ...]

    @classmethod
    def from_state(cls, state: BitboardState) -> VoronoiSnapshot:
        player_dists = shortest_turn_distances(state, state.player_idx, state.opponent_idx)
        opp_dists = shortest_turn_distances(state, state.opponent_idx, state.player_idx)
        player_loc = index_to_loc(state.player_idx)
        opp_loc = index_to_loc(state.opponent_idx)

        entries: list[EntryInfo] = []
        for entry_idx, direction, chain_len, landing_idx in collect_chain_entries(state, min_chain_len=2):
            player_dist = player_dists[entry_idx] if player_dists[entry_idx] >= 0 else None
            opp_dist = opp_dists[entry_idx] if opp_dists[entry_idx] >= 0 else None
            if player_dist is None and opp_dist is None:
                continue

            if opp_dist is None:
                zone = "safe"
            elif player_dist is None:
                zone = "dead"
            elif player_dist + 2 <= opp_dist:
                zone = "safe"
            elif opp_dist + 2 <= player_dist:
                zone = "dead"
            else:
                zone = "contested"

            entry_loc = index_to_loc(entry_idx)
            player_same_axis = _shares_chain_axis(player_loc, entry_loc, direction)
            opp_same_axis = _shares_chain_axis(opp_loc, entry_loc, direction)
            landing_exits, landing_space_exits = landing_exit_profile_after_carpet(
                state,
                entry_idx,
                direction,
                chain_len,
                state.opponent_idx,
            )
            entries.append(
                EntryInfo(
                    entry_idx=entry_idx,
                    direction=direction,
                    chain_len=chain_len,
                    landing_idx=landing_idx,
                    value=float(CARPET_POINTS_TABLE[min(chain_len, 7)]),
                    player_dist=player_dist,
                    opp_dist=opp_dist,
                    zone=zone,
                    player_same_axis=player_same_axis,
                    opp_same_axis=opp_same_axis,
                    landing_exits=landing_exits,
                    landing_space_exits=landing_space_exits,
                )
            )

        entries.sort(key=lambda info: (info.zone, -info.value, info.entry_idx, int(info.direction)))
        return cls(entries=tuple(entries))

    def zone_entries(self, zone: str) -> tuple[EntryInfo, ...]:
        return tuple(info for info in self.entries if info.zone == zone)

    def best_zone_value(self, zone: str) -> float:
        best = 0.0
        for info in self.entries:
            if info.zone == zone and info.value > best:
                best = info.value
        return best


def _shares_chain_axis(loc_a: tuple[int, int], loc_b: tuple[int, int], direction: Direction) -> bool:
    if direction in (Direction.LEFT, Direction.RIGHT):
        return loc_a[1] == loc_b[1]
    return loc_a[0] == loc_b[0]
