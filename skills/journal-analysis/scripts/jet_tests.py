#!/usr/bin/env python3
"""cpa-toolkit: 仕訳テスト(JET)標準テスト実行スクリプト。

使い方:
  python jet_tests.py 仕訳.csv --colmap colmap.json --fiscal-end 2026-03-31 \
      --tests A,B1,B2,C1,C3,D2,D3,D4,E1 --materiality 50000000 \
      --revenue-prefixes 41,42 --out output

colmap.json は「論理名→実データの列名」の対応表。存在するキーに応じて
実行可能なテストが決まる(足りないテストはスキップして報告される)。
  必須: entry_id(伝票番号), date(計上日), account(勘定科目),
        debit(借方金額), credit(貸方金額)
  任意: entry_datetime(入力日時), entry_date(入力日), description(摘要),
        preparer(起票者), approver(承認者), manual_flag(手入力フラグ),
        account_code(勘定コード)

出力: <out>/A_completeness.md と、テスト別の抽出CSV(0件でも作る)、
      <out>/summary.json(全テストの件数一覧)。
金額は円単位の整数に丸めて処理する(浮動小数点誤差の回避)。
"""
import argparse
import json
import os
import sys

import numpy as np
import pandas as pd

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

VAGUE_WORDS = ["調整", "その他", "修正", "仮", "訂正"]
REQUIRED_COLS = ("entry_id", "date", "account", "debit", "credit")
OPTIONAL_COLS = ("entry_datetime", "entry_date", "description", "preparer", "approver", "manual_flag", "account_code")


def load(path: str, colmap: dict) -> pd.DataFrame:
    missing = [k for k in REQUIRED_COLS if k not in colmap]
    if missing:
        raise SystemExit(f"colmapに必須キーがありません: {', '.join(missing)}")
    unknown = [k for k in colmap if k not in REQUIRED_COLS + OPTIONAL_COLS]
    if unknown:
        raise SystemExit(f"colmapに未知のキーがあります: {', '.join(unknown)}(使用可能: {', '.join(REQUIRED_COLS + OPTIONAL_COLS)})")
    if path.lower().endswith((".xlsx", ".xls")):
        try:
            raw = pd.read_excel(path)
        except ImportError:
            raise SystemExit("Excel読込には openpyxl が必要です: pip install openpyxl")
    else:
        for enc in ("utf-8-sig", "cp932", "utf-8"):
            try:
                raw = pd.read_csv(path, encoding=enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            raise SystemExit(f"読込失敗(文字コード): {path}")
    df = pd.DataFrame()
    for logical, actual in colmap.items():
        if actual not in raw.columns:
            raise SystemExit(f"colmap指定の列が存在しません: {logical} -> {actual}(実列: {list(raw.columns)})")
        df[logical] = raw[actual]
    for col in ("debit", "credit"):
        df[col] = (
            pd.to_numeric(df[col].astype(str).str.replace(",", "").replace({"nan": "0", "": "0"}), errors="coerce")
            .fillna(0)
            .round()
            .astype("int64")
        )
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ("entry_datetime", "entry_date"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    df["amount"] = df[["debit", "credit"]].max(axis=1)
    return df


def completeness(df: pd.DataFrame, out: str) -> list[str]:
    lines = ["# A. 完全性チェック", ""]
    d, c = int(df["debit"].sum()), int(df["credit"].sum())
    lines.append(f"- A1 貸借一致(全体): 借方 {d:,} / 貸方 {c:,} / 差額 {d - c:,}")
    bal = df.groupby("entry_id")[["debit", "credit"]].sum()
    bad = bal[bal["debit"] != bal["credit"]]
    lines.append(f"- A1 貸借一致(伝票単位): 不一致 {len(bad)} 伝票")
    if len(bad):
        bad.to_csv(os.path.join(out, "A1_unbalanced_entries.csv"), encoding="utf-8-sig")
    monthly = df.set_index("date").resample("ME")["amount"].agg(["count", "sum"])
    lines.append("- A2 月別件数・金額:")
    for idx, row in monthly.iterrows():
        lines.append(f"  - {idx:%Y-%m}: {int(row['count'])}件 / {int(row['sum']):,}")
    nadate = int(df["date"].isna().sum())
    lines.append(f"- A3 日付不正(パース不能): {nadate}件 / 金額欠損は0円化済み")
    lines.append(f"- A3 伝票番号の欠損: {int(df['entry_id'].isna().sum())}件")
    with open(os.path.join(out, "A_completeness.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return lines


def run_tests(df: pd.DataFrame, args: argparse.Namespace, out: str) -> dict:
    results = {}

    def save(name: str, sub: pd.DataFrame):
        sub.to_csv(os.path.join(out, f"{name}.csv"), index=False, encoding="utf-8-sig")
        results[name] = len(sub)

    tests = set(t.strip().upper() for t in args.tests.split(","))
    fiscal_end = pd.Timestamp(args.fiscal_end) if args.fiscal_end else None
    if "manual_flag" in df:
        manual = df["manual_flag"].astype(str).str.strip().isin(["1", "True", "TRUE", "手入力", "有"])
    else:
        manual = pd.Series(True, index=df.index)
        if tests & {"B1", "D2"}:
            results["NOTE_manual_flag"] = "manual_flag列なし: B1/D2は全仕訳を対象(手入力の絞り込みなし)"

    if "B1" in tests:
        if fiscal_end is None:
            results["B1_SKIP"] = "fiscal-end未指定"
        else:
            win = (df["date"] >= fiscal_end - pd.Timedelta(days=args.period_end_days)) & (
                df["date"] <= fiscal_end + pd.Timedelta(days=args.period_end_days)
            )
            save("B1_period_end", df[win & manual])
    if "B2" in tests:
        ts = df["entry_datetime"] if "entry_datetime" in df else None
        base = ts if ts is not None else (df["entry_date"] if "entry_date" in df else df["date"])
        flag = base.dt.dayofweek >= 5
        try:
            import jpholiday  # type: ignore

            flag = flag | base.dt.date.map(lambda x: bool(x and jpholiday.is_holiday(x)))
        except ImportError:
            results["B2_NOTE"] = "jpholiday未導入のため祝日判定は土日のみ"
        if ts is not None:
            flag = flag | (ts.dt.hour >= 22) | (ts.dt.hour < 5)
        save("B2_holiday_night", df[flag.fillna(False)])
    if "B3" in tests:
        if "entry_date" in df or "entry_datetime" in df:
            ed = (df["entry_datetime"] if "entry_datetime" in df else df["entry_date"]).dt.normalize()
            save("B3_late_entry", df[(ed - df["date"]).dt.days > args.backdate_days])
        else:
            results["B3_SKIP"] = "entry_date/entry_datetime列なし"
    if "C1" in tests:
        big = df["amount"] >= args.round_min
        save("C1_round_numbers", df[big & (df["amount"] % 10000 == 0)])
    if "C2" in tests:
        if args.materiality:
            m = args.materiality
            save("C2_near_materiality", df[(df["amount"] >= m * 0.9) & (df["amount"] < m)])
        else:
            results["C2_SKIP"] = "materiality未指定"
    if "C3" in tests:
        save("C3_top_amounts", df.nlargest(args.top_n, "amount"))
    if "C4" in tests:
        pop = df[df["amount"] > 0]["amount"]
        if len(pop) < 1000:
            results["C4_SKIP"] = f"母集団{len(pop)}件は目安1,000件未満"
        else:
            first = pop.astype(str).str[0].astype(int)
            obs = first.value_counts().reindex(range(1, 10), fill_value=0)
            exp = np.log10(1 + 1 / np.arange(1, 10)) * len(pop)
            chi2 = float((((obs - exp) ** 2) / exp).sum())
            pd.DataFrame({"digit": range(1, 10), "observed": obs.values, "expected": exp.round(1)}).to_csv(
                os.path.join(out, "C4_benford.csv"), index=False, encoding="utf-8-sig"
            )
            results["C4_benford_chi2"] = round(chi2, 1)  # 自由度8: 5%有意水準の目安 15.51
    if "D1" in tests:
        acc = df.groupby("entry_id")["account"].apply(lambda s: " / ".join(sorted(set(s.astype(str)))))
        freq = acc.value_counts()
        rare_ids = acc[acc.isin(freq[freq <= args.rare_combo_max].index)].index
        save("D1_rare_combos", df[df["entry_id"].isin(rare_ids)])
    if "D2" in tests:
        if args.revenue_prefixes:
            prefixes = tuple(p.strip() for p in args.revenue_prefixes.split(","))
            key = df["account_code"].astype(str) if "account_code" in df else df["account"].astype(str)
            rev_ids = df[key.str.startswith(prefixes)]["entry_id"].unique()
            save("D2_revenue_manual", df[df["entry_id"].isin(rev_ids) & manual])
        else:
            results["D2_SKIP"] = "revenue-prefixes未指定"
    if "D3" in tests:
        sig = df.groupby("entry_id").agg(
            total=("debit", "sum"), accs=("account", lambda s: frozenset(s.astype(str))), d=("date", "first")
        )
        sig = sig[sig["total"] > 0]
        pairs = []
        for (total, accs), grp in sig.groupby(["total", "accs"], sort=False):
            if len(grp) >= 2 and (grp["d"].max() - grp["d"].min()).days <= args.reversal_window:
                pairs.extend(grp.index.tolist())
        save("D3_reversal_pairs", df[df["entry_id"].isin(pairs)])
    if "D4" in tests:
        if "description" in df:
            desc = df["description"].astype(str).str.strip()
            vague = desc.isin(["", "nan"]) | desc.apply(lambda x: any(x == w or x == w + "分" for w in VAGUE_WORDS))
            save("D4_vague_description", df[vague & (df["amount"] >= args.round_min)])
        else:
            results["D4_SKIP"] = "description列なし"
    if "E1" in tests:
        if "preparer" in df and "approver" in df:
            save("E1_same_preparer_approver", df[df["preparer"].astype(str) == df["approver"].astype(str)])
        else:
            results["E1_SKIP"] = "preparer/approver列なし"

    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--colmap", required=True, help="論理名→列名のJSONファイル")
    ap.add_argument("--tests", default="B1,B2,B3,C1,C2,C3,C4,D1,D2,D3,D4,E1")
    ap.add_argument("--fiscal-end", default=None)
    ap.add_argument("--materiality", type=int, default=0)
    ap.add_argument("--revenue-prefixes", default="", help="収益勘定のコード/名称の接頭辞(カンマ区切り)")
    ap.add_argument("--period-end-days", type=int, default=7)
    ap.add_argument("--backdate-days", type=int, default=30)
    ap.add_argument("--round-min", type=int, default=1_000_000)
    ap.add_argument("--top-n", type=int, default=50)
    ap.add_argument("--rare-combo-max", type=int, default=2)
    ap.add_argument("--reversal-window", type=int, default=60)
    ap.add_argument("--out", default="output")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    with open(args.colmap, encoding="utf-8") as f:
        colmap = json.load(f)
    df = load(args.input, colmap)
    completeness(df, args.out)
    results = run_tests(df, args, args.out)
    summary = {"input": args.input, "rows": len(df), "entries": int(df["entry_id"].nunique()), "results": results}
    with open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
