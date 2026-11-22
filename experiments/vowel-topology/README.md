# 母音の等フォルマント解のトポロジー

嘉音の静止 /a/ と F1–F3 がほぼ等しい声道形状を集め、その点群の形をパーシステントホモロジーで調べる。

- `sample.py`：レプリカ交換で形状を集め、可動域で正規化した座標と最大絶対対数フォルマント誤差を `results/kanon-a/samples.npz` に、各鎖の状態と乱数状態を `samples.chains.json` に保存する。同じ `--out` で再実行すると各鎖を `--steps` だけ延長し、`--seeds` に新しいシードがあれば鎖を追加する。分割して延長しても一度に回した場合と同じ鎖になる。
- `rips.py`：誤差帯ごとに点群を選び、正規化した調音空間の距離 r による Vietoris–Rips の H0–H2 を計算する。距離で張った辺の途中の音響は評価しない。
- `colab.ipynb`：上の2つを Colab で実行するだけのノートブック。
- `fiber_path.cpp`, `run_fiber_paths.py`, `fiber_persistence.py`：手動 fitted 形状への経路と、その経路上の H0。

手元（macOS）ではリポジトリ直下で次を実行する。NumPy と ripser が必要。

```sh
cmake --build build-mac/gui --target VocalTractLabApi
clang++ -shared -fPIC -std=c++14 -O2 -Ibackend experiments/vowel-topology/measure.cpp build-mac/gui/libVocalTractLabApi.dylib -Wl,-rpath,@loader_path/gui -o build-mac/measure.so
python3 experiments/vowel-topology/sample.py --workers 3
python3 experiments/vowel-topology/rips.py
```
