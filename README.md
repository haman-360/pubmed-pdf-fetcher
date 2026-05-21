# PubMed PDF Downloader

PMIDリストから論文メタデータを取得し、合法的に公開されているPDFだけを自動保存するCLIツールです。

## できること

- `input/pmids.txt` に書いたPMIDから、NCBI E-utilitiesでメタデータを取得
- PMCIDがある論文は PubMed Central の公開PDF取得を試行
- DOIがある論文は Unpaywall API と Europe PMC API でOA PDF URLを検索
- 一部出版社については、認証不要でPDFとして返る既知の正規PDF URLだけを試行
- PubMedのメタデータにPIIが含まれる場合は、出版社PDF候補の生成にも利用
- 取得できたPDFを `pdf/` に保存
- 全論文のメタデータを `output/metadata.csv` に出力
- 取得できなかった論文を `output/not_found.csv` に出力

## セットアップ

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Mac標準PythonではSSLライブラリの都合で警告が出ることがあるため、`urllib3<2` を指定しています。

## Unpaywall API用メールアドレス

Unpaywall APIはリクエスト時にメールアドレスが必要です。環境変数で設定してください。

```bash
export UNPAYWALL_EMAIL="your-email@example.com"
```

毎回設定したくない場合は、利用しているシェルの設定ファイルに追記します。

```bash
echo 'export UNPAYWALL_EMAIL="your-email@example.com"' >> ~/.zshrc
source ~/.zshrc
```

メールアドレス未設定でもツールは動きますが、その場合はUnpaywall検索をスキップします。

## 使い方

`input/pmids.txt` にPMIDを1行1件で入力します。

```text
31452104
30049270
```

`#` で始まる行は無視されます。取得済みや、今回は再試行しないPMIDはコメントアウトして管理できます。

```text
# done: 42055592
# not_found_2026-05-21: 42068093
42055088
42017769
```

未取得だった論文でも、後日 Unpaywall や Europe PMC にPDFリンクが追加されることがあります。再確認したい場合は、先頭の `#` を外してもう一度実行してください。

実行します。

```bash
python -m src.main input/pmids.txt
```

Macでダブルクリック実行したい場合は、初回のみ実行権限を付けます。

```bash
chmod +x run_pubmed_pdf_downloader.command
```

その後、`run_pubmed_pdf_downloader.command` をダブルクリックすると、仮想環境の作成、依存ライブラリのインストール、PDF取得まで実行されます。

出力先:

- PDF: `pdf/`
- メタデータ: `output/metadata.csv`
- 未取得リスト: `output/not_found.csv`
- 手動確認用URL: `output/manual_check.csv`
- 実行履歴: `output/history.csv`

`history.csv` は実行ごとに追記されます。PMIDとタイトルを見比べやすいように、以下の列を保存します。

- `date`: 実行日時
- `status`: `downloaded`、`already_exists`、`not_found`
- `PMID`
- `title`
- `pdf_file`
- `source`
- `url`
- `reason`

## 注意点

- このツールは、PubMed Central、Unpaywall、Europe PMC、または認証不要でPDFとして返る出版社の正規PDF URLから取得します。
- 現在、出版社PDF候補として Wiley Online Library の `https://onlinelibrary.wiley.com/doi/epdf/{DOI}` 形式、Gastrojournal / ScienceDirect 系のPIIベースPDF URLを試行します。
- PubMedにOpen accessやFree full textの表示があっても、APIからPDF直リンクが得られない場合があります。その場合は出版社候補URLを試し、PDFではなくHTML、CAPTCHA、ログイン画面が返った場合は自動保存しません。
- 有料論文、所属機関ログイン、出版社サイトの認証が必要なPDFは取得しません。
- 出版社サイトでCAPTCHA、画像選択クイズ、ログイン確認が出る場合は自動取得しません。その場合は `output/manual_check.csv` のURLをブラウザで開き、手動で確認してください。
- 認証回避やスクレイピングによるPDF取得は行いません。
- 大量アクセスを避けるため、月5〜10件程度の利用を想定しています。
- NCBI E-utilitiesの利用では、必要に応じて `NCBI_API_KEY` を環境変数に設定できます。

```bash
export NCBI_API_KEY="your-ncbi-api-key"
```
