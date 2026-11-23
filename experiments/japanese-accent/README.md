# 日本語ピッチアクセントの試作

日本語テキストから VTL の seg ファイルを作り、嘉音話者で合成する。アクセント句と核の位置は OpenJTalk（pyopenjtalk）から取り、F0 は藤崎モデル、継続長はモーラ等時のルールで決める。録音した話者の韻律は使っていない。

## 処理

1. `pyopenjtalk.extract_fullcontext` のラベルから、モーラごとにアクセント句内の位置（A:a2）、句のモーラ数と型（F:f1, f2）を読む。フルコンテキストラベルは平板型を「型 = モーラ数」と書き、尾高型と区別できない。そこで `run_frontend` の NJD の `acc` と `chain_flag` から句ごとの型を計算し直し、句のモーラ数の並びがラベルと一致するときだけ平板型（0型）に戻す。
2. モーラを VTL の SAMPA に写す。ウは `M`（非円唇の [ɯ]）、シ・シャ行は `s\`（[ɕ]）、チ・チャ行は `ts\`（[tɕ]）、ジ・ジャ行は `dz\`（[dʑ]）、ヒは `C`、ラ行は `4`、ワ行の `w` は 50 ms の円唇 `u`、ヤ行の `j` は 60 ms にする（短い `M` と 35 ms の `j` では狭めに届かなかった。[consonant-tuning](../consonant-tuning/README.md) で測定）。拗音は子音に短い `j` を足し、撥音 `N` は後続子音に合わせて `m`/`n`/`N` に分ける。促音は後続子音の持続を延ばす。無声化母音は 0.75 倍に縮めて残し、手順 6 で声門を開く（`devoice="drop"` で落とす旧方式）。`palatal_i=True` なら、/i/ の前の k g n m b p r に 25 ms の `j` を足す。
   `M` と `s\ z\ ts\ dz\` は、このブランチで VTL 本体（[Sampa.cpp](../../backend/Sampa.cpp)、[GesturalScore.cpp](../../backend/GesturalScore.cpp)）に追加した記号。`M` は話者ファイルの形状 `M` を母音ジェスチャとして使う。`s\ z\` は舌尖ジェスチャ `tt-alveolopalatal-fricative` を作り、話者ファイルの同名の形状を参照する。`ts\ dz\` は他の破擦音と同様に、破裂部と摩擦部に分ける。
3. 1モーラ 135 ms を目安に、子音の基本長を引いた残りを母音に割り当てる。ポーズ前のモーラは 1.35 倍に延ばす。
4. 藤崎モデルの指令を置く。フレーズ指令は発話の頭と各ポーズの後に1つずつ置く（$A_p$ = 0.32, 0.22、$\alpha$ = 3/s）。アクセント指令は東京式の規則に従う。1型は第1モーラから、それ以外は第2モーラから立ち上げ、核のモーラ（平板型は句末）の終わりで切る。振幅は $A_a$ = 0.30（平板型はその 0.8 倍）、$\beta$ = 20/s、$\gamma$ = 0.9、指令は 50 ms 先行させる。$F_b$ = 170 Hz。
5. 各分節の 20%・50%・80% 時点の F0 を seg に書き、`vtlSegmentSequenceToGesturalScore` でジェスチャスコアにする。
6. seg 形式で書けない日本語向けの修正を、スコアの各層を時刻で書き換えて入れる（[gestures.py](gestures.py)）。
   - 無声化母音：子音の頭から母音の終わりまで、声門形状を `voiceless-fricative`（振幅 0 で開いた声門）にする。母音の声道形状は残るので、気息雑音がその母音の共鳴で色づく。
   - フ：唇の層の `ll-dental-fricative` を、話者ファイルにある `ll-labial-fricative` に替えて両唇摩擦音 [ɸ] にする。
7. `vtlGesturalScoreToAudio` で合成し、API の定数から取ったサンプリング周波数（48 kHz）で WAV に書く。

## 結果

[F0 の目標曲線](results/f0.png)。破線はアクセント指令を外したフレーズ成分のみの曲線。合成音の母音中央で自己相関から取った F0（Hz）は次のとおりで、「は・し・が」の高低は目標どおりに並ぶ。

| 語 | ha | shi | ga | a | ru |
|---|---:|---:|---:|---:|---:|
| 箸（頭高） | 306 | 240 | 231 | 271 | 211 |
| 橋（尾高） | 246 | 294 | 238 | 273 | 211 |
| 端（平板） | 245 | 289 | 286 | 284 | 211 |

最初のコミットでは、48 kHz の出力を 44.1 kHz として書き出していた。そのため WAV は約 8% 遅く、約 1.5 半音低く再生されていた。上の表と WAV は修正後のもの。

| 試聴 | 文 |
|---|---|
| [箸](results/hashi-chopsticks.wav) / [橋](results/hashi-bridge.wav) / [端](results/hashi-edge.wav) | 〜がある。 |
| [tenki](results/tenki.wav) | 今日はいい天気ですね。 |
| [ame](results/ame.wav) | 雨が降っていますが、私は傘を持っていません。 |

それぞれ `-monotone.wav` がフレーズ指令だけの比較音。聞こえとしての自然さは未評価。

## 子音と無声化の測定

[consonants.py](consonants.py) で測った（[全測定値](results/consonants/summary.json)）。摩擦区間は中央の 60% を使い、重心は 1–11 kHz のパワー重心とした。低域は 70–500 Hz のエネルギーで、同じ発話の有声母音との差を示す。

**無声化**　「私は菊が少し好きです。」の無声化モーラ4つ（き・す・し・す）の低域。

| モーラ | 落とす | 落とす + kʲ | 残す | 残す + kʲ |
|---|---:|---:|---:|---:|
| き | −21.5 dB | −18.8 dB | −26.9 dB | −21.6 dB |
| す（少し） | −32.1 dB | −29.4 dB | −29.6 dB | −29.9 dB |
| し | −23.7 dB | −23.7 dB | −28.2 dB | −28.7 dB |
| す（です） | −39.2 dB | −38.2 dB | −32.3 dB | −32.0 dB |

どの方式でも、声帯振動は有声母音より約 19 dB 以上低い。聴取では、落とす方式は /ɕisuki/ が /ɕski/、/kiku/ が /kk/ のように聞こえ（「ココ」などに聞こえる）、残す方式のほうが良かった。そこで既定は残す方式にした。「kʲ」は /i/ の前の子音に短い `j` を足した版。聞き比べは [落とす](results/consonants/devoicing-drop.wav)、[落とす + kʲ](results/consonants/devoicing-drop-palatal.wav)、[残す](results/consonants/devoicing-keep.wav)、[残す + kʲ](results/consonants/devoicing-keep-palatal.wav)。

**摩擦音**　/a_a/ の枠で、VTL の既定と日本語向けの修正を比べた。破擦音は、閉鎖部（先頭 33%）を除いた残りの中央 60% を測った。

| 音 | 既定 → 修正 | 重心 | ピーク | 母音比レベル |
|---|---|---:|---:|---:|
| シ | `S` → `s\` | 6176 → 4476 Hz | 7061 → 4975 Hz | −12.4 → −14.8 dB |
| シャ | `S` → `s\` | 3396 → 4106 Hz | 3287 → 4506 Hz | −14.5 → −11.4 dB |
| シュ | `S` → `s\` | 1920 → 3903 Hz | 1734 → 3844 Hz | −15.0 → −10.9 dB |
| チ | `tS` → `ts\` | 5552 → 4643 Hz | 6158 → 3762 Hz | −10.6 → −11.9 dB |
| フ | `f` 唇歯 → 両唇 | 4068 → 3593 Hz | 1406 → 1242 Hz | −26.7 → −23.1 dB |
| ヒ | `h` → `C` | 3629 → 4087 Hz | 2584 → 4500 Hz | −11.6 → −19.6 dB |
| サ | `s` | 7121 Hz | 6135 Hz | −14.2 dB |

VTL の `S` は後続母音で重心が 1.9〜6.2 kHz と大きく動き、シュは円唇の [ʃ] になっていた。ɕ は 3.9〜4.5 kHz にまとまり、s（7.1 kHz）より低い。ヒは `h` のままだと、低域が母音比 −16 dB で声帯振動が残っている。`C` にすると −30 dB まで消え、4.5 kHz にピークをもつ硬口蓋摩擦音になる。

### ɕ の形状

[alveolopalatal.py](alveolopalatal.py) で作った。話者の `tt-postalveolar-fricative(v)`（v = a, i, u）から始めて、舌体の4パラメータ（TCX TCY TBX TBY）を `tb-palatal-fricative(v)` に寄せる割合 w、舌尖の下げ幅（TTY を 0 または 0.4 下げる）、唇（そのまま、または LP を −0.5 以下にして広げる）の 16 通りを試した（[全候補の測定値](results/alveolopalatal/summary.json)）。

舌体を寄せるだけ（舌尖はそのまま）では、/i/ 文脈の重心が 6.0〜6.4 kHz のまま変わらない。舌尖を下げると、狭めが舌尖から前舌面に移る（/i/ 文脈の最小断面積が 0.14 → 0.38 cm²）。w = 1 と組み合わせたときだけ、3文脈とも重心が 3.9〜4.5 kHz にそろった。日本語の [ɕ] は唇を突き出さないので、唇を広げた `w1.00-tip0.4-spread` を `tt-alveolopalatal-fricative(a|i|u)` として話者ファイルに追加した（既存の形状は変えていない）。聴取での確認はまだ。

## 既知の限界

- ツは VTL の既定の `ts`、ジ・ヂは語中でも破擦音 `dz\` で、摩擦音 `z\` との使い分けはない。
- ウの非円唇化（`M`）は、音響的には測っていない。
- ɕ の形状は重心をそろえる基準で選んだだけで、目標の実測値に合わせたものではない。
- 無声化母音の声門の開き方と継続長は固定値で、無声化の度合いや位置の自然な揺れはない。
- フレーズ指令は呼気段落ごとに1つで、文末の下降や疑問の上昇はない。
- 継続長は固定ルールで、句頭・句末以外の伸縮はない。

## 再現

```sh
pip install pyopenjtalk numpy scipy matplotlib
cmake --build build-mac/gui --target VocalTractLabApi
python3 experiments/japanese-accent/run.py
python3 experiments/japanese-accent/consonants.py
python3 experiments/japanese-accent/alveolopalatal.py
```

API の dylib はこのブランチの backend からビルドしたものが必要（`M` と `s\` などを使うため）。`build-mac/gui/` 以外にあるときは `VTL_LIB`、話者ファイルは `VTL_SPEAKER` で指定する。ɕ の形状を別の話者ファイルに入れるには `alveolopalatal.py --install w1.00-tip0.4-spread` を使う。
