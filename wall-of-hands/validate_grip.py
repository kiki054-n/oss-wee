#!/usr/bin/env python3
"""
validate_grip.py
Wall of Hands — WAVE -> GRIP -> COLLAPSE の状態遷移を検証する最小実装。

設計原則(README.md参照):
  1. WAVE状態のReachは信用スコアの計算に使わない。
  2. Collapseは一方向のみ。一度確定したBond/Breachは書き換えない。
  3. Witnessが不在のGripは provisional として区別し、
     時効(既定30日)を過ぎるまでは集計に算入しない。

依存: jsonschema (pip install jsonschema --break-system-packages)
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    from jsonschema import validate as jsonschema_validate, ValidationError
except ImportError:
    print("jsonschema が見つかりません。`pip install jsonschema --break-system-packages` を実行してください。", file=sys.stderr)
    sys.exit(1)

SCHEMA_DIR = Path(__file__).parent / "schema"
PROVISIONAL_EXPIRY_DAYS = 30


def load_schema(name: str) -> dict:
    with open(SCHEMA_DIR / f"{name}.schema.json", encoding="utf-8") as f:
        return json.load(f)


class WallOfHandsError(Exception):
    pass


class ImmutabilityError(WallOfHandsError):
    """既に収縮済み(collapsed)のReachに対して再度Gripを記録しようとした場合。"""


class LedgerState:
    """
    メモリ上の簡易台帳。実運用ではGitリポジトリ上のJSONファイル群、
    または追記専用ストレージに置き換える想定。
    """

    def __init__(self):
        self.hands: dict[str, dict] = {}
        self.reaches: dict[str, dict] = {}
        self.grips: dict[str, dict] = {}
        self.wall: list[dict] = []
        self._schemas = {
            "hand": load_schema("hand"),
            "reach": load_schema("reach"),
            "grip": load_schema("grip"),
            "wall_entry": load_schema("wall_entry"),
        }

    # --- 登録系 -----------------------------------------------------

    def register_hand(self, hand: dict) -> None:
        jsonschema_validate(hand, self._schemas["hand"])
        self.hands[hand["hand_id"]] = hand

    def declare_reach(self, reach: dict) -> None:
        jsonschema_validate(reach, self._schemas["reach"])
        for role in ("from", "to"):
            if reach[role] not in self.hands:
                raise WallOfHandsError(f"未登録のHand: {reach[role]}")
        if reach["state"] != "wave":
            raise WallOfHandsError("新規Reachは必ず 'wave' 状態で宣言する。")
        self.reaches[reach["reach_id"]] = reach

    # --- 測定(収縮)系 -------------------------------------------------

    def record_grip(self, grip: dict) -> dict:
        """
        Gripを記録し、対応するReachをwave -> collapsedへ遷移させる。
        既にcollapsed済みのReachへの再Gripは拒否する(不変性の担保)。
        """
        jsonschema_validate(grip, self._schemas["grip"])

        reach = self.reaches.get(grip["reach_id"])
        if reach is None:
            raise WallOfHandsError(f"存在しないReachへのGrip: {grip['reach_id']}")
        if reach["state"] == "collapsed":
            raise ImmutabilityError(
                f"Reach {grip['reach_id']} は既に収縮済み。過去の測定結果は書き換えられない。"
            )

        # witnesses不在ならprovisional必須（schema側のallOfでも検証されるが、二重に明示）
        if len(grip["witnesses"]) == 0 and not grip["provisional"]:
            raise WallOfHandsError("Witnessが不在のGripは provisional=true でなければならない。")

        self.grips[grip["grip_id"]] = grip
        reach["state"] = "collapsed"

        # provisionalでなければ即座にWallへ追記。provisionalは集計対象外のまま保持。
        if not grip["provisional"]:
            self._append_to_wall(grip)

        return grip

    def _append_to_wall(self, grip: dict) -> None:
        entry = {
            "wall_id": f"wall:{len(self.wall) + 1:04d}",
            "grip_id": grip["grip_id"],
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "immutable": True,
        }
        jsonschema_validate(entry, self._schemas["wall_entry"])
        self.wall.append(entry)

    # --- 時効処理 -----------------------------------------------------

    def promote_expired_provisional_grips(self, now: datetime | None = None) -> list[str]:
        """
        witness不在のままPROVISIONAL_EXPIRY_DAYSを経過したGripは、
        『誰も見ていない出来事は、粒にならない』の原則に従い、
        集計対象化(Wallへの追記)を行わずに『失効』として扱う。
        （＝Bond/Breachいずれの実績にもカウントされないまま確定する）
        """
        now = now or datetime.now(timezone.utc)
        expired = []
        for grip_id, grip in self.grips.items():
            if not grip["provisional"]:
                continue
            occurred = datetime.fromisoformat(grip["occurred_at"])
            if now - occurred >= timedelta(days=PROVISIONAL_EXPIRY_DAYS):
                expired.append(grip_id)
        return expired

    # --- 集計 ---------------------------------------------------------

    def bond_rate(self, hand_id: str) -> float | None:
        """
        指定Handが 'from' として関わった収縮済みGripのうち、Bondになった割合。
        provisionalなGripは分母に含めない。
        注意: これは単独のランキング指標として使わないこと(README.md参照)。
        """
        relevant = []
        for grip in self.grips.values():
            if grip["provisional"]:
                continue
            reach = self.reaches[grip["reach_id"]]
            if reach["from"] == hand_id:
                relevant.append(grip["outcome"])
        if not relevant:
            return None
        return relevant.count("bond") / len(relevant)


def _demo():
    ledger = LedgerState()

    ledger.register_hand({
        "hand_id": "hand:kiki054-n",
        "display_name": "キキ",
        "created_at": "2026-07-02T00:00:00Z",
    })
    ledger.register_hand({
        "hand_id": "hand:someone",
        "display_name": "誰か",
        "created_at": "2026-07-02T00:00:00Z",
    })

    ledger.declare_reach({
        "reach_id": "reach:0001",
        "from": "hand:kiki054-n",
        "to": "hand:someone",
        "declared_value": "3日分の翻訳作業を貸す",
        "declared_at": "2026-07-02T00:00:00Z",
        "state": "wave",
    })

    grip = ledger.record_grip({
        "grip_id": "grip:0001",
        "reach_id": "reach:0001",
        "occurred_at": "2026-07-10T00:00:00Z",
        "outcome": "bond",
        "evidence": "成果物URL",
        "witnesses": ["hand:someone"],
        "provisional": False,
    })
    print("Grip確定:", grip["outcome"])
    print("Wall件数:", len(ledger.wall))

    # 不変性の検証: 同じReachへの再Gripは拒否される
    try:
        ledger.record_grip({
            "grip_id": "grip:0002",
            "reach_id": "reach:0001",
            "occurred_at": "2026-07-15T00:00:00Z",
            "outcome": "breach",
            "witnesses": [],
            "provisional": True,
        })
    except ImmutabilityError as e:
        print("不変性チェックOK:", e)

    print("kiki054-n のbond_rate:", ledger.bond_rate("hand:kiki054-n"))


if __name__ == "__main__":
    _demo()
