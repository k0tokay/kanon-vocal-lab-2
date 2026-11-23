# 子音形状の調整ツール

嘉音の話者ファイル（`speakers/fulkhisa-kanon/fulkhisa-kanon-v0-8-vtl24.speaker`）の子音形状を変え、CV 音節を合成して、聞き比べと測定を1コマンドで行う。元の話者ファイルは書き換えず、毎回新しい話者ファイルを出力フォルダに書く。

- [ctune.py](ctune.py)：本体（モジュール兼コマンド）。
- [ctrack.cpp](ctrack.cpp)：ジェスチャスコアから調音パラメタの時系列を取り出す小さな C++。VTL の API は音声と管の列しか出さないので、これを足した。
- [edits/alveolopalatal.json](edits/alveolopalatal.json)：ɕ の修正（下記）。
- [results/](results/)：調整前（`baseline`）、調整後（`tuned`）、[試聴セット](results/listening/ab.wav)。

anatomy-compensation ブランチの [vtlmap](../vtlmap/README.md)（`Tract`、`jacobian`、`bounded_step`）と、[japanese-accent](../japanese-accent/README.md) の日本語の音素対応と seg 書き出しを使う。このブランチは両方をマージしてある。

## VTL 2.4 での子音の扱い（調査）

- 子音は `<名前>(a)`、`<名前>(i)`、`<名前>(u)` の3形状で持つ。合成時には `GesturalScore::getContextDependentConsonant` が、そのときの母音形状を a–i–u の三角形に射影した座標で3形状を補間する。舌と唇は別々の座標で補間される。
  - 例えば `M`（非円唇の [ɯ]）は、舌の座標が u に近く、唇の座標が i に近い。そのため、M の前の子音は「舌は (u) から、唇は (i) から」取られる。`shu` の唇を (u) で変えても音が変わらなかったのはこのため。
- 子音が有効な区間では、子音の形状が目標値になる。その声道パラメタを決めるのは、調音点より前（唇側）の子音である。
  - 舌体の子音は舌・顎・唇の全パラメタを決める。
  - 舌尖の子音は、舌体（TCX, TCY）以外のパラメタを上書きする。
  - 唇の子音は、顎と唇だけを上書きする。
  - 子音が1つしかなければ、HX, HY, VS, TRX などの残りも、その子音形状の値になる。
- **パラメタごとの dominance（`DX` のような値）は VTL 2.4 にも、この話者ファイルにもない**。調整できるのは形状そのものと、ジェスチャの時間（seg の継続長、時定数）だけである。
- 日本語向けの記号（japanese-accent ブランチで backend に追加したもの）は次のように展開される。
  - `s\`・`z\`（シ・ジ）：`tt-alveolopalatal-fricative`。
  - `ts\`・`dz\`（チ・ヂ）：`t` または `d`（`tt-alveolar-closure`）＋ `s\`・`z\`。破裂部は 33% または 40%。
  - `C`（ヒ）と `j`（ヤ行）：どちらも `tb-palatal-fricative` を使う。ヤ行だけを変えることはできない。
  - `4`（ラ行）：直前の母音（語頭では後続母音）の `tt-tap-<母音>`。ない場合は `tt-alveolar-closure` を使う。
  - `w`：VTL には記号がない。そのため japanese-accent では短い `M` で代用している。`w` をそのまま seg に書くと無音になる。

静的形状の口腔内の最小断面積（cm²）と位置（声門からの距離 cm）。喉頭より上（3 cm 以降）で測った。嘉音の声道長は 11.6〜12.9 cm。

| 形状 | (a) | (i) | (u) |
|---|---|---|---|
| `ll-labial-closure` | 0.000 @ 12.08 | 0.000 @ 11.81 | 0.000 @ 12.73 |
| `ll-labial-fricative` | 0.150 @ 11.71 | **0.000** @ 12.31 | 0.118 @ 12.94 |
| `ll-labial-approximant` | 0.150 @ 11.73 | 0.269 @ 11.71 | 0.150 @ 12.36 |
| `ll-dental-fricative` | 0.150 @ 11.45 | 0.150 @ 11.30 | 0.150 @ 11.96 |
| `tt-alveolar-closure` | 0.000 @ 10.34 | 0.000 @ 10.74 | 0.000 @ 10.73 |
| `tt-alveolar-flap` | 0.000 @ 10.22 | 0.032 @ 10.92 | 0.000 @ 10.93 |
| `tt-alveolar-fricative` | 0.150 @ 10.75 | 0.150 @ 10.32 | 0.175 @ 11.12 |
| `tt-postalveolar-closure` | 0.000 @ 9.60 | 0.000 @ 9.89 | 0.000 @ 9.82 |
| `tt-postalveolar-fricative` | **0.331** @ 10.50 | 0.139 @ 10.25 | 0.092 @ 9.98 |
| `tt-alveolopalatal-fricative`（元） | **0.348** @ 10.13 | **0.380** @ 9.98 | **0.000** @ 10.18 |
| `tt-alveolopalatal-fricative`（修正後） | 0.105 @ 10.31 | 0.173 @ 10.66 | 0.103 @ 10.15 |
| `tb-palatal-fricative` | 0.150 @ 11.41 | 0.150 @ 11.22 | 0.150 @ 11.40 |
| `tb-velar-closure` | 0.000 @ 6.48 | 0.000 @ 7.35 | 0.000 @ 6.74 |
| `tb-velar-fricative` | 0.371 @ 7.28 | 0.000 @ 7.58 | 0.034 @ 6.28 |

`tt-tap-a/i/u/e/o` は、いずれも 10.5〜11.1 cm で閉じる。太字は、摩擦音なのに狭めがない、または閉じている箇所。

## 測定

`ctune.py run` は各音節を「（無音）a + CV（無音）」の枠で合成する。F0 は 220 Hz からゆるく下げ、/a/ は 0.2 s、母音は 0.24 s。子音の継続長は japanese-accent の値を使う。各音節について次の量を測る。

調音（ctrack で取ったパラメタ列を 2.5 ms ごとに vtlmap で評価した厳密値）：

| 列 | 意味 |
|---|---|
| `minA`, `pos` | 子音区間（前後 30〜40 ms を含む）の口腔内最小断面積 [cm²] とその位置 [cm] |
| `shut` | 口腔が閉じている時間（≤ 0.001 cm²）[ms] |
| `narw` | 0.25 cm² より狭い時間 [ms]。狭めをどれだけ保っているか |
| `F2rel` | 解放の 5 ms 後（閉鎖音）、または最も狭い時点（継続音）の F2 [Hz]。VTL の伝達関数のピークから求め、鼻腔は閉じて計算する |
| `F2v` | 母音中央の F2 |

音響（WAV から）：

| 列 | 意味 |
|---|---|
| `sil` | 0.5〜12 kHz 帯が母音より 35 dB 以上低い区間（無音閉鎖）[ms] |
| `brst` | 閉鎖直後 8 ms の母音比レベル [dB]。JSON には重心 `burst_cog_hz` もある |
| `VOT` | 解放から 70〜500 Hz 帯が母音の −12 dB 以内に戻るまで [ms] |
| `noise` | 子音区間での 2〜12 kHz 帯の最大値（母音比）[dB] |
| `fCoG`, `fdB`, `voic` | 摩擦区間（2〜12 kHz 帯がピークから 6 dB 以内の区間の中央 60%）のパワー重心、母音比レベル、70〜500 Hz 帯の母音比（声帯振動の漏れ）。JSON には帯域ごとのエネルギー比 `fric_bands` もある |
| `nas` | 鼻音のつぶやき区間の母音比レベル |

`summary.json` の `locus` は、子音ごとの locus equation（F2rel = k·F2v + c）と locus c/(1−k)。軟口蓋音は母音によって locus が2つに分かれるので、`k` の値は意味をなさない。

F2 を音声の LPC で取る方法も最初に試したが、F0 が 220 Hz の嘉音の声では /i/ の F2 を 600 Hz 台と誤るので、やめた。

## 調整前の所見

[results/baseline/summary.json](results/baseline/summary.json)、全音節は [all.wav](results/baseline/all.wav)。測定で悪かった順に並べる。

1. **ɕ（シャ・シ・シュ）**：`tt-alveolopalatal-fricative` の (a)(i) は口腔に狭めがない。sha の最小断面積は 0.40 cm²、shi は 0.31 cm² で、後続の /i/（0.30 cm²）より広い。一方 (u) は閉じている。そのため **shu は 32 ms の閉鎖と破裂をもつ [tɕu]（チュ）になっていた**。前のブランチの `alveolopalatal.py` は摩擦の重心だけを基準に選んでいて、断面積は見ていなかった。
2. **ワ**：`w` を短い `M` で代用しているので、唇の狭めがなく（0.44 cm²）、F2 も /a/ からほとんど動かない（1591 → 1530 Hz）。「ア」に近い。
3. **ヤ行**：`j` は 35 ms で、目標（0.15 cm²）に届かない。最小断面積は ya 0.57、yo 0.39 cm²。形状の問題ではなく継続長の問題。
4. その他、測定で目立つ問題はなかった。
   - 閉鎖音の閉鎖は 30〜55 ms。
   - ki の VOT は 26 ms、chi は 54 ms、tsu は 44 ms。
   - sa の重心は 6.9 kHz。
   - タップの閉鎖は 10〜15 ms。
   - ただし `ll-labial-fricative(i)` が閉じているので、「フィ」は破裂音になるはずである（この音節セットには入れていない）。

## 修正

### ɕ の形状（edits/alveolopalatal.json）

`fit` で、(a)(i)(u) の舌6パラメタを動かした。目標は、声門から 10.0 cm（歯茎の /s/ の 10.3〜11.1 cm と、後部歯茎閉鎖の 9.6〜9.9 cm の間）で 0.12 cm² になることとした。パラメタの変化は各範囲を単位として最小にする。

- (u) は閉じた形状から始まる。閉じていると断面積の微分が 0 なので、まず /u/ の方向へ、断面積が 0.25 cm² になるまで混ぜて開く。そのうえで (u) の舌尖を TTX = 2.8（元は 2.2）に前へ出し、舌体だけで 10.2 cm・0.12 cm² に合わせた。舌尖が奥にあるままでは、前腔が大きく、重心が 2.6 kHz まで下がった。
- (i) は fit で TTY が −0.69 から −0.43 に上がる。これでは chi（`t` + `s\`）で、歯茎閉鎖からの移行中に舌尖が離れず、閉鎖が 27.5 ms から 50 ms に延びた。そこで TTY を −0.55 に戻した。この値では、shi の最小断面積は 0.20 cm²、重心は 4.9 kHz、chi の閉鎖は 35 ms になる。

```sh
python3 ctune.py fit "tt-alveolopalatal-fricative(*)" --area 0.12 --pos 10.0 --append edits/alveolopalatal.json
#  (u) の TTX=2.8, TTY=-0.4 を edits に足してから
python3 ctune.py fit "tt-alveolopalatal-fricative(u)" --area 0.12 --pos 10.2 --free TCX,TCY,TBX,TBY \
    --edits edits/alveolopalatal.json --append edits/alveolopalatal.json
#  最後に (i) の TTY=-0.55 を足す
```

### ヤ・ワ（音素対応の変更。話者ファイルは変えない）

- `y=j:0.06`：`j` を 35 ms から 60 ms にすると、ya・yu・yo とも 0.15 cm² に達する。
- `w=u:0.05`：円唇の `u` を 50 ms 置く。唇が 0.15 cm² まで狭まり、F2 が 1216 Hz から /a/ へ上がる。日本語の /w/ は円唇が弱いので、これは近似である。唇を丸めずに狭める形状を作るには、backend に `w` の記号を足す必要がある。

この2つは japanese-accent の `accent.py` に入れた（`JA_ONSET["w"] = ["u"]`、`BASE` の `j` = 0.06 s、`u` = 0.05 s）。そのため `--map` を付けなくても、上と同じ値になる。拗音の渡り（kya などの `j`）は 25 ms のまま。japanese-accent の例文 WAV（`results/*.wav`）は pyopenjtalk がないので作り直していない。

## 結果

[results/tuned/summary.json](results/tuned/summary.json)、[全音節](results/tuned/all.wav)。変わった音節だけを示す（矢印の左が調整前）。

| 音節 | 最小断面積 [cm²] | 狭め [ms] | 閉鎖 [ms] | 摩擦重心 [Hz] | F2rel [Hz] |
|---|---|---|---|---|---|
| sha | 0.40 → 0.18 | 0 → 22.5 | 0 | 4161 → 4329 | 2509 → 2510 |
| shi | 0.31 → 0.20 | 0 → 40 | 0 | 4445 → 4896 | 2587 → 2685 |
| shu | 0.00 → 0.14 | 62.5 → 55 | **32.5 → 0** | （破裂）→ 4150 | 2347 → 2830 |
| chi | 0 | 65 → 85 | 27.5 → 35 | 4370 → 5572 | 2756 → 2705 |
| ji | 0 | 62.5 → 70 | 27.5 → 35 | 4211 → 4593 | 2699 → 2677 |
| ya | 0.57 → 0.15 | 0 → 17.5 | 0 | – | 2363 → 2376 |
| yo | 0.39 → 0.15 | 0 → 25 | 0 | – | 2321 → 2381 |
| wa | 0.44 → 0.15 | 0 → 37.5 | 0 | – | 1591 → 1216 |

他の音節の値は変わっていない。ɕ の重心は sha 4.3、shu 4.2、shi 4.9 kHz にまとまり、同じ母音の前の s（sa 6.9、su 5.5 kHz）より低い。

**試聴**：[results/listening/ab.wav](results/listening/ab.wav) は、sha shi shu chi ji ya yo wa の順に、それぞれ調整前 → 調整後を並べたもの。音節ごとの `<音節>-before.wav` / `<音節>-after.wav` もある。聴取による評価はまだしていない。

## 使い方

ビルド（リポジトリ直下）：

```sh
cmake --build build-mac/gui --target VocalTractLabApi      # 日本語記号の入った API
clang++ -shared -fPIC -std=c++14 -O2 -w -Ibackend experiments/vtlmap/vtlmap.cpp $(ls backend/*.cpp | grep -v SoundLib.cpp) -o build-mac/vtlmap.so
clang++ -shared -fPIC -std=c++14 -O2 -w -Ibackend experiments/consonant-tuning/ctrack.cpp $(ls backend/*.cpp | grep -v SoundLib.cpp) -o build-mac/ctrack.so
```

以下は `experiments/consonant-tuning/` で実行する。pyopenjtalk は不要。

```sh
# 形状の静的な狭め（子音名、形状名、日本語の頭子音 k s sh … のどれでもよい）
python3 ctune.py show sh k tb-velar-closure --params

# 編集して合成・測定する。音節を省くと 45 音節すべてを合成する（約 1 分）
python3 ctune.py run out/try1 -e "tb-velar-closure(*):TBX+=0.1" -s ka,ki,ku --compare results/baseline

# 編集をファイルにまとめ、音素対応も替える（例：ワを M の 70 ms に戻す）
python3 ctune.py run out/try2 --edits edits/alveolopalatal.json --map w=M:0.07

# 狭めの断面積と位置を目標に、形状を fit する（結果は edits の形で出る）
python3 ctune.py fit "tt-alveolar-fricative(u)" --area 0.15 --pos 10.9 --append edits/mine.json
python3 ctune.py fit "tt-alveolopalatal-fricative(i)" --area 0.12 --pos 10.0 --limit "TTY<=-0.55"

# 2つの run から試聴セットを作る
python3 ctune.py ab results/baseline out/try1 out/ab -s ka,ki,ku
```

- **編集の書式**：`形状:パラメタ 演算 値`。演算は `=`、`+=`、`-=`、`*=`。`(*)` は (a)(i)(u) の3つ、`tt-tap-*` はタップ形状のすべてを指す。値はパラメタの範囲に切り詰める。
- **出力**：`run` は出力フォルダに次を書く。
  - `kanon.speaker`：編集後の話者ファイル。元のテンプレートの声門モデルはそのまま残る。
  - 音節ごとの WAV と、それをつないだ `all.wav`。
  - `summary.json`：編集の内容、変更前後の値、測定値。
  - 編集なしで書き出した話者ファイルは元と同じ音になる（WAV のサンプル差 0 を確認した）。
- Python からは `ctune.run(edits, syllables, out_dir)`、`ctune.fit(tract, shape, area, pos)`、`ctune.measure(wav, frame, speaker)` を直接呼べる。
- **`fit`**：口腔内の最小断面積の位置は、パラメタを動かすと区間ごとに跳ぶので、微分に使えない。そこで残差を次の2つにした。
  - 目標位置での断面積と目標値の差。
  - ほかの区間が目標より狭くなったときにだけかかる罰則。

  ヤコビアンは `vtlmap.jacobian`（minmod、範囲の 1% 刻み）、ステップは `vtlmap.bounded_step`（Levenberg–Marquardt）で求める。試行点で口腔が閉じたら、その点は採らない。

## 限界と今後

- 評価は測定だけで、聴取による確認はまだ。重心の目安（ɕ が s より低いこと）も、嘉音の目標の実測値ではない。
- chi・ji の閉鎖部は `tt-alveolar-closure`（10.3〜10.8 cm）である。`ts\` を `tt-postalveolar-closure` で閉じるには backend の変更が要る。ɕ を狭めたので、chi の摩擦の重心は 4.4 → 5.6 kHz に上がった。
- `noise`（摩擦の強さ）は、ɕ の断面積を 0.31 → 0.10 cm² と変えても 1 dB ほどしか変わらない。無声摩擦の声門ジェスチャによる気息雑音が支配的だからである。摩擦の強さを調整する手段は、形状ではなく声門の形状や声門下圧になる。
- `ll-labial-fricative(i)` が閉じている（「フィ」が破裂音になる）。この音節セットには入れていないので、まだ直していない。
- japanese-accent の例文 WAV は、ヤ・ワの変更後にまだ作り直していない。
