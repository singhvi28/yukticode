"""
leaderboard.py
==============
In-memory leaderboard backed by a segment tree over coordinate-compressed
score buckets with competition (1-2-2-4) tie-breaking by submission timestamp.

Architecture
------------
Score range  ──► coordinate compression ──► sorted score list + score_to_idx map
                                                        │
                                               segment tree leaves
                                           (each leaf = one distinct score)
                                           node value: (count, sum_scores)
                                                        │
Per-score bucket  {score_value: {timestamp: set(player_ids)}}
    └── used for O(T) tie-break counting within the same score bucket

Ranking formula
---------------
    rank(p) = 1
            + count(players with strictly higher score)      # O(log M) via tree
            + count(same score, strictly more recent ts)     # O(T) bucket scan
"""

from __future__ import annotations

import bisect
import time
import unittest
from typing import Dict, List, Optional, Set, Tuple


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _next_pow2(n: int) -> int:
    """Return the smallest power of 2 that is >= *n* (minimum 1)."""
    p = 1
    while p < n:
        p <<= 1
    return p


# ---------------------------------------------------------------------------
# Segment tree
# ---------------------------------------------------------------------------

class _SegmentTree:
    """
    Array-backed, iterative segment tree with ``num_leaves`` logical leaves
    (0-indexed).  Each node stores a ``(count, sum_scores)`` aggregate.

    The tree is padded to the next power-of-2 so that the standard iterative
    scheme works without edge-case guards.  Unused leaves stay zero and never
    appear in range queries.

    Node layout (1-indexed)
    -----------------------
    ::

        index : 1
                / \\
               2   3
              / \\ / \\
             4  5 6  7   ← leaves for a 4-leaf tree (n=4)

    For a tree with ``self._n`` (power-of-2) leaves:
    - leaves live at positions ``self._n … 2*self._n - 1``
    - the root lives at position ``1``

    All operations are O(log n) where n = ``self._n``.
    """

    def __init__(self, num_leaves: int) -> None:
        self._n: int = _next_pow2(max(num_leaves, 1))
        size = 2 * self._n
        self._count: List[int] = [0] * size
        self._sum: List[float] = [0.0] * size

    # ------------------------------------------------------------------
    # Internal: propagate a leaf change upward
    # ------------------------------------------------------------------

    def _pull_up(self, i: int) -> None:
        """Recompute all ancestors of leaf array-index *i* from children."""
        i >>= 1
        while i >= 1:
            self._count[i] = self._count[2 * i] + self._count[2 * i + 1]
            self._sum[i] = self._sum[2 * i] + self._sum[2 * i + 1]
            i >>= 1

    # ------------------------------------------------------------------
    # Public tree operations
    # ------------------------------------------------------------------

    def update(self, pos: int, d_count: int, d_sum: float) -> None:
        """
        O(log n) point update: add ``(d_count, d_sum)`` at logical leaf
        *pos* (0-indexed).

        Parameters
        ----------
        pos:
            0-based leaf index.
        d_count:
            Delta to apply to the count stored at this leaf.
        d_sum:
            Delta to apply to the score sum stored at this leaf.
        """
        i = pos + self._n          # map to array position
        self._count[i] += d_count
        self._sum[i] += d_sum
        self._pull_up(i)

    def query(self, l: int, r: int) -> Tuple[int, float]:
        """
        O(log n) range-sum query over the closed interval ``[l, r]``
        (0-indexed logical leaf positions).

        Returns
        -------
        (count, sum_scores)
            Aggregate over all leaves in the queried range.
        """
        if l > r:
            return 0, 0.0
        res_c, res_s = 0, 0.0
        l += self._n          # shift to array positions
        r += self._n + 1      # half-open [l, r+1)
        while l < r:
            if l & 1:          # l is a right child: include and step right
                res_c += self._count[l]
                res_s += self._sum[l]
                l += 1
            if r & 1:          # r-1 is a right child: include and step left
                r -= 1
                res_c += self._count[r]
                res_s += self._sum[r]
            l >>= 1
            r >>= 1
        return res_c, res_s

    @property
    def total_count(self) -> int:
        """Total number of elements across all leaves (root value)."""
        return self._count[1]

    @property
    def total_sum(self) -> float:
        """Total score sum across all leaves (root value)."""
        return self._sum[1]


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------

class Leaderboard:
    """
    In-memory leaderboard with O(log M) rank queries backed by a segment tree
    over M distinct score buckets (coordinate-compressed).

    Ranking rules
    -------------
    * Higher score → better rank.
    * Equal scores: more recent timestamp (larger value) → better rank.
    * Equal ``(score, timestamp)``: players share the same **competition rank**
      (dense: if two players tie at rank *k*, the next distinct group has
      rank *k + 2*, not *k + 1*).

    Thread safety
    -------------
    Not thread-safe; external locking is required for concurrent access.
    """

    def __init__(self) -> None:
        # player_id → (score, timestamp)
        self._players: Dict[str, Tuple[float, float]] = {}

        # Coordinate compression
        # Sorted ascending list of all distinct score values seen
        self._sorted_scores: List[float] = []
        # score_value → 0-based compressed index
        self._score_to_idx: Dict[float, int] = {}

        # Per-score bucket:  score_value → {timestamp → set(player_id)}
        # Timestamps are plain dict keys; we iterate and compare numerically.
        self._buckets: Dict[float, Dict[float, Set[str]]] = {}

        # Segment tree; None until at least one distinct score is registered
        self._tree: Optional[_SegmentTree] = None

    # ------------------------------------------------------------------
    # Private: coordinate compression & tree management
    # ------------------------------------------------------------------

    def _ensure_score(self, score: float) -> bool:
        """
        Register *score* in the compressed index if it has not been seen before.

        Parameters
        ----------
        score : float
            Score value to register.

        Returns
        -------
        bool
            ``True`` if *score* was newly inserted — the caller **must** call
            :meth:`_rebuild_tree` afterwards.  ``False`` if it already existed.
        """
        if score in self._score_to_idx:
            return False
        # Insert in the correct sorted position
        idx = bisect.bisect_left(self._sorted_scores, score)
        self._sorted_scores.insert(idx, score)
        # Rebuild the O(M) index map (all indices after insertion point shift)
        self._score_to_idx = {s: i for i, s in enumerate(self._sorted_scores)}
        # Initialise empty bucket for the new score
        self._buckets[score] = {}
        return True

    def _rebuild_tree(self) -> None:
        """
        Reconstruct the segment tree from scratch using current bucket data.

        This is called whenever a new distinct score is introduced, because all
        compressed indices may have shifted.  O(M log M) overall but M is
        expected to be small relative to the number of players.
        """
        m = len(self._sorted_scores)
        if m == 0:
            self._tree = None
            return
        self._tree = _SegmentTree(m)
        for score, ts_map in self._buckets.items():
            n = sum(len(pids) for pids in ts_map.values())
            if n:
                idx = self._score_to_idx[score]
                self._tree.update(idx, n, score * n)

    def _tree_point_update(self, score: float, d_count: int) -> None:
        """
        O(log M) point update: change the count at *score*'s leaf by
        *d_count* (positive to add, negative to remove).

        No-op if the tree has not been built yet.
        """
        if self._tree is None:
            return
        idx = self._score_to_idx[score]
        self._tree.update(idx, d_count, score * d_count)

    def _count_strictly_higher(self, score_idx: int) -> int:
        """
        Return the total number of players whose score index is strictly
        greater than *score_idx* (i.e. strictly higher score).
        O(log M).
        """
        m = len(self._sorted_scores)
        hi = m - 1
        if self._tree is None or score_idx >= hi:
            return 0
        count, _ = self._tree.query(score_idx + 1, hi)
        return count

    # ------------------------------------------------------------------
    # Private: per-bucket timestamp helpers
    # ------------------------------------------------------------------

    def _bucket_add(self, score: float, timestamp: float, player_id: str) -> None:
        """Insert *player_id* at the ``(score, timestamp)`` slot in the bucket."""
        ts_map = self._buckets[score]
        if timestamp not in ts_map:
            ts_map[timestamp] = set()
        ts_map[timestamp].add(player_id)

    def _bucket_remove(self, score: float, timestamp: float, player_id: str) -> None:
        """Remove *player_id* from the ``(score, timestamp)`` slot; prune empties."""
        ts_map = self._buckets[score]
        ts_map[timestamp].discard(player_id)
        if not ts_map[timestamp]:
            del ts_map[timestamp]

    def _count_same_score_newer_ts(self, score: float, timestamp: float) -> int:
        """
        Count players with the same *score* and a **strictly greater**
        timestamp (they are ranked higher within the same score bucket).

        O(T) where T is the number of distinct timestamps at *score*.
        """
        ts_map = self._buckets.get(score, {})
        return sum(len(pids) for ts, pids in ts_map.items() if ts > timestamp)

    # ------------------------------------------------------------------
    # Private: rank computation
    # ------------------------------------------------------------------

    def _compute_rank(self, score: float, timestamp: float) -> int:
        """
        Compute the competition rank for the ``(score, timestamp)`` pair.

        rank = 1
             + count(players with strictly higher score)          # tree query
             + count(same score, strictly more recent timestamp)  # bucket scan

        Parameters
        ----------
        score : float
        timestamp : float

        Returns
        -------
        int
            1-based competition rank.
        """
        if not self._sorted_scores:
            return 1
        score_idx = self._score_to_idx[score]
        count_higher = self._count_strictly_higher(score_idx)
        count_newer = self._count_same_score_newer_ts(score, timestamp)
        return 1 + count_higher + count_newer

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_player(
        self,
        player_id: str,
        score: float,
        timestamp: Optional[float] = None,
    ) -> None:
        """
        Add *player_id* to the leaderboard.

        Parameters
        ----------
        player_id : str
            Unique identifier for the player.
        score : float
            Initial score (higher is better).
        timestamp : float, optional
            Submission time as a Unix epoch float.  Defaults to
            ``time.time()`` at the moment of the call.

        Raises
        ------
        ValueError
            If *player_id* is already registered.  Use
            :meth:`update_score` to change an existing player's score.
        """
        if player_id in self._players:
            raise ValueError(
                f"Player '{player_id}' already exists. "
                "Use update_score() to modify an existing entry."
            )
        if timestamp is None:
            timestamp = time.time()

        # --- coordinate compression (tree rebuild if new score) ---
        is_new_score = self._ensure_score(score)
        if is_new_score:
            # Tree rebuilt from buckets; player not yet in any bucket → correct
            self._rebuild_tree()

        # --- insert into bucket ---
        self._bucket_add(score, timestamp, player_id)
        self._players[player_id] = (score, timestamp)

        # --- point-update the tree ---
        # Whether or not we just rebuilt, we increment the leaf for this score.
        self._tree_point_update(score, +1)

    def update_score(
        self,
        player_id: str,
        new_score: float,
        timestamp: Optional[float] = None,
    ) -> None:
        """
        Update *player_id*'s score to *new_score*, or add them if absent.

        Parameters
        ----------
        player_id : str
            Unique identifier for the player.
        new_score : float
            New score (higher is better).
        timestamp : float, optional
            Submission time as a Unix epoch float.  Defaults to
            ``time.time()`` at the moment of the call.
        """
        if timestamp is None:
            timestamp = time.time()

        if player_id not in self._players:
            self.add_player(player_id, new_score, timestamp)
            return

        old_score, old_ts = self._players[player_id]

        # --- remove from old position (bucket + tree) ---
        self._bucket_remove(old_score, old_ts, player_id)
        self._tree_point_update(old_score, -1)

        # --- coordinate compression (tree rebuild if new score) ---
        # At this point the player is in neither bucket nor tree; any rebuild
        # will reflect the fully consistent state of all *other* players.
        is_new_score = self._ensure_score(new_score)
        if is_new_score:
            self._rebuild_tree()

        # --- insert into new position (bucket + tree) ---
        self._bucket_add(new_score, timestamp, player_id)
        self._players[player_id] = (new_score, timestamp)
        self._tree_point_update(new_score, +1)

    def remove_player(self, player_id: str) -> None:
        """
        Remove *player_id* from the leaderboard permanently.

        Parameters
        ----------
        player_id : str
            Unique identifier for the player.

        Raises
        ------
        KeyError
            If *player_id* is not registered.
        """
        if player_id not in self._players:
            raise KeyError(f"Player '{player_id}' not found.")

        score, ts = self._players.pop(player_id)
        self._bucket_remove(score, ts, player_id)
        self._tree_point_update(score, -1)

    def get_rank(self, player_id: str) -> int:
        """
        Return the competition rank of *player_id* (1 = best).

        Competition ranking: if *k* players share rank *r*, the next distinct
        group begins at rank *r + k* (not *r + 1*).

        Parameters
        ----------
        player_id : str
            Unique identifier for the player.

        Returns
        -------
        int
            1-based competition rank.

        Raises
        ------
        KeyError
            If *player_id* is not registered.
        """
        if player_id not in self._players:
            raise KeyError(f"Player '{player_id}' not found.")
        score, ts = self._players[player_id]
        return self._compute_rank(score, ts)

    def get_top_k(self, k: int) -> List[Tuple[str, float, int, float]]:
        """
        Return the top-*k* players ordered by their ranking.

        Within a tied group (same competition rank), the secondary ordering is
        score descending then timestamp descending, which is consistent with
        the ranking rules and gives a deterministic result within a single call.

        Parameters
        ----------
        k : int
            Maximum number of results to return.  Passing a value larger than
            the total number of players returns all players.

        Returns
        -------
        list of (player_id, score, rank, timestamp)
            Tuples sorted by rank ascending (then score desc, timestamp desc
            as a tiebreaker for display ordering within a tied group).
        """
        if k <= 0:
            return []

        entries: List[Tuple[str, float, int, float]] = []
        for pid, (score, ts) in self._players.items():
            rank = self._compute_rank(score, ts)
            entries.append((pid, score, rank, ts))

        # Sort: rank ASC, score DESC, timestamp DESC (stable within tied groups)
        entries.sort(key=lambda x: (x[2], -x[1], -x[3]))
        return entries[:k]

    def kth_highest(self, k: int) -> Tuple[str, float, int, float]:
        """
        Return the *k*-th player in sorted leaderboard order (1 = best).

        Two players who share competition rank *r* occupy consecutive sorted
        positions; both are returned at their respective *k* values and both
        carry ``rank == r`` in the result.

        Parameters
        ----------
        k : int
            1-based position in the sorted leaderboard
            (not necessarily equal to the competition rank at that position).

        Returns
        -------
        (player_id, score, rank, timestamp)

        Raises
        ------
        IndexError
            If *k* < 1 or *k* > total number of registered players.
        """
        n = len(self._players)
        if k < 1 or k > n:
            raise IndexError(
                f"k={k} is out of range; "
                f"leaderboard currently has {n} player(s)."
            )
        return self.get_top_k(n)[k - 1]

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        """Return the number of players currently on the leaderboard."""
        return len(self._players)

    def __contains__(self, player_id: str) -> bool:
        """Return ``True`` if *player_id* is registered."""
        return player_id in self._players

    def __repr__(self) -> str:  # pragma: no cover
        return f"Leaderboard(players={len(self._players)})"


# ===========================================================================
# Unit tests
# ===========================================================================

class TestSegmentTree(unittest.TestCase):
    """Unit tests for the internal _SegmentTree data structure."""

    def test_single_leaf(self) -> None:
        tree = _SegmentTree(1)
        tree.update(0, 3, 30.0)
        count, total = tree.query(0, 0)
        self.assertEqual(count, 3)
        self.assertAlmostEqual(total, 30.0)

    def test_non_power_of_two_leaves(self) -> None:
        """Tree with 5 leaves (padded to 8 internally) should still work."""
        tree = _SegmentTree(5)
        tree.update(0, 1, 10.0)
        tree.update(4, 2, 40.0)
        count, total = tree.query(0, 4)
        self.assertEqual(count, 3)
        self.assertAlmostEqual(total, 50.0)

    def test_point_update_accumulates(self) -> None:
        tree = _SegmentTree(4)
        tree.update(2, 2, 20.0)
        tree.update(2, 3, 30.0)     # add to same leaf
        count, total = tree.query(2, 2)
        self.assertEqual(count, 5)
        self.assertAlmostEqual(total, 50.0)

    def test_negative_update(self) -> None:
        tree = _SegmentTree(4)
        tree.update(1, 5, 50.0)
        tree.update(1, -2, -20.0)
        count, total = tree.query(1, 1)
        self.assertEqual(count, 3)
        self.assertAlmostEqual(total, 30.0)

    def test_range_query_boundaries(self) -> None:
        tree = _SegmentTree(6)
        for i in range(6):
            tree.update(i, 1, float(i * 10))   # leaf i: count=1, sum=i*10
        # Full range
        count, total = tree.query(0, 5)
        self.assertEqual(count, 6)
        self.assertAlmostEqual(total, 150.0)    # 0+10+20+30+40+50
        # Sub-range [2,4]
        count, total = tree.query(2, 4)
        self.assertEqual(count, 3)
        self.assertAlmostEqual(total, 90.0)     # 20+30+40
        # Empty range
        count, total = tree.query(3, 2)
        self.assertEqual(count, 0)

    def test_total_count_property(self) -> None:
        tree = _SegmentTree(4)
        tree.update(0, 2, 0.0)
        tree.update(3, 5, 0.0)
        self.assertEqual(tree.total_count, 7)

    def test_many_leaves(self) -> None:
        n = 100
        tree = _SegmentTree(n)
        for i in range(n):
            tree.update(i, 1, float(i))
        self.assertEqual(tree.total_count, n)
        count, _ = tree.query(50, 99)
        self.assertEqual(count, 50)


class TestLeaderboardBasic(unittest.TestCase):
    """Tests for fundamental add / remove / update operations."""

    def _make_lb(self) -> Leaderboard:
        """Three-player leaderboard with deterministic timestamps."""
        lb = Leaderboard()
        lb.add_player("alice", 100.0, timestamp=1000.0)
        lb.add_player("bob", 200.0, timestamp=2000.0)
        lb.add_player("charlie", 150.0, timestamp=3000.0)
        return lb

    def test_empty_leaderboard_len(self) -> None:
        self.assertEqual(len(Leaderboard()), 0)

    def test_add_single_player_rank_one(self) -> None:
        lb = Leaderboard()
        lb.add_player("alice", 42.0, timestamp=1.0)
        self.assertEqual(len(lb), 1)
        self.assertEqual(lb.get_rank("alice"), 1)

    def test_basic_ranking_by_score(self) -> None:
        lb = self._make_lb()
        # bob(200) > charlie(150) > alice(100)
        self.assertEqual(lb.get_rank("bob"), 1)
        self.assertEqual(lb.get_rank("charlie"), 2)
        self.assertEqual(lb.get_rank("alice"), 3)

    def test_contains(self) -> None:
        lb = self._make_lb()
        self.assertIn("alice", lb)
        self.assertNotIn("zoe", lb)

    def test_add_duplicate_raises_value_error(self) -> None:
        lb = Leaderboard()
        lb.add_player("alice", 100.0, timestamp=1.0)
        with self.assertRaises(ValueError):
            lb.add_player("alice", 200.0, timestamp=2.0)

    def test_remove_player_updates_ranks(self) -> None:
        lb = self._make_lb()
        lb.remove_player("bob")
        self.assertEqual(len(lb), 2)
        self.assertEqual(lb.get_rank("charlie"), 1)
        self.assertEqual(lb.get_rank("alice"), 2)

    def test_remove_nonexistent_raises_key_error(self) -> None:
        lb = Leaderboard()
        with self.assertRaises(KeyError):
            lb.remove_player("ghost")

    def test_get_rank_unknown_player_raises(self) -> None:
        lb = Leaderboard()
        with self.assertRaises(KeyError):
            lb.get_rank("nobody")

    def test_update_score_changes_rank(self) -> None:
        lb = self._make_lb()
        lb.update_score("alice", 300.0, timestamp=9000.0)
        self.assertEqual(lb.get_rank("alice"), 1)
        self.assertEqual(lb.get_rank("bob"), 2)
        self.assertEqual(lb.get_rank("charlie"), 3)

    def test_update_score_adds_missing_player(self) -> None:
        lb = Leaderboard()
        lb.update_score("dave", 50.0, timestamp=100.0)
        self.assertEqual(len(lb), 1)
        self.assertEqual(lb.get_rank("dave"), 1)

    def test_update_score_same_score_different_bucket(self) -> None:
        """update_score to a score that already exists as a bucket."""
        lb = self._make_lb()
        # Set alice to 200 (same as bob)
        lb.update_score("alice", 200.0, timestamp=5000.0)
        # alice has ts=5000 > bob ts=2000 → alice rank 1, bob rank 2
        self.assertEqual(lb.get_rank("alice"), 1)
        self.assertEqual(lb.get_rank("bob"), 2)

    def test_default_timestamp_assigned(self) -> None:
        """When no timestamp is supplied, time.time() is used (not 0 or None)."""
        lb = Leaderboard()
        before = time.time()
        lb.add_player("x", 10.0)
        after = time.time()
        _, ts = lb._players["x"]
        self.assertGreaterEqual(ts, before)
        self.assertLessEqual(ts, after)


class TestLeaderboardTieBreaking(unittest.TestCase):
    """Tests for competition ranking in the presence of ties."""

    def test_same_score_higher_timestamp_wins(self) -> None:
        """More recent submission should rank higher at equal score."""
        lb = Leaderboard()
        lb.add_player("early", 100.0, timestamp=1000.0)
        lb.add_player("late", 100.0, timestamp=2000.0)
        self.assertEqual(lb.get_rank("late"), 1)
        self.assertEqual(lb.get_rank("early"), 2)

    def test_same_score_same_timestamp_share_rank(self) -> None:
        """Players with identical (score, timestamp) share competition rank 1."""
        lb = Leaderboard()
        lb.add_player("p1", 100.0, timestamp=1000.0)
        lb.add_player("p2", 100.0, timestamp=1000.0)
        self.assertEqual(lb.get_rank("p1"), 1)
        self.assertEqual(lb.get_rank("p2"), 1)

    def test_competition_rank_gap_after_two_way_tie(self) -> None:
        """Two players tie at rank 1; next player must be rank 3, not 2."""
        lb = Leaderboard()
        lb.add_player("p1", 100.0, timestamp=1.0)
        lb.add_player("p2", 100.0, timestamp=1.0)
        lb.add_player("p3", 50.0, timestamp=1.0)
        self.assertEqual(lb.get_rank("p1"), 1)
        self.assertEqual(lb.get_rank("p2"), 1)
        self.assertEqual(lb.get_rank("p3"), 3)     # gap: rank 2 does not exist

    def test_competition_rank_gap_after_three_way_tie(self) -> None:
        """Three-way tie at rank 1 → next player is rank 4."""
        lb = Leaderboard()
        lb.add_player("a", 100.0, timestamp=1.0)
        lb.add_player("b", 100.0, timestamp=1.0)
        lb.add_player("c", 100.0, timestamp=1.0)
        lb.add_player("d", 50.0, timestamp=1.0)
        for pid in ("a", "b", "c"):
            self.assertEqual(lb.get_rank(pid), 1)
        self.assertEqual(lb.get_rank("d"), 4)

    def test_mixed_tie_across_levels(self) -> None:
        """Tie at one level should not corrupt ranks at other levels."""
        lb = Leaderboard()
        lb.add_player("top1", 300.0, timestamp=1.0)
        lb.add_player("top2", 300.0, timestamp=1.0)   # tied at rank 1
        lb.add_player("mid",  200.0, timestamp=1.0)   # rank 3 (gap after two-way tie)
        lb.add_player("low1", 100.0, timestamp=2.0)
        lb.add_player("low2", 100.0, timestamp=1.0)   # low1 newer → rank 4, low2 rank 5
        self.assertEqual(lb.get_rank("top1"), 1)
        self.assertEqual(lb.get_rank("top2"), 1)
        self.assertEqual(lb.get_rank("mid"), 3)
        self.assertEqual(lb.get_rank("low1"), 4)
        self.assertEqual(lb.get_rank("low2"), 5)

    def test_updating_to_break_tie(self) -> None:
        """After an update, the updated player should leave the tied group."""
        lb = Leaderboard()
        lb.add_player("a", 100.0, timestamp=1.0)
        lb.add_player("b", 100.0, timestamp=1.0)
        lb.add_player("c", 50.0, timestamp=1.0)
        # break tie: give a a better score
        lb.update_score("a", 200.0, timestamp=2.0)
        self.assertEqual(lb.get_rank("a"), 1)
        self.assertEqual(lb.get_rank("b"), 2)   # no longer tied; rank 2 exists
        self.assertEqual(lb.get_rank("c"), 3)


class TestLeaderboardGetTopK(unittest.TestCase):
    """Tests for get_top_k ordering and edge cases."""

    def _make_lb(self) -> Leaderboard:
        lb = Leaderboard()
        lb.add_player("alice",   100.0, timestamp=1000.0)
        lb.add_player("bob",     200.0, timestamp=2000.0)
        lb.add_player("charlie", 150.0, timestamp=3000.0)
        return lb

    def test_top_k_returns_correct_order(self) -> None:
        lb = self._make_lb()
        top2 = lb.get_top_k(2)
        self.assertEqual(len(top2), 2)
        self.assertEqual(top2[0][0], "bob")     # rank 1
        self.assertEqual(top2[1][0], "charlie") # rank 2

    def test_top_k_larger_than_players(self) -> None:
        """When k exceeds the number of players, all players are returned."""
        lb = self._make_lb()
        result = lb.get_top_k(100)
        self.assertEqual(len(result), 3)

    def test_top_k_zero(self) -> None:
        self.assertEqual(Leaderboard().get_top_k(0), [])

    def test_top_k_empty_leaderboard(self) -> None:
        self.assertEqual(Leaderboard().get_top_k(5), [])

    def test_top_k_tuple_structure(self) -> None:
        """Each tuple must be (player_id, score, rank, timestamp)."""
        lb = self._make_lb()
        entry = lb.get_top_k(1)[0]
        pid, score, rank, ts = entry
        self.assertEqual(pid, "bob")
        self.assertAlmostEqual(score, 200.0)
        self.assertEqual(rank, 1)
        self.assertAlmostEqual(ts, 2000.0)

    def test_top_k_with_ties_all_tied_at_rank_1(self) -> None:
        lb = Leaderboard()
        lb.add_player("p1", 100.0, timestamp=1.0)
        lb.add_player("p2", 100.0, timestamp=1.0)
        lb.add_player("p3", 50.0, timestamp=1.0)
        top3 = lb.get_top_k(3)
        # First two entries should have rank 1, third rank 3
        self.assertEqual(top3[0][2], 1)
        self.assertEqual(top3[1][2], 1)
        self.assertEqual(top3[2][2], 3)
        self.assertEqual(top3[2][0], "p3")

    def test_top_k_timestamp_tiebreak_ordering(self) -> None:
        """Within get_top_k, the player with the more recent ts appears first."""
        lb = Leaderboard()
        lb.add_player("old", 100.0, timestamp=1000.0)
        lb.add_player("new", 100.0, timestamp=2000.0)
        lb.add_player("best", 200.0, timestamp=500.0)
        top3 = lb.get_top_k(3)
        pids = [e[0] for e in top3]
        self.assertEqual(pids[0], "best")
        self.assertEqual(pids[1], "new")    # same score as old but more recent
        self.assertEqual(pids[2], "old")

    def test_top_k_single_player(self) -> None:
        lb = Leaderboard()
        lb.add_player("solo", 99.0, timestamp=1.0)
        result = lb.get_top_k(1)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][0], "solo")
        self.assertEqual(result[0][2], 1)

    def test_top_k_ranks_are_consistent_with_get_rank(self) -> None:
        """Rank embedded in get_top_k must agree with get_rank for each player."""
        lb = Leaderboard()
        lb.add_player("x", 10.0, timestamp=5.0)
        lb.add_player("y", 20.0, timestamp=3.0)
        lb.add_player("z", 20.0, timestamp=7.0)
        lb.add_player("w", 5.0, timestamp=1.0)
        for pid, score, rank, ts in lb.get_top_k(4):
            self.assertEqual(rank, lb.get_rank(pid))


class TestLeaderboardKthHighest(unittest.TestCase):
    """Tests for kth_highest correctness and edge cases."""

    def _make_lb(self) -> Leaderboard:
        lb = Leaderboard()
        lb.add_player("alice",   100.0, timestamp=1000.0)
        lb.add_player("bob",     200.0, timestamp=2000.0)
        lb.add_player("charlie", 150.0, timestamp=3000.0)
        return lb

    def test_kth_highest_k1_is_best(self) -> None:
        lb = self._make_lb()
        pid, score, rank, ts = lb.kth_highest(1)
        self.assertEqual(pid, "bob")
        self.assertAlmostEqual(score, 200.0)
        self.assertEqual(rank, 1)

    def test_kth_highest_last(self) -> None:
        lb = self._make_lb()
        pid, score, rank, ts = lb.kth_highest(3)
        self.assertEqual(pid, "alice")
        self.assertEqual(rank, 3)

    def test_kth_highest_raises_on_zero(self) -> None:
        lb = self._make_lb()
        with self.assertRaises(IndexError):
            lb.kth_highest(0)

    def test_kth_highest_raises_on_too_large(self) -> None:
        lb = self._make_lb()
        with self.assertRaises(IndexError):
            lb.kth_highest(4)

    def test_kth_highest_raises_on_empty(self) -> None:
        with self.assertRaises(IndexError):
            Leaderboard().kth_highest(1)

    def test_kth_highest_tied_positions_share_rank(self) -> None:
        """k=1 and k=2 should both return rank-1 entries when two players tie."""
        lb = Leaderboard()
        lb.add_player("p1", 100.0, timestamp=1.0)
        lb.add_player("p2", 100.0, timestamp=1.0)
        lb.add_player("p3", 50.0, timestamp=1.0)
        e1 = lb.kth_highest(1)
        e2 = lb.kth_highest(2)
        e3 = lb.kth_highest(3)
        # positions 1 and 2 are both rank-1 tied entries
        self.assertEqual(e1[2], 1)
        self.assertEqual(e2[2], 1)
        # position 3 is rank 3 (competition gap)
        self.assertEqual(e3[2], 3)
        self.assertEqual(e3[0], "p3")

    def test_kth_highest_all_tied(self) -> None:
        """When all players are tied, every kth_highest position has rank 1."""
        lb = Leaderboard()
        for i in range(5):
            lb.add_player(f"p{i}", 100.0, timestamp=1.0)
        for k in range(1, 6):
            self.assertEqual(lb.kth_highest(k)[2], 1)

    def test_kth_highest_consistent_with_get_top_k(self) -> None:
        """kth_highest(k) must equal the k-th entry of get_top_k(n)."""
        lb = Leaderboard()
        lb.add_player("a", 30.0, timestamp=1.0)
        lb.add_player("b", 30.0, timestamp=2.0)
        lb.add_player("c", 20.0, timestamp=5.0)
        lb.add_player("d", 10.0, timestamp=3.0)
        top = lb.get_top_k(4)
        for k, expected in enumerate(top, start=1):
            self.assertEqual(lb.kth_highest(k), expected)


class TestLeaderboardCoordinateCompression(unittest.TestCase):
    """Tests verifying that tree rebuilds on new scores maintain correctness."""

    def test_many_distinct_scores_sequential(self) -> None:
        lb = Leaderboard()
        n = 50
        for i in range(n):
            lb.add_player(f"p{i}", float(i), timestamp=float(i))
        # Highest score is i=49
        self.assertEqual(lb.get_rank("p49"), 1)
        # Lowest score is i=0; rank = n
        self.assertEqual(lb.get_rank("p0"), n)

    def test_many_distinct_scores_reverse(self) -> None:
        lb = Leaderboard()
        n = 30
        for i in range(n - 1, -1, -1):          # insert in descending order
            lb.add_player(f"p{i}", float(i), timestamp=1.0)
        self.assertEqual(lb.get_rank("p29"), 1)
        self.assertEqual(lb.get_rank("p0"), n)

    def test_interleaved_score_insertion(self) -> None:
        """Inserting a score that falls between two existing scores."""
        lb = Leaderboard()
        lb.add_player("low", 10.0, timestamp=1.0)
        lb.add_player("high", 30.0, timestamp=1.0)
        # Insert score 20 — will insert between existing indices 0 and 1
        lb.add_player("mid", 20.0, timestamp=1.0)
        self.assertEqual(lb.get_rank("high"), 1)
        self.assertEqual(lb.get_rank("mid"), 2)
        self.assertEqual(lb.get_rank("low"), 3)

    def test_update_to_brand_new_score_triggers_rebuild(self) -> None:
        lb = Leaderboard()
        lb.add_player("a", 10.0, timestamp=1.0)
        lb.add_player("b", 20.0, timestamp=1.0)
        # Update to a score not yet in the tree
        lb.update_score("a", 99.0, timestamp=2.0)
        self.assertEqual(lb.get_rank("a"), 1)
        self.assertEqual(lb.get_rank("b"), 2)

    def test_score_reuse_after_all_players_leave_bucket(self) -> None:
        """After removing all players from a score, the score bucket stays
        (stale but harmless) and a new player at that score works fine."""
        lb = Leaderboard()
        lb.add_player("a", 50.0, timestamp=1.0)
        lb.add_player("b", 100.0, timestamp=1.0)
        lb.remove_player("a")
        lb.add_player("c", 50.0, timestamp=2.0)
        self.assertEqual(lb.get_rank("b"), 1)
        self.assertEqual(lb.get_rank("c"), 2)

    def test_float_scores(self) -> None:
        lb = Leaderboard()
        lb.add_player("x", 3.14, timestamp=1.0)
        lb.add_player("y", 2.71, timestamp=1.0)
        lb.add_player("z", 1.41, timestamp=1.0)
        self.assertEqual(lb.get_rank("x"), 1)
        self.assertEqual(lb.get_rank("y"), 2)
        self.assertEqual(lb.get_rank("z"), 3)


class TestLeaderboardIntegration(unittest.TestCase):
    """End-to-end integration scenarios."""

    def test_full_workflow(self) -> None:
        """Add → update → remove → re-add cycle."""
        lb = Leaderboard()
        lb.add_player("alice", 100.0, timestamp=1.0)
        lb.add_player("bob", 90.0, timestamp=2.0)
        lb.add_player("carol", 80.0, timestamp=3.0)
        # carol gets a big score boost
        lb.update_score("carol", 150.0, timestamp=4.0)
        self.assertEqual(lb.get_rank("carol"), 1)
        self.assertEqual(lb.get_rank("alice"), 2)
        self.assertEqual(lb.get_rank("bob"), 3)
        # bob leaves
        lb.remove_player("bob")
        self.assertEqual(len(lb), 2)
        self.assertEqual(lb.get_rank("alice"), 2)
        # bob comes back
        lb.add_player("bob", 200.0, timestamp=10.0)
        self.assertEqual(lb.get_rank("bob"), 1)

    def test_leaderboard_single_player_throughout(self) -> None:
        lb = Leaderboard()
        lb.add_player("solo", 50.0, timestamp=1.0)
        self.assertEqual(lb.get_rank("solo"), 1)
        self.assertEqual(lb.kth_highest(1)[0], "solo")
        top = lb.get_top_k(5)
        self.assertEqual(len(top), 1)
        lb.update_score("solo", 75.0, timestamp=2.0)
        self.assertEqual(lb.get_rank("solo"), 1)
        lb.remove_player("solo")
        self.assertEqual(len(lb), 0)

    def test_add_remove_add_same_player(self) -> None:
        lb = Leaderboard()
        lb.add_player("p", 10.0, timestamp=1.0)
        lb.remove_player("p")
        lb.add_player("p", 20.0, timestamp=2.0)
        self.assertEqual(lb.get_rank("p"), 1)
        self.assertEqual(len(lb), 1)

    def test_ranking_stability_under_many_updates(self) -> None:
        """Repeatedly updating scores should keep ranks consistent."""
        lb = Leaderboard()
        scores = {"a": 10.0, "b": 20.0, "c": 30.0, "d": 5.0}
        for pid, s in scores.items():
            lb.add_player(pid, s, timestamp=1.0)
        # Raise "d" to the top
        lb.update_score("d", 100.0, timestamp=2.0)
        self.assertEqual(lb.get_rank("d"), 1)
        self.assertEqual(lb.get_rank("c"), 2)
        # Lower "d" to the bottom
        lb.update_score("d", 1.0, timestamp=3.0)
        self.assertEqual(lb.get_rank("c"), 1)
        self.assertEqual(lb.get_rank("d"), 4)

    def test_get_top_k_after_multiple_updates(self) -> None:
        lb = Leaderboard()
        for i in range(10):
            lb.add_player(f"p{i}", float(i), timestamp=float(i))
        # Promote p0 to the top
        lb.update_score("p0", 100.0, timestamp=99.0)
        top = lb.get_top_k(3)
        self.assertEqual(top[0][0], "p0")
        self.assertEqual(top[0][2], 1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main(verbosity=2)
