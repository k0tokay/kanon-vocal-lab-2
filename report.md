# 嘉音の母音形状と日本語 /r/ の合成実験

VTL 2.4の嘉音話者では、異なる声道形状がほぼ同じF1–F3を実現した。音声から調音を逆推定するときは、同じフォルマントを説明できる形状を複数残し、静止母音の音色と子音への移行も評価するのが妥当である。

## 母音形状と聞こえ

| 基準との比較 | 形状距離 | F1–F3の相対RMS誤差 | 静止伝達関数の差 |
|---|---:|---:|---:|
| 初回の /a/ 別解（顎を開いて探索） | 0.094 | 0.010% | 0.88 dB |
| 手動形状を再調整した /a/（a-compare） | 0.412 | 0.017% | 4.29 dB |
| 手動形状を再調整した /o/（o-compare） | 0.556 | 0.197% | 9.30 dB |

形状距離は独立な16パラメータの差を各可動域で割ったL2ノルム。伝達関数差は200 Hz〜8 kHzの対数振幅差のRMS。初回のみフォルマントの抽出条件が異なる。イヤホン試聴では初回の /a/ の違いは小さく、手動形状では /i/ への遷移よりも母音を保っている区間で音色の違いが分かりやすかった。これは聴取者の所感で、母音同定の成績は未測定である。[全候補の比較](experiments/vowel-inversion/results/shape-distances.csv)

## 等フォルマント面上で伝達関数の変化を選ぶ

可動域で正規化した形状パラメータを $x$、対数フォルマントを $f(x)=(\log F_1,\log F_2,\log F_3)$、周波数ごとの伝達関数の対数振幅を $h(x)$ とし、両者のヤコビアン $J_f,J_h$ を数値差分で求めた。$J_f$ の零空間の正規直交基底を列にもつ行列を $N$ とすると、変位 $Nv$ はF1–F3を一次近似で保つ。この接空間に制限した $J_hN$ の最小・最大特異値に対応する右特異ベクトル $v$ を選べば、同じ微小変位量で伝達関数の振幅がそれぞれ最も変わりにくい方向・変わりやすい方向に進める。嘉音の /a/ では、正規化距離がともに約0.045、各フォルマントのずれが0.02%以内の二点で、伝達関数差は **0.10 dB と1.18 dB** になった。[局所測定値](experiments/vowel-inversion/results/level-set.json)

数値積分では各点で方向を求め直し、一歩進むごとにフォルマントのずれを補正した。長距離への延長では既知の遠方解に向かう成分も加えた。/o/ の終点では、変わりにくい側は基準からの距離0.703で伝達関数差2.95 dB、変わりやすい側は距離0.555で8.95 dBだった。試聴WAVはどちらの母音も、変わりにくい経路、変わりやすい経路の順に基準形から終点までをたどる。[積分コード](experiments/vowel-inversion/integrate.py) · [積分経路と全137保存点](experiments/vowel-inversion/results/integrated-long/checkpoints.csv) · [/a/ の試聴](experiments/vowel-inversion/results/integrated-long/a-paths.wav) · [/o/ の試聴](experiments/vowel-inversion/results/integrated-long/o-paths.wav)

## /ara/ と今後使う /r/

従来版の舌尖閉鎖を使い、前後の /a/ だけを差し替えた。元のスコアでは基準形で7.5 msの閉鎖が生じたが、形状差の大きい4候補では閉鎖を検出できなかった。同じ舌尖目標のまま各形状に合わせて指令時刻を再計算すると、全候補で10〜15 msの閉鎖が生じた。静止母音のF1–F3が一致しても、次の子音を作るための時間条件は変わる。閉鎖はモデルの声道断面積から2.5 ms刻みで判定した。[閉鎖時刻の測定結果](experiments/vowel-inversion/results/large-ara/summary.json)

**今後の嘉音の /r/ には refined 版を採用する。** 音素記号は `4`。語中では主に先行母音、語頭では後続母音に応じた舌尖目標を使う。イヤホンで感じたクリック様の音が舌尖接触に由来する可能性はあるが、原因は未検証である。[refined版の試聴](experiments/vowel-inversion/results/integrated/ara-reference-fixed.wav) · [母音文脈と接触位置を調べた前川のMRI研究](bib/japanese-phonetics/Maekawa2023JapaneseR.pdf)

### 嘉音 /a/ の手動形状への経路

基準形状から各 fitted 形状までの直線と、直線の両端を固定し内部15点で顎・唇・舌の6パラメータを局所調整した折れ線を比較した。目的関数は F1–F3 の最大絶対対数比、開口条件は最小断面積 0.12 cm²。各経路を等しい区間数で513点測定した。

| 終点 | 直線の最大誤差 | 補正経路の最大誤差 | 終点の誤差 |
|---|---:|---:|---:|
| a-compare | 1.595 | 1.337 | 0.027 |
| a-compare-2 | 7.339 | 3.665 | 2.689 |

数値は最大絶対対数比の100倍。全測定点で最小断面積は 0.223 cm² を超えた。2番目の終点はそれ自体に誤差があり、この値より薄い許容帯での連結性を調べるには終点の再フィットが必要。離散測定では厳密な等値面の成分数や経路上の連続最大値は決まらない。

再現にはリポジトリ直下で以下を実行する。形状・フォルマント・断面積は experiments/vowel-inversion/results/fiber-paths/ に保存する。

```sh
cmake --build build-mac/gui --target VocalTractLabApi
clang++ -O2 -std=c++14 -Ibackend -Wl,-rpath,build-mac/gui experiments/vowel-inversion/fiber_path.cpp build-mac/gui/libVocalTractLabApi.dylib -o build-mac/fiber-path
python3 experiments/vowel-inversion/run_fiber_paths.py
```
