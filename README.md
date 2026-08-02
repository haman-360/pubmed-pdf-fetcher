# PubMed PDF Downloader

PMIDリストから論文メタデータを取得し、合法的に公開されているPDFだけを自動保存するCLIツールです。

## できること

- `input/pmids.txt`、Google Docsからコピーした文章、または `.docx` に含まれるPMIDから、NCBI E-utilitiesでメタデータを取得
- PMCIDがある論文は PubMed Central の公開PDFと公式OAパッケージからの取得を試行
- DOIがある論文は Unpaywall API と Europe PMC API でOA PDF URLを検索
- Unpaywallの最優先URLが失敗した場合も、残りのOA PDF候補を順に試行
- 一部出版社の既知の正規PDF URLと、出版社ページが標準メタデータで明示するPDF URLを試行
- PubMedのメタデータにPIIが含まれる場合は、出版社PDF候補の生成にも利用
- 取得できたPDFを `pdf/` に保存
- `pdf/` に手動保存したPDFをPMID・DOI・タイトルで照合し、CSVへ取得済みとして反映
- 照合できたPDF名を `PMID_約10語のタイトルキーワード.pdf` に統一
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

`manual_check.csv` は手動取得の見込みが高い順に並びます。PubMed LinkOutが
`free resource` と示す論文、PMCIDがある論文、出版社の既知PDF URLがある論文について、
優先度、判定根拠、ブラウザで開くURLを記録します。`not_found.csv` にも最優先の手動確認URLを残します。

## 手動ダウンロードしたPDFを同期する

ブラウザで取得したPDFを `pdf/` フォルダへ入れ、`run_sync_pdf_library.command` を
ダブルクリックします。PDFのファイル名と先頭ページからPMID、DOI、PMCID、PII、タイトルを照合し、
次の処理を行います。

- ファイル名を `PMID_約10語のタイトルキーワード.pdf` に変更
- `metadata.csv` に `pdf_status=available` とPDF名・照合方法を記録
- 取得済みPMIDを `not_found.csv` と `manual_check.csv` から削除
- `history.csv` に `synced_existing` として追記

確実に照合できないPDFや、改名先と衝突するPDFは変更せず、実行画面に `Unmatched` と表示します。
通常の `run_pubmed_pdf_downloader.command` 実行時にも、ダウンロード開始前に同じ同期処理を行います。

ターミナルから同期だけ実行する場合:

```bash
python -m src.main --sync-library
```

## Google Docsから簡単に実行する

Google Docs APIの認証設定は不要です。Google Document内に `PMID: 31452104`、PubMed URL、またはPMIDだけの行が含まれていれば利用できます。

1. Google Documentを開き、対象範囲（または全文）をコピー
2. `run_from_clipboard.command` をダブルクリック
3. 抽出されたPMIDのメタデータ取得とPDF探索がそのまま始まる

初回のみ実行権限を付けます。

```bash
chmod +x run_from_clipboard.command
```

ターミナルから実行する場合:

```bash
python -m src.main --clipboard
```

Google Docsから「Microsoft Word（.docx）」でダウンロードしたファイルも直接指定できます。

```bash
python -m src.main ~/Downloads/pubmed-abstract.docx
```

年、ページ番号、DOI中の数字などをPMIDと誤認しないよう、任意の数字列は取り込みません。PMIDは次のいずれかの形式にしてください。

```text
PMID: 31452104
https://pubmed.ncbi.nlm.nih.gov/30049270/
42055088
```

重複するPMIDは最初の出現だけを使用します。

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
- 現在、出版社PDF候補として Wiley Online Library、Hogrefe、Gastrojournal / ScienceDirect 系の正規PDF URLを試行します。
- それ以外の出版社でも、論文ページに `citation_pdf_url` などの標準的なPDFメタデータがあり、認証なしで実際のPDFが返る場合は保存します。
- PubMedにOpen accessやFree full textの表示があっても、APIからPDF直リンクが得られない場合があります。その場合は出版社候補URLを試し、PDFではなくHTML、CAPTCHA、ログイン画面が返った場合は自動保存しません。
- 有料論文、所属機関ログイン、出版社サイトの認証が必要なPDFは取得しません。
- 出版社サイトでCAPTCHA、画像選択クイズ、ログイン確認が出る場合は自動取得しません。その場合は `output/manual_check.csv` のURLをブラウザで開き、手動で確認してください。
- 認証回避やスクレイピングによるPDF取得は行いません。
- 大量アクセスを避けるため、月5〜10件程度の利用を想定しています。
- NCBI E-utilitiesの利用では、必要に応じて `NCBI_API_KEY` を環境変数に設定できます。
- NCBIの推奨に沿って連絡先を送信する場合は、`NCBI_EMAIL` を環境変数に設定できます。未設定時は `UNPAYWALL_EMAIL` を利用します。

```bash
export NCBI_API_KEY="your-ncbi-api-key"
export NCBI_EMAIL="your-email@example.com"
```

一時的な通信エラーは自動再試行します。PDFは `.part` ファイルへ一時保存し、ダウンロード完了後にだけ正式なファイル名へ切り替えるため、中断したファイルを取得済みと誤認しません。
