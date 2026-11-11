# CLAUDE.md — hakusan-tui

## 目的

JAIST HAKUSAN（Slurm）利用者向けの、Python + Textual製ターミナルUI `hakusan-tui` を作る。
仕様の正本は `docs/slurm.md`（設計書 v1.0）。迷ったら設計書に戻る。

## 会話・記録ルール

- 会話・ドキュメント・UI文言は日本語。
- 作業の予定と進捗は `todo.md` に書く。完了したら `[x]` にする。
- その日にやったこと・判断・ハマりどころは `work_history.md` に日付見出しで追記する（作業の区切りごとに更新）。

## 技術スタック

- Python 3.11+、パッケージ管理は **uv**（`uv sync`, `uv run ...`）。
- TUI: Textual + Rich。データモデルは dataclass（frozen）。
- Slurm連携は公式CLIを `asyncio.create_subprocess_exec(*argv)` で呼ぶ。**`shell=True` / `sh -c` にユーザー入力を連結しない**。
- テスト: pytest / pytest-asyncio / Textual Pilot。品質: ruff。

## 開発原則

- 関数・メソッドは小さく、SOLID原則に従う（1関数1責務、アダプターはProtocolで差し替え可能に）。
- UIは生のSlurm出力を直接扱わない。必ずパーサーで共通モデルへ正規化する。
- **取得できない値は `None` とし、0や推測値で埋めない**。表示は「未取得」「不明」。
- GPUは「Slurm割当」と「実使用率」を混同しない。MIG・VM分割GPUを物理GPU枚数に加算しない。複数パーティション所属ノードを重複集計しない。
- 書き込み操作（sbatch / scancel / salloc / PBS変更系）は、コマンドプレビュー → 明示確認 → 実行。他ユーザーのジョブは操作不可。`--readonly` と `--demo` では実行しない。
- ログインノードで重い処理（コンパイル・学習・nvidia-smi連打）をしない。Slurm照会はキャッシュ＋単一フライト。
- サイト固有値（パーティション上限・ノード台数）を静的コピーで判定に使わない。デモデータは「デモ」と明示する。
- 実機未確認の事項は推測で確定せず `docs/hakusan-site.md` に列挙する。

## ディレクトリ

- `src/hakusan_tui/` 本体（`adapters/` `services/` `screens/` `widgets/` `resources/`）
- `tests/unit` `tests/ui` `tests/integration`（`integration` は Docker の実Slurmで実行）
- `docker/` テスト用Slurmクラスタ（mariadb + slurmdbd + slurmctld + slurmd×2、偽GPU GRES付き）

## よく使うコマンド

```bash
uv sync
uv run hakusan-tui --demo          # Slurmなしでデモ起動
uv run pytest -q                   # 単体 + UI テスト（Slurm不要）
uv run ruff check .

# 実Slurmでの結合テスト（Docker）
docker compose -f docker/compose.yml up -d --build
docker compose -f docker/compose.yml exec ctl /work/docker/run-integration.sh
docker compose -f docker/compose.yml down -v
```

## 完了条件（抜粋）

`uv run hakusan-tui --demo`、`uv run pytest`、`uv run ruff check .` が成功し、Docker上のSlurmで
`sbatch → squeue → sacct → ログ閲覧 → scancel` の結合テストが通ること。
