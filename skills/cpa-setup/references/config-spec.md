# config.json の項目仕様

すべて任意。存在するキーだけが「設定済み」として扱われる。

```json
{
  "profile": {
    "framework_default": "日本基準",          // 既定の会計基準(日本基準/IFRS/併用)
    "engagement_types": ["法定監査", "財務DD"], // 主な業務類型
    "language": "ja"
  },
  "reporting": {
    "default_audience": "監査チーム内",        // レポートの既定想定読者
    "default_format": "docx",                // 既定の出力形式
    "unit": "千円",                           // 数値の既定単位
    "tone": "である調"
  },
  "materiality_policy": {
    "primary_benchmark": "税引前利益",
    "primary_rate": 0.05,
    "performance_materiality_rate": 0.7,
    "trivial_rate": 0.03
  },
  "jet_defaults": {                           // journal-analysis の既定閾値
    "period_end_days": 7,
    "round_min": 1000000,
    "top_n": 50,
    "revenue_prefixes": "41",
    "backdate_days": 30
  },
  "sampling_defaults": {
    "confidence": 0.90,
    "assurance_factor_high": 3.0,
    "assurance_factor_moderate": 2.3,
    "assurance_factor_low": 1.5
  },
  "templates": {                              // 事務所様式(設定フォルダ内 templates/ に保存)
    "workpaper": "templates/workpaper.docx",
    "report": null
  },
  "standards_watch": {
    "sources": ["ASBJ", "JICPA", "金融庁"],   // 巡回対象(IFRS財団の追加可)
    "focus": ["収益認識", "リース"]           // 特に関心のある領域(任意)
  }
}
```

- パスは設定フォルダ(config.json と同じ場所)からの相対パスで記録する。
- クライアント固有の設定は `clients/<クライアント名>.json` に同じ構造で保存し、既定値を上書きする形で使う。
