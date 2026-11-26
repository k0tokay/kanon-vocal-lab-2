# app：VTL の新しい GUI(作りかけ)

VocalTractLab の wxWidgets の GUI を置き換える新しい GUI．アプリ名は未定で，仮の名前は [app_core/names.py](app_core/names.py) の定数だけにある(フォルダ `app/` とパッケージ `app_core` も仮)．

いまは **第2段**：データ・操作・元に戻す・VTL の呼び出し・サーバー(第1段)に，声道ワークスペースの画面(第2段)が付いた．

## すぐ試す

```bash
app/start.sh
```

リポジトリ直下で実行し，http://127.0.0.1:5173 を開く．サーバーと画面が一緒に起動する．Ctrl+C で両方止まる．既定では嘉音 v1.4.1 と JD2 を開く．別の話者は `app/start.sh --speaker 名前=パス ...` で開く．同じページを2つの窓で開くと，一方の編集がもう一方にも出る．

## 構成

ローカルの Python サーバーがデータをすべて持ち，画面(React + Vite，ブラウザで開く)は操作を送って変更の通知を受け，描き直す．計算は VTL の C++ backend を `libVocalTractLabApi.dylib`(ctypes)経由で使う．

| ファイル | 役割 |
|---|---|
| [app_core/names.py](app_core/names.py) | 仮のアプリ名(ここだけ直せば名前が変わる) |
| [app_core/xmltree.py](app_core/xmltree.py) | 書式を1バイトも失わない XML の読み書き |
| [app_core/speaker.py](app_core/speaker.py) | `.speaker` を木として読む(解剖，声道の形状，声門モデル4種と選択，静的パラメタと形状)．値は番地(タプル)で読み書きする |
| [app_core/ops.py](app_core/ops.py) | 操作の仕組み：登録，変更の記録，履歴の1歩 |
| [app_core/operators.py](app_core/operators.py) | 操作そのもの(今は `tract.set_param` と `glottis.set_param`) |
| [app_core/project.py](app_core/project.py) | プロジェクト：話者，履歴(1本)，元に戻す・やり直す，通知，保存と `.meta.json` |
| [app_core/vtl.py](app_core/vtl.py) | VTL を呼ぶ層：面積関数，伝達関数，フォルマント，正中断面の輪郭 |
| [app_core/server.py](app_core/server.py) | HTTP と WebSocket の最小のサーバー |
| [examples/edit_speaker.py](examples/edit_speaker.py) | Python から操作を呼ぶ例 |
| [tests/](tests/) | テスト(標準の `unittest`) |
| [start.sh](start.sh) | サーバーと画面を1つのコマンドで起動する |
| [web/](web/) | 画面(React 19 + Vite + TypeScript) |

### 話者

`.speaker` がそのまま正本．読み込んだ XML の書式(字下げ，CRLF，属性の間の空白，小数の桁数)をすべて残すので，変えていない話者を保存すると元とバイト単位で同じになり，値を1つ変えるとその値の文字だけが変わる．数値は元の桁数で書くので，木の値はいつも VTL が読み返す値と同じ(`Speaker.quantize` で先に分かる)．

値の番地：

```
("tract_shape", 形状, パラメタ)            ("tract_shape", "a", "TCX")
("tract_param", パラメタ, 欄)              ("tract_param", "TCX", "max")
("glottis_selected",)
("glottis_static", モデル, 略称)           (..., "Triangular body-cover glottis", "rest_f0")
("glottis_shape", モデル, 形状, 略称か番号) (..., "modal", "f0")
("anatomy", 要素, ..., 属性)               ("anatomy", "palate", "p3", "x")
```

### 操作と元に戻す

すべての編集は操作を通る．操作は `Context.set` でだけ値を変え，その記録(話者，番地，前の値，後の値)が元に戻すための情報になる．画面もスクリプトも同じ関数を呼ぶ：

```python
project.ops.tract.set_param(speaker="kanon", shape="a", param="TCX", value=0.3)   # Python
project.call("tract.set_param", {...}, drag="slider-TCX")                       # サーバー経由
```

履歴の1歩になる単位：

- 操作1回(数値入力の確定，ボタン)．
- ドラッグ：同じ `drag` の呼び出しは `end_drag` までで1歩．途中も毎回通知するので画面は動きに付いてくる．別の操作が来たらそこでドラッグを閉じる．
- `with project.group("名前"):` の中(一括操作，スクリプト1本)．入れ子は外側に合流する．

表示の切り替え(拡大，選択，ワークスペース)と音のキャッシュは操作ではないので，履歴に入らない．操作が途中で失敗したら，その操作の変更は取り消す．値は話者ファイルの範囲(min〜max)に収める(VTL と同じ)．

変更のたびに `Project.subscribe` で登録した関数に通知が届く：

```json
{"type": "changed", "source": "do|undo|redo", "op": "...",
 "changes": [{"speaker": "kanon", "address": ["tract_shape", "a", "TCX"], "value": 0.3,
              "edited": true, "saved": -0.8236}],
 "history": {"can_undo": true, "can_redo": false, "undo_label": "...", "redo_label": null, "open": null}}
```

`edited` は値が前回の保存(または開いたとき)の値 `saved` と違うかどうか．`Project.edited(id)` とプロジェクトの JSON の `edited` にも同じものがある．

保存(`Project.save_speaker`)は `.speaker` を書き，横の `foo.meta.json` の `saves` に，時刻，ファイルの sha256，前回の保存からの操作一覧(実行，元に戻す，やり直す)を足す．

### VTL を呼ぶ層

API は話者をファイルからしか読めず，同時に1人しか持てない．そこで `Backend.use(speaker)` は木を一時ファイルに書いて `vtlInitialize` する．ただし読み直すのは解剖か声門モデルが変わったときだけで，形状のパラメタは毎回の呼び出しで渡すので，形状の編集では読み直さない(読み直しは約 30 ms)．

- `tube`：面積関数(`vtlTractToTube`，40 区間)．
- `spectrum`：声門から唇までの伝達関数(`vtlGetTransferFunction`)．
- `formants`：そのスペクトルの山(dB の放物線補間．既定 8192 点 = 5.9 Hz 刻み)．
- `contours`：正中断面の輪郭．既存の `vtlExportTractSvg` が書く SVG の折れ線 14 本を読み，cm(VTL の座標，唇が +x，上が +y)に戻す．名前は `CONTOUR_NAMES`．1回約 12 ms．backend に手は入れていない．速さが足りなければ，同じ折れ線を配列で返す API 関数を足せばよい．

## 画面(web/)

| ファイル | 役割 |
|---|---|
| [web/src/store.ts](web/src/store.ts) | サーバーのデータの写し．WebSocket で通知を受けて当てはめ，操作・元に戻す・計算を送る |
| [web/src/compute.ts](web/src/compute.ts) | VTL の計算の依頼．同時に1つだけ送り，待つ間に来た入力は最新だけ残す(ドラッグで溜まらない) |
| [web/src/App.tsx](web/src/App.tsx) | 声道ワークスペースの配置，上の帯，下の帯，キー操作 |
| [web/src/components/plots.tsx](web/src/components/plots.tsx) | 正中断面，面積関数，スペクトル |
| [web/src/components/Params.tsx](web/src/components/Params.tsx) | パラメタのスライダと数値入力 |
| [web/src/i18n/](web/src/i18n/) | 翻訳ファイル(`en.json` が既定，`ja.json`) |
| [web/src/styles.css](web/src/styles.css) | トークンと見た目(schedule2 の principles.md に従う) |

- 形状を選ぶと，その形状の正中断面・面積関数・スペクトル(F1–F3)が出る．計算はサーバーの VTL．
- スライダのドラッグは `drag` で履歴の1歩にまとめる．動かしている間も図が付いてくる．値を押すと数値を直接入力できる(Enter か欄を離れると確定，Esc で取り消し)．スライダは矢印キーでも動く(Shift で10倍)．
- 元に戻す・やり直す：下の帯のボタン，Cmd/Ctrl+Z，Shift+Cmd/Ctrl+Z．
- 保存したときから変わった値は，値と形状に「●」と特色(`--accent`)の印が付く．図には保存した形が特色の点線で重なる．下の帯の件数は，保存したときと違う値の個数．「保存」は第3段以降．
- 明暗と言語は右上で切り替え，ブラウザが覚える(`localStorage` の `ui.theme`，`ui.lang`)．文言はすべて `web/src/i18n/*.json` にある．言語を足すには，同じキーを持つ JSON(例：`kono.json`，`_name` は切り替えに出す名前，`_order` は並び順)を置くだけでよい．
- ほかのワークスペースのタブ，エディタ名の ▾，再生はまだ無い(押すと「まだ無い機能です」と出る)．声道の図の操作点，区画の分割，別窓も第3段以降．

開発中は `app/web` で次を実行して型を確かめる：

```bash
npx tsc --noEmit
```

`npm run build` で `web/dist/` に作っておくと，Python のサーバーだけで画面も出せる(`http://127.0.0.1:8765/`)．

## 起動(部品ごと)

Python は main の checkout の venv(`build-mac/venv`)を使う．依存は [requirements.txt](requirements.txt)：

```bash
uv pip install --python build-mac/venv/bin/python -r app/requirements.txt
```

VTL の API を作る(worktree では自分の `build-mac/` に)：

```bash
cmake -S . -B build-mac/gui && cmake --build build-mac/gui -j8
```

ライブラリは環境変数 `VTL_LIB`，なければこの checkout の `build-mac/gui/libVocalTractLabApi.dylib`．

サーバー(`app/` で)：

```bash
../build-mac/py.sh -m app_core.server --speaker kanon=../speakers/fulkhisa-kanon/fulkhisa-kanon-v1-4-1.speaker --speaker ../speakers/JD2.speaker
```

`127.0.0.1:8765` で待つ．試す：

```bash
curl -s -XPOST localhost:8765/api/op -d '{"op":"tract.set_param","args":{"speaker":"kanon","shape":"a","param":"TCX","value":0.3}}'
curl -s -XPOST localhost:8765/api/compute -d '{"speaker":"kanon","shape":"a","what":["formants"]}'
curl -s -XPOST localhost:8765/api/undo
```

HTTP と WebSocket の取り決めは [server.py](app_core/server.py) の冒頭．WebSocket `/ws` は，つないだ直後にプロジェクト全体(`hello`)を送り，以後すべての変更を全部の窓に送る．

Python から：

```bash
../build-mac/py.sh examples/edit_speaker.py
```

## テスト

`app/` で：

```bash
../build-mac/py.sh -m unittest discover -s tests -t .
```

- 話者：リポジトリのすべての `.speaker`(嘉音 v1.4.1，JD2 ほか 22 個)が，読んで書くとバイト単位で元と同じ．値を1つ変えると差分はその1行だけ．木の形状の値が，VTL が同じファイルから読む値(`vtlGetTractParams`)と一致し，書き換えた値も VTL がそのまま読む．
- 操作：1回 = 1歩，ドラッグ = 1歩，グループ = 1歩，元に戻すとバイト単位で元に戻る，失敗した操作は何も変えない，通知，保存と `.meta.json`．
- VTL：母音のフォルマントの大小，面積関数，輪郭，操作で結果が変わり元に戻ること，形状の編集では読み直さないこと．
- サーバー：HTTP の操作が2つの WebSocket に届く，WebSocket からの操作・ドラッグ・元に戻す，エラー，計算．

VTL のライブラリが無いと，VTL を使うテストは飛ばす．

## まだ無いもの(第3段以降)

声道ワークスペース以外の画面，保存の操作，トラック・クリップ・作品・プロジェクトのファイル，保存していない変更の自動退避，操作の種類(今は2つ)．
