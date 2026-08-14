"""Lumina Notes Console（開発確認用）の表層コピー。

正本の合意: docs/P2_2_PHASE1_COPY_PROPOSALS.md
公開 Guided UI は短い説明のみ。Console は段チェックと開発用の補足説明を残す。
"""

from __future__ import annotations

from library_unit import works_placement_guide_text

# --- A: 短いラベル ---
TAB_SELECT = " 選ぶ "
TAB_NOTES = " 対話ノート作成 "
FRAME_HELP = " 説明 "
FRAME_FOLDER = " 対象フォルダ "
FRAME_PROCESS = " 選ぶプロセス "
STAGE_M1 = "残す (M1)"
STAGE_M2 = "見返す (M2)"
STAGE_M3 = "言葉にする (M3)"
DRY_RUN = "試行（JPEGには記録しない）"
BTN_START_SELECT = "選ぶプロセス開始"
FRAME_CARDS = " 対話カード "
BTN_MAKE_CARD = "対話カード作成"
BTN_START_NOTES = "対話ノート作成"
FRAME_LOG = " 実行ログ "
WINDOW_TITLE = "Lumina Notes Console（開発確認）"

STAGE_LABELS = {"M1": "残す", "M2": "見返す", "M3": "言葉にする"}


def format_stage_list(stages: list[str]) -> str:
    return ", ".join(STAGE_LABELS.get(s, s) for s in stages)


def help_select_text() -> str:
    return (
        "画像を選ぶお手伝いをします。\n"
        "対象フォルダ：\n"
        "　対象とするオリジナル画像のフォルダ（月別／イベント別）を選んでください。\n"
        "選ぶプロセス：（公開版は M1,M2,M3 の選択不要・全て実行。"
        "この Console では開発確認のため段チェックを残せます）\n"
        "　残す＝撮影ミスと思われるもの以外を残す\n"
        "　見返す＝言葉にする候補を残す\n"
        "　言葉にする＝画像から読み取れる印象（気付き・感情・記憶）を言葉にする\n"
        "結果を JPEG Rating の星の数で示します\n"
        "　残す＝1、見返す＝2、印象に残る＝3、印象に強く残る＝4\n"
        "　対話ノートを作成する画像を選ぶ目安にしてください\n"
        "\n"
        "【開発確認】月の配下イベントは既定で対象外。必要なときだけ下のチェックをON。\n"
        "閉じると DxO で直した星の差分を自動記録します。\n"
        "\n"
        + works_placement_guide_text()
    )


def help_cards_text() -> str:
    return (
        "星の数3または4の画像について、タイトルと画像から読み取れる印象を記したカードを作成します。\n"
        "\n"
        "【開発確認】DxO で星を直したあとの差分は、ウィンドウを閉じるときに自動で残します"
        "（手動操作は不要）。説明欄へ TITLE / SUMMARY / SCORES / CRITIQUE_SUMMARY も書き込みます。"
    )


def help_notes_text() -> str:
    return (
        "画像から読み取れる印象（気付き・感情・記憶）を対話ノートとして残します。\n"
        "対話ノートを作成する（Worksフォルダ）に月別に保存された "
        '".jpg" または "_dev.jpg" 画像が対象です。\n'
        "対象フォルダ：\n"
        "　対話ノートを作成する画像を集めたフォルダ（月別Worksフォルダ）を選んでください。\n"
        "\n"
        "【開発確認】常にカード＋詳細ノート（【1】〜【7】）。"
        "説明に TITLE 等があるコマはカードを作り直しません（ノートは作成）。\n"
        "「選ぶ」をしていなくても、Works に画像があればここだけ使えます。"
        "ファイルのコピーはしません。\n"
        "Works は YYYYMM のみ（例: ~/2026/202606）。"
        "同一コマは {stem}_dev.jpg を優先（撮って出し除外は確認時に表示）。\n"
        "\n"
        + works_placement_guide_text()
    )


# --- D ---
CONFIRM_SELECT_TITLE = "実行確認"
CONFIRM_SELECT_Q = "選ぶプロセスを始めますか？"
CONFIRM_NOTES_TITLE = "対話ノート作成"
CONFIRM_NOTES_Q = "対話ノート作成を始めますか？"
CONFIRM_CARDS_TITLE = "対話カード作成"
CONFIRM_CARDS_Q = "対話カード作成を始めますか？"

# --- E 見出し ---
DONE_SELECT = "星をつけ終わりました"
DONE_DRY = "試行が終わりました"
DONE_CANCEL = "中止しました"
DONE_INCOMPLETE = "完了しませんでした"
DONE_NOTES = "対話ノートを作成しました"
DONE_CARDS = "対話カードを作成しました"
