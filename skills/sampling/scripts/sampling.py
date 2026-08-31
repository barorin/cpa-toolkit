#!/usr/bin/env python3
"""cpa-toolkit: 監査サンプリング実行スクリプト。

サブコマンド:
  size-attr  属性サンプリングのサンプルサイズ算定(二項分布ベース)
      python sampling.py size-attr --confidence 0.90 --tolerable 0.05 --expected 0
  size-mus   MUSのサンプルサイズ算定(保証係数方式)
      python sampling.py size-mus --population 5000000000 --tolerable 100000000 \
          --expected 10000000 --factor 3.0
  mus        金額単位抽出の実行
      python sampling.py mus 母集団.csv --amount-col 金額 --n 60 --seed 20260830 --out output
  random     無作為抽出の実行
      python sampling.py random 母集団.csv --n 25 --seed 20260830 --out output

共通ルール: 抽出前に母集団の件数・合計を表示するので、呼び出し元は必ず
GL残高等と一致することを確認してから抽出結果を使うこと。
マイナス・ゼロ金額は母集団から除外し、excluded.csv に出力する。
抽出過程(パラメータ・シード・間隔)は sampling_record.md に記録される。
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")


def read_pop(path: str) -> pd.DataFrame:
    if path.lower().endswith((".xlsx", ".xls")):
        try:
            return pd.read_excel(path)
        except ImportError:
            raise SystemExit("Excel読込には openpyxl が必要です: pip install openpyxl")
    for enc in ("utf-8-sig", "cp932", "utf-8"):
        try:
            return pd.read_csv(path, encoding=enc)
        except UnicodeDecodeError:
            continue
    raise SystemExit(f"読込失敗(文字コード): {path}")


def attr_size(confidence: float, tolerable: float, expected: float) -> int:
    """許容逸脱率tolerableのもとで信頼水準confidenceを満たす最小n(予想逸脱expected)。"""
    try:
        from scipy import stats
    except ImportError:
        raise SystemExit("size-attr には scipy が必要です: pip install scipy")
    if expected >= tolerable:
        raise SystemExit("予想逸脱率が許容逸脱率以上です。サンプリングは適用できません。")
    for n in range(1, 20001):
        k = int(np.floor(expected * n))
        if stats.binom.cdf(k, n, tolerable) <= 1 - confidence:
            return n
    raise SystemExit("n>20000でも満たせません。パラメータを見直してください。")


def mus_size(population: int, tolerable: int, expected: int, factor: float) -> int:
    if tolerable <= expected:
        raise SystemExit("許容誤謬が予想誤謬以下です。")
    return int(np.ceil(population * factor / (tolerable - expected)))


def prep(df: pd.DataFrame, amount_col: str | None, out: str):
    os.makedirs(out, exist_ok=True)
    if amount_col:
        if "_amt" in df.columns:
            raise SystemExit("入力に「_amt」列があるため処理できません(内部で予約している列名)。列名を変更してください。")
        df = df.copy()
        df["_amt"] = (
            pd.to_numeric(df[amount_col].astype(str).str.replace(",", ""), errors="coerce").fillna(0).round().astype("int64")
        )
        excluded = df[df["_amt"] <= 0]
        if len(excluded):
            excluded.drop(columns=["_amt"]).to_csv(os.path.join(out, "excluded.csv"), index=False, encoding="utf-8-sig")
        df = df[df["_amt"] > 0].reset_index(drop=True)
        print(f"母集団(除外後): {len(df)}件 / 合計 {int(df['_amt'].sum()):,}(除外 {len(excluded)}件)")
    else:
        print(f"母集団: {len(df)}件")
    return df


def record(out: str, lines: list[str]):
    with open(os.path.join(out, "sampling_record.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(["# 抽出記録", ""] + lines))


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("size-attr")
    p.add_argument("--confidence", type=float, required=True)
    p.add_argument("--tolerable", type=float, required=True)
    p.add_argument("--expected", type=float, default=0.0)

    p = sub.add_parser("size-mus")
    p.add_argument("--population", type=int, required=True)
    p.add_argument("--tolerable", type=int, required=True)
    p.add_argument("--expected", type=int, default=0)
    p.add_argument("--factor", type=float, required=True, help="保証係数(例: 高3.0/中2.3/低1.5)")

    for name in ("mus", "random"):
        p = sub.add_parser(name)
        p.add_argument("input")
        p.add_argument("--n", type=int, required=True)
        p.add_argument("--seed", type=int, required=True)
        p.add_argument("--out", default="output")
        p.add_argument("--amount-col", default=None, required=(name == "mus"))

    a = ap.parse_args()

    if a.cmd == "size-attr":
        n = attr_size(a.confidence, a.tolerable, a.expected)
        print(f"属性サンプルサイズ: {n}件(信頼水準{a.confidence:.0%}, 許容{a.tolerable:.1%}, 予想{a.expected:.1%})")
        return
    if a.cmd == "size-mus":
        n = mus_size(a.population, a.tolerable, a.expected, a.factor)
        print(f"MUSサンプルサイズ: {n}件(母集団{a.population:,}, 許容{a.tolerable:,}, 予想{a.expected:,}, 係数{a.factor})")
        return

    df = prep(read_pop(a.input), a.amount_col, a.out)
    rng = np.random.default_rng(a.seed)

    if a.cmd == "random":
        if a.n > len(df):
            raise SystemExit("nが母集団件数を超えています。")
        sample = df.sample(n=a.n, random_state=int(rng.integers(0, 2**31)))
        sample = sample.drop(columns=["_amt"], errors="ignore")
        sample.to_csv(os.path.join(a.out, "sample_list.csv"), index=False, encoding="utf-8-sig")
        record(a.out, [f"- 手法: 無作為抽出 / n={a.n} / seed={a.seed}", f"- 母集団: {len(df)}件", f"- 入力: {a.input}"])
        print(f"抽出完了: {a.n}件 -> {a.out}/sample_list.csv")
        return

    # MUS
    total = int(df["_amt"].sum())
    interval = total // a.n
    if interval == 0:
        raise SystemExit("抽出間隔が0です。nが大きすぎます。")
    start = int(rng.integers(1, interval + 1))
    cum = df["_amt"].cumsum()
    points = np.arange(start, total + 1, interval)[: a.n]
    idx = np.searchsorted(cum.values, points, side="left")
    picked = sorted(set(int(i) for i in idx))
    sample = df.iloc[picked].copy()
    sample["_特定項目"] = sample["_amt"] >= interval
    sample.rename(columns={"_amt": "_金額(検証用)", "_特定項目": "特定項目(間隔以上)"}).to_csv(
        os.path.join(a.out, "sample_list.csv"), index=False, encoding="utf-8-sig"
    )
    record(
        a.out,
        [
            f"- 手法: 金額単位抽出(MUS) / n={a.n}(選定 {len(picked)}件・重複統合後) / seed={a.seed}",
            f"- 母集団: {len(df)}件 / 合計 {total:,} / 入力: {a.input}",
            f"- 抽出間隔: {interval:,} / 開始点: {start:,}",
            f"- 特定項目(間隔以上で必然選定): {int(sample['_特定項目'].sum())}件",
        ],
    )
    print(f"抽出完了: {len(picked)}件 -> {a.out}/sample_list.csv(間隔 {interval:,}, 開始点 {start:,})")


if __name__ == "__main__":
    main()
