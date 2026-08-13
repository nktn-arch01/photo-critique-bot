# Phase D オフライン fixture（画像不要）

API／JPEG なしで、人物分岐・時間帯禁止の**再発防止**を固めるテキストです。

| ファイル | 期待 |
|----------|------|
| `person_pass_phase1.txt` | 人物あり → PASS |
| `no_person_pass_phase1.txt` | 人物なし → PASS（観る者の視線は可） |
| `no_person_fail_anthropomorph.txt` | 人物なしへの擬人化 → FAIL |
| `time_ban_fail_phase1.txt` | 時間帯ラベル → FAIL |

実 API 再評価は従来どおり `scripts/phase_d_eval.py`（画像を `eval/phase_d/images/` に配置）。
