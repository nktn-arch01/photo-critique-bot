# Guided 光方位の上限つき評価

朝夕の逆転が無いことを機械判定する。プロンプトを合格まで自動で書き換え続けない。

## オフライン（API 0回）

```bash
python3 test_offline_suite.py
python3 scripts/prompt_eval.py
```

見本: `eval/prompt_eval/fixtures/`（東なのに夕暮れが混ざる文は FAIL）。

## 実 API（任意・最大3回）

Phase 1 のみ。`temperature=0`。同じ条件はキャッシュ。

```bash
python3 scripts/prompt_eval.py --live --max-calls 3 --image path/to/P02.jpg
```

案は最大3つ（`guided_web/light_prompt_variants.py`）。GitHub CI では呼ばない。
