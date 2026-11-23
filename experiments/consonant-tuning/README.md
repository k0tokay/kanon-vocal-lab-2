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

## ノイズ源の解剖スケーリング（backend の変更）

VTL の摩擦・破裂ノイズ源（`TdsModel::calcNoiseSources`）の定数は、JD2 の寸法の絶対値で書かれていた。そのため、声道が小さい嘉音（中立形状で 12.5 cm、JD2 は 16.8 cm）では、ɕ もヒ（ç）も「歯から 1 cm 前後」の同じ扱いになっていた。その結果、雑音フィルタのカットオフ（約 4.3 kHz）がほぼ同じになり、シャがヒャに聞こえていた。

このブランチでは、話者の大きさ s = 中立形状の管長 / JD2 の値 で、これらの定数を伸縮する。

| 定数 | 元の値 | 伸縮 |
|---|---|---|
| 狭めとみなす最大断面積・その幅・テーパ開始 | 1.0 / 0.2 / 0.5 cm² | ×s² |
| 歯の音源とみなす距離・減衰距離 | 2.5 / 3.0 cm | ×s |
| 声門上の音源位置 | 1.5 cm | 伸縮しない（下記） |
| 唇の f/p 判定の断面積 | 0.15 / 0.10 cm² | ×s² |
| カットオフ（歯 6000/1500、壁 1500、唇 8000/500 Hz） | | ×1/s |

- 利得はそのままにしてある。声門の気息雑音と鼻腔の音源も変えていない。
- 実装：
  - `VocalTract::calcSizeScale()` が s を計算する。呼ばれるのは話者ファイルの読み込み時と `AnatomyParams::setFor` の後。
  - s は `Tube::sizeScale` として `TdsModel` に渡る。GUI でも API でも同じように効く。
  - 管列ファイル（tube sequence）からの合成では、s = 1 のまま。
- 基準長 `VocalTract::REFERENCE_TRACT_LENGTH_CM` は JD2 の中立形状の値（16.779… cm）そのもの。そのため JD2 では s = 1 になる。スケーリングの有無で JD2 の出力がサンプル単位で一致することを確かめた（sa, shi, ka, pa）。
- API：`vtlGetSizeScale(&s, &length)` と `vtlScaleNoiseToAnatomy(0/1)`（既定は 1）。`ctune.py run --no-noise-scaling` で元の動作に戻せる。嘉音の s は 0.747。

- 伸縮の指数は `vtlSetNoiseScalingExponents(長さ, 面積, 周波数)` で変えられる（既定 1, 2, −1）。`ctune.py run --noise-exponents=1,0,-1` など。

### 声門の音源位置を伸縮しない理由（「こもって聞こえる」の原因）

最初の版は声門上 1.5 cm の音源位置も ×s（嘉音で 1.12 cm）にしていた。これで母音がこもった。

- 嘉音の modal は relative amplitude 0.508 で息っぽい。母音にも声門の気息雑音が常に混ざっていて、それが母音の高域を作っている。
- 音源位置を動かすと、雑音が注入される管の区間が変わり、声道の伝達特性での高域の出方が変わる。母音区間のスペクトル重心が a 907→774、e 869→627、i 615→485 Hz に下がった。
- 指数を一つずつ切り替えて調べると、長さの伸縮だけで鈍る。面積と周波数の伸縮は母音に影響しない。原因は声門の音源位置だった。
- 声門の音源は口腔の形の判定とは関係がない。そのため伸縮から外した。

母音区間（中央 80 ms）のスペクトル重心 [Hz]：

| 条件 | a | i | u | e | o |
|---|---|---|---|---|---|
| スケーリングなし | 910 | 611 | 592 | 850 | 652 |
| 最初の版（声門も ×s） | 774 | 485 | 572 | 627 | — |
| 現在の版 | 937 | 645 | 589 | 858 | 643 |

結果（[scaling-off](results/scaling-off/summary.json) → [scaling-on](results/scaling-on/summary.json)。どちらも ɕ の修正後の形状）：

| 音節 | 摩擦の重心 [Hz] | 2–12 kHz のピーク（母音比）[dB] |
|---|---|---|
| sha / hya | 4329 / 3552 → 4383 / 3573 | 16.5 / 17.5 → 15.2 / 13.3 |
| shi / hi | 4896 / 4100 → **5633 / 4274** | 10.8 / 10.4 → 10.8 / 9.1 |
| shu / hyu | 4150 / 4030 → 4257 / 4041 | 19.8 / 22.2 → 19.2 / 20.9 |
| sa / su | 6890 / 5529 → 7187 / 5906 | 11.1 / 17.1 → 10.4 / 18.3 |
| ha | 3320 → 2734 | 11.3 → 10.5 |
| fu | 3634 → 3632 | 13.6 → 13.7 |

- シとヒは 1.4 kHz 離れた。シャとヒャは重心の差は変わらないが、ヒャのノイズが 4 dB 弱くなった。
- シュとヒュは、まだ近い。(u) の ɕ の狭めは、fit でも 10.15 cm より前に動かせなかった。
- 最初の版では ɕ と ç の差がもっと大きく見えた（hya 2880、hi 2883 Hz）。しかしその差の多くは、声門の気息雑音の位置が変わったことによるもので、母音もこもっていた。
- ɕ と ç の区別の主役はノイズ源の規則ではなく、狭めの形（前後の位置と、前方の空洞の長さ）である。ここを詰めるのは形状側の作業。
- 試聴：[listening-noise-scaling/ab.wav](results/listening-noise-scaling/ab.wav)。sha hya shu hyu shi hi sa su fu ha の順に、それぞれ スケーリングなし → あり。

## 破裂音のパルスと声門の relative amplitude

破裂音の解放で単発のパルスが出るのは、解放が強すぎるからではなかった。母音が弱いからである。

- 嘉音の解放の振幅は母音のピークの 0.66〜1.15 倍（`rpk` 列）。JD2 では 0.64〜0.75 倍。
- 嘉音の modal の声門（Geometric glottis 2019）は、次のとおり。
  - lower/upper displacement が 0.081 / 0.121 cm（モデルの既定は 0.02）。
  - relative amplitude が 0.508。
- そのため声帯振動の振幅が小さい。一方、解放の過渡音は肺圧で決まるので、JD2 と同程度の大きさになる。
- 声門を開いたまま無声破裂の外転を広げても、ノイズ源をスケーリングしても、`rpk` は変わらなかった。
- relative amplitude（control param 6）が直接効く。

| modal の relative amplitude | ka | ta | pa | da | ga | ba |
|---|---|---|---|---|---|---|
| 0.508（現状） | 0.61 | 1.06 | 0.93 | 1.08 | 0.81 | 0.88 |
| 0.75 | 0.37 | 0.67 | 0.56 | 0.69 | 0.48 | 0.55 |
| 1.0（声門の音源位置を直す前の測定） | 0.24 | 0.43 | 0.36 | 0.46 | 0.31 | 0.35 |

- 0.75 で JD2 と同じくらいの比になる。
- 母音の気息雑音も減るので、母音区間の重心は下がる（a 937→814、e 858→694 Hz）。息っぽさが減った分であって、上の「こもり」とは別のもの。
- 声質（息っぽさ）に関わるので、話者ファイルは変えていない。試聴用の話者は [results/relamp-0.75/kanon.speaker](results/relamp-0.75/kanon.speaker)。ɕ の修正と relative amplitude 0.75 が入っている。
- 試聴：[listening-relamp/ab.wav](results/listening-relamp/ab.wav)。ka ta pa da ga ba sa sha の順に、それぞれ 0.508 → 0.75。どちらもスケーリングあり。

### relative amplitude 1 でもパルスが残る理由：声門が閉じない

パルスの大きさは、波形のピーク比（`rpk`）では測れていなかった。帯域ごとに見ると、原因は母音の側にある。

- Geometric glottis 2019 の振動振幅は 0.0007 × (rest_length / 1.6) × √(経声門圧) cm である。
- 嘉音は rest_length が 0.8 cm なので、relative amplitude 1 でも振幅は約 0.03 cm にしかならない。一方、modal の静止時の開き（x_bottom / x_top）は 0.081 / 0.121 cm ある。そのため声帯は一度も閉じない。
- JD2 は振幅 0.059 cm に対して開きが 0.05 cm なので、毎周期閉じる。
- 嘉音の modal の開きは、同じファイルの breathy（0.020 / 0.031）や default（0.050 / 0.090）よりも大きい。
- 閉じない声門の音源は、中高域の倍音が弱い。破裂の解放は広帯域なので、母音に比べて中高域だけが目立ち、パルスに聞こえる。

解放の前後 11 ms の帯域ごとの最大振幅を、同じ帯域の母音での値と比べた [dB]（ta / ka / pa）：

| 声門 | 振幅 / 開き | 300–1500 Hz | 1500–4000 Hz |
|---|---|---|---|
| JD2 | 1.17 | −19 / −27 / −23 | −20 / −29 / −22 |
| 嘉音の現状（rel_amp 0.508） | 0.12 | −2 / −6 / −1 | −9 / +1 / +6 |
| rel_amp 1.0 | 0.24 | −13 / −17 / −12 | −15 / −3 / +1 |
| 開き 0.025 / 0.040、rel_amp 0.75 | 0.55 | −19 / −23 / −19 | −24 / −16 / −13 |
| 開き 0.040 / 0.060、rel_amp 1.0 | 0.49 | −20 / −24 / −20 | −26 / −15 / −13 |
| 開き 0.025 / 0.025、rel_amp 1.0 | 1.17 | −21 / −27 / −22 | −24 / −20 / −19 |

- relative amplitude だけを上げても、1.5–4 kHz の解放は母音と同じくらいの強さのまま残る。
- 静止時の開きを振幅の 2 倍程度まで狭めると、JD2 に近くなる。完全に閉じなくてもよい。
- 解放の後の気息（VOT の区間）の 4–10 kHz も、現状では母音より強い。これも母音の高域が弱いことによる。
- 開きを狭めると息っぽさが減るので、声質が変わる。話者ファイルは変えていない。
- 他の候補も調べた。舌先の開く速さは嘉音の ta のほうが JD2 より速い（解放の 10 ms 後に 0.83 cm²、JD2 は 0.54 cm²）。しかし ka は JD2 より遅く、pa もほぼ同じなので、三つに共通するパルスの説明にはならない。
- 話者：[glottis-variants/](results/glottis-variants)（ɕ の修正入り。modal の声門だけが違う）。
- 試聴：[listening-glottis/](results/listening-glottis)。1 現状、2 rel_amp 1.0、3 開き 0.025/0.040・rel_amp 0.75、4 開き 0.040/0.060・rel_amp 1.0、5 開き 0.025/0.025・rel_amp 1.0。どれも /a/ に続けて ka ta pa da ga ba sa sha ha。

注意：同じプロセスで続けて合成すると、ノイズの乱数が引き継がれるので、2回目以降は波形が変わる。`ctune.py run` は毎回同じ順で合成するので、同じ条件なら同じ結果になる。

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
- 上の「調整前の所見」と「結果」の表は、ノイズ源のスケーリングを入れる前の backend で測った値である（`baseline`、`tuned`）。
- `ll-labial-fricative(i)` が閉じている（「フィ」が破裂音になる）。この音節セットには入れていないので、まだ直していない。
- japanese-accent の例文 WAV は、ヤ・ワの変更後にまだ作り直していない。
