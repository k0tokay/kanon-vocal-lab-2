# 母音の等フォルマント解のトポロジー

嘉音の静止母音と F1–F3 がほぼ等しい声道形状を集め、その点群の形を調べる。結果は [report.md](report.md)。

- `sample.py`：レプリカ交換で形状を集め、可動域で正規化した座標と最大絶対対数フォルマント誤差を `results/kanon-a/samples.npz` に、各鎖の状態と乱数状態を `samples.chains.json` に保存する。同じ `--out` で再実行すると各鎖を `--steps` だけ延長し、`--seeds` に新しいシードがあれば鎖を追加する。分割して延長しても一度に回した場合と同じ鎖になる。
- `rips.py`：誤差帯ごとに点群を選び、正規化した調音空間の距離 r による Vietoris–Rips の H0–H2 を計算する。距離で張った辺の途中の音響は評価しない。
- `paths.py`：近傍グラフと最小全域木の辺を内部点で測り、途中も帯に収まる辺だけで成分数を数える。
- `connect.py`：分かれた成分を、帯の上を歩く経路（予測子・修正子）で最も近い別成分とつなぐ。
- `cluster.py`：辺を確かめたグラフで、両側20%以上の切り方のうち辺の比率（コンダクタンス）が最小のものを探し、同じ点数に間引いた /a/ と比べてくびれを判定する。
- `spectrum.py`：誤差帯ごとの大域PCAと、対数フォルマントのヤコビアンによる法線の向き。
- `h0_control.py`：薄い帯の H0 を、厚い帯から同数を無作為に選んだ点群と比べる。
- `outlines.py`：話者の形状に最も近いサンプルと、帯から散らばるように選んだサンプルの正中断面図を描く。
- `run.sh`：1母音分の上の一連を回す（`sh run.sh o`）。
- `measure.cpp`：フォルマントと形状の有効性。最小断面積は VTL が舌側面パラメータ（`TS2`, `TS3`）で底上げする前の値で 0.12 cm² 以上を要求する（底上げ後の値では舌と口蓋・口蓋垂の接触が開いて見える）。
- `colab.ipynb`：サンプリングと Rips を Colab で実行するだけのノートブック。
- `fiber_path.cpp`, `run_fiber_paths.py`, `fiber_persistence.py`：手動 fitted 形状への経路と、その経路上の H0。

手元（macOS）ではリポジトリ直下で次を実行する。NumPy と ripser が必要。

```sh
clang++ -shared -fPIC -std=c++14 -O2 -w -Ibackend experiments/vowel-topology/measure.cpp $(ls backend/*.cpp | grep -v SoundLib.cpp) -o build-mac/measure.so
python3 experiments/vowel-topology/sample.py --workers 3
python3 experiments/vowel-topology/rips.py
```
