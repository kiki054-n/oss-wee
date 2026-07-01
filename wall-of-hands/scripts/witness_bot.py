#!/usr/bin/env python3
"""
witness_bot.py
Wall of Hands — GitHub Issue/PRコメントを Witness署名のUIとして流用する仕組み。

流れ:
  1. 「Grip」Issue Formでissueを作成する = Reachへの測定イベントを宣言する（provisional=true）
  2. 当事者(from/to)以外のHandが `/witness hand:xxxx` とコメントする
  3. 本スクリプトがコメント投稿者の実GitHubアカウントを hands-github-map.json と突き合わせ、
     なりすましでないこと・当事者でないことを確認する
  4. 有効なWitnessが1名以上そろった時点でGripを確定（provisional=false）し、
     wall-of-hands/data/wall.jsonl に不変の1行として追記する

新しい椅子（専用サーバーやDB）を作らず、GitHubのIssue/PR機能をそのままWallとして使う設計。
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "wall-of-hands" / "data"
GRIPS_DIR = DATA_DIR / "grips"
WALL_FILE = DATA_DIR / "wall.jsonl"
HANDS_MAP_FILE = REPO_ROOT / "wall-of-hands" / "hands-github-map.json"

WITNESS_PATTERN = re.compile(r"/witness\s+(hand:[a-zA-Z0-9_-]+)")


class WitnessError(Exception):
    pass


def load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_hands_map() -> dict:
    data = load_json(HANDS_MAP_FILE)
    return {k: v for k, v in data.items() if not k.startswith("_")}


def parse_issue_form_body(body: str) -> dict:
    """
    GitHub Issue Formは本文を
        ### ラベル

        値

        ### 次のラベル
        ...
    という形式でレンダリングする。これをdictに変換する。
    """
    sections = re.split(r"^###\s+", body, flags=re.MULTILINE)
    parsed = {}
    for section in sections[1:]:
        lines = section.strip().splitlines()
        if not lines:
            continue
        label = lines[0].strip().lower()
        value = "\n".join(lines[1:]).strip()
        if value == "_No response_":
            value = ""
        key_map = {
            "reach id": "reach_id",
            "from hand id": "from_hand",
            "to hand id": "to_hand",
            "occurred at (iso 8601)": "occurred_at",
            "outcome": "outcome",
            "evidence": "evidence",
        }
        key = key_map.get(label, label.replace(" ", "_"))
        parsed[key] = value
    return parsed


def grip_record_path(issue_number: int) -> Path:
    return GRIPS_DIR / f"grip-issue-{issue_number}.json"


def load_or_init_grip_record(issue_number: int, issue_body: dict) -> dict:
    path = grip_record_path(issue_number)
    if path.exists():
        return load_json(path)
    record = {
        "grip_id": f"grip:issue-{issue_number}",
        "reach_id": issue_body.get("reach_id", ""),
        "from": issue_body.get("from_hand", ""),
        "to": issue_body.get("to_hand", ""),
        "occurred_at": issue_body.get("occurred_at", ""),
        "outcome": issue_body.get("outcome", ""),
        "evidence": issue_body.get("evidence", ""),
        "witnesses": [],
        "provisional": True,
        "finalized_at": None,
    }
    return record


def save_grip_record(record: dict) -> None:
    GRIPS_DIR.mkdir(parents=True, exist_ok=True)
    issue_number = record["grip_id"].split("-")[-1]
    path = grip_record_path(int(issue_number))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(record, f, ensure_ascii=False, indent=2)
        f.write("\n")


def append_to_wall(record: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "wall_id": f"wall:{record['grip_id']}",
        "grip_id": record["grip_id"],
        "reach_id": record["reach_id"],
        "outcome": record["outcome"],
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "immutable": True,
    }
    with open(WALL_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def validate_witness(
    comment_author_login: str,
    claimed_hand_id: str,
    hands_map: dict,
    reach_from: str,
    reach_to: str,
) -> tuple[bool, str]:
    registered_hand = hands_map.get(comment_author_login)
    if registered_hand is None:
        return False, (
            f"@{comment_author_login} は hands-github-map.json に未登録です。"
            "Witnessとして署名する前に、PRで自分のHand IDを登録してください。"
        )
    if registered_hand != claimed_hand_id:
        return False, (
            f"@{comment_author_login} の登録済みHand ID（{registered_hand}）と、"
            f"コメントで名乗った {claimed_hand_id} が一致しません。なりすましは記録されません。"
        )
    if claimed_hand_id in (reach_from, reach_to):
        return False, "当事者(from/to)自身はこのGripのWitnessになれません。"
    return True, "OK"


def process_event(event: dict) -> dict:
    """
    GitHub Actions の issue_comment イベントを処理し、
    { "message": str, "finalized": bool } を返す。
    """
    comment_body = event["comment"]["body"]
    comment_author = event["comment"]["user"]["login"]
    issue_number = event["issue"]["number"]
    issue_body_raw = event["issue"]["body"] or ""

    match = WITNESS_PATTERN.search(comment_body)
    if not match:
        return {"message": "", "finalized": False}

    claimed_hand_id = match.group(1)
    issue_fields = parse_issue_form_body(issue_body_raw)
    record = load_or_init_grip_record(issue_number, issue_fields)

    if not record["provisional"]:
        return {
            "message": (
                f"このGripは既に確定済み（{record['outcome']}）です。"
                "過去の測定結果は書き換えられません。"
            ),
            "finalized": False,
        }

    hands_map = load_hands_map()
    ok, reason = validate_witness(
        comment_author, claimed_hand_id, hands_map, record["from"], record["to"]
    )
    if not ok:
        return {"message": f"⚠️ Witness署名を却下しました: {reason}", "finalized": False}

    if claimed_hand_id not in record["witnesses"]:
        record["witnesses"].append(claimed_hand_id)

    finalized = False
    message = f"✅ {claimed_hand_id}（@{comment_author}）のWitness署名を記録しました。"

    if len(record["witnesses"]) >= 1:
        record["provisional"] = False
        record["finalized_at"] = datetime.now(timezone.utc).isoformat()
        append_to_wall(record)
        finalized = True
        message += (
            f"\n\n🔒 Witnessが確定したため、このGripは **{record['outcome']}** として"
            "収縮しました。Wallに追記済みです。このIssueをクローズします。"
        )

    save_grip_record(record)
    return {"message": message, "finalized": finalized}


def main():
    if len(sys.argv) != 2:
        print("使い方: witness_bot.py <GITHUB_EVENT_PATH>", file=sys.stderr)
        sys.exit(1)

    event = load_json(Path(sys.argv[1]))
    result = process_event(event)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            # コメント本文は改行を含みうるので、GitHub Actionsのマルチライン構文を使う
            f.write(f"message<<EOF\n{result['message']}\nEOF\n")
            f.write(f"finalized={'true' if result['finalized'] else 'false'}\n")
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
