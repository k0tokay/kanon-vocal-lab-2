# vtlmap：VTL の解剖・調音空間からの写像とヤコビアン

解剖パラメタや調音パラメタから音響量（フォルマントなど）への写像を Python で組み立て、そのヤコビアンや等音響面に沿った積分を計算するための共通部品。

- [vtlmap.cpp](vtlmap.cpp)：VTL の backend を直接呼ぶ C の関数群（ctypes 用）。
  - 話者ファイルの読み込み。
  - 解剖パラメタ13個の取得と設定（`AnatomyParams::getFrom` / `setFor`）。
  - 年齢・性別からの解剖（`calcFromAge`）。
  - VTL の調音適応（`adaptArticulation`）とその逆変換。
  - 静的形状のフォルマント。
  - 面積関数。
  - 話者ファイルの書き出し。
- [vtlmap.py](vtlmap.py)：
  - `Tract`：上の関数のラッパ。解剖を変えたときだけ幾何を作り直す。
  - 汎用の数値計算：VTL に依存しない、任意の写像 `f(z) -> y` と箱型の範囲を受け取る関数。
    - `jacobian`：中心差分。範囲の端と、写像が定義されない側（`Invalid`）では片側差分にする。
    - `null_space`
    - `bounded_step`：範囲つき最小ノルム最小二乗。
    - `follow`：一部の座標を目標へ直線で動かし、残りの座標で `f` を一定に保つ予測子・修正子法。

## ビルド

リポジトリ直下で次を実行する。

```sh
clang++ -shared -fPIC -std=c++14 -O2 -w -Ibackend experiments/vtlmap/vtlmap.cpp $(ls backend/*.cpp | grep -v SoundLib.cpp) -o build-mac/vtlmap.so
```

## 使い方の例

```python
import vtlmap as vm
t = vm.Tract("speakers/fulkhisa-kanon/fulkhisa-kanon-v0-8-vtl24.speaker")
x = t.shape("a")
f, level, min_area, n = t.peaks(x, 3)          # F1-F3 [Hz]
J, y = vm.jacobian(lambda z: np.log(t.peaks(z)[0]), x, 0.01 * (hi - lo))
```

## 注意

- **フォルマント**：`Tract.formants` は VTL の `getFormants` そのもの。2048 点のスペクトル（23 Hz 刻み）に放物線補間をかけているので、差分をとると刻みの跡が出る。`Tract.peaks` は 8192 点（5.9 Hz 刻み）で dB の放物線補間をとるので、差分にはこちらを使う。
- **差分の刻み幅**：VTL の幾何（中心線、舌の肋、接触の処理）はパラメタに対して滑らかではない。刻みを小さくしても導関数は収束しない。
  - 嘉音の静止母音で、範囲の 1% 刻みと 0.5%・2% 刻みのヤコビアンを比べると、相対差は /a/ で約 10%、/i/ で 15〜60%、/u/ で 50〜90% だった。/u/ は最小断面積が 0.14 cm² と狭い。
  - ヤコビアンは「その刻み幅での割線」とみなし、予測子と修正子の方向にだけ使う。等音響面に乗っているかどうかは、実際の残差で判定する。
  - 片側にだけ跳びがある場所では、中心差分がその跳びを拾って符号まで変わる。例えば、接触の境界にいる /u/ で TCX を負に動かした場合で、1% 刻みの dF2/dTCX が 2.9、2% 刻みでは −23.8 になった。
    - `jacobian(..., scheme="minmod")` は、前進差分と後退差分の符号が一致すれば絶対値の小さいほうを、一致しなければ 0 をとる。
    - 嘉音の /u/ の例では、中心差分の修正子が 0.5% の誤差で止まった点で、minmod なら1回の反復で 0.04% まで下がった。
- **`correct`（修正子）**：Levenberg–Marquardt 法。受け入れた点ごとに自由座標のヤコビアンを計算し直す。古いヤコビアンを使い回すと、折れ目を越えたあとで方向を誤る。また、許容誤差 `tol` ぎりぎりで止めると次の予測子が外れるので、`tol/4` を狙って `tol` で受け入れる。
- **解剖の基準話者**：`setFor` は基準話者（既定は VTL に組み込みの成人男性。JD2 とほぼ同じ）を伸縮して解剖を作る。嘉音の話者ファイルは、組み込みの基準から作ると元と同じフォルマントになる。
- **VTL のバグ**：`AnatomyParams::setFor` / `adaptArticulation` は、存在しない4つ目の舌側面パラメタ（TS4）まで書き込んでいた。このブランチの backend で直してある。直さないと、解剖を変えるたびにメモリが壊れる。
- **`Tract` の解放**：`setFor` のあとで `VocalTract` を破棄すると VTL 内部で abort する。そのため `Tract` は解放しない。
