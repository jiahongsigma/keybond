<h1 align="center">Keybond</h1>

<p align="center">
  <a href="https://langvector.com"><img src="https://raw.githubusercontent.com/jiahongsigma/keybond/main/assets/jdai-tool-mark.svg" width="26" height="26" alt="" align="absmiddle"></a>
  <a href="https://langvector.com"><b>Jdai Tool</b></a>
</p>

<p align="center">
  <a href="https://github.com/jiahongsigma/keybond/actions/workflows/tests.yml"><img alt="tests" src="https://github.com/jiahongsigma/keybond/actions/workflows/tests.yml/badge.svg"></a>
  <a href="https://pypi.org/project/keybond/"><img alt="PyPI" src="https://img.shields.io/pypi/v/keybond.svg"></a>
  <a href="https://github.com/jiahongsigma/keybond/blob/main/LICENSE"><img alt="license: MIT" src="https://img.shields.io/badge/license-MIT-blue.svg"></a>
  <img alt="python 3" src="https://img.shields.io/badge/python-3-blue.svg">
  <img alt="platform: Linux" src="https://img.shields.io/badge/platform-Linux-lightgrey.svg">
  <img alt="Bluetooth: BlueZ" src="https://img.shields.io/badge/Bluetooth-BlueZ-0a66c2.svg">
</p>

<p align="center"><a href="https://github.com/jiahongsigma/keybond/blob/main/README.md">English</a> | <b>简体中文</b></p>

<p align="center"><b>在 Linux 上配对蓝牙键盘时，桌面弹出的配对码一闪就消失、根本来不及看？用这个工具。</b></p>

配对蓝牙键盘时，电脑会显示一串数字，你要在键盘上把它敲出来。有些 Linux 桌面上，显示数字的窗口过一会儿
就自己关掉了，配对永远完成不了。keybond 改在终端里显示这串数字，并且一直留在屏幕上，直到你敲完为止。

## 快速开始

```
pipx install --system-site-packages keybond
keybond
```

或者什么都不装，克隆后直接运行：

```
git clone https://github.com/jiahongsigma/keybond.git
cd keybond
./keybond.py
```

两种方式接下来都一样：

1. 让键盘进入配对模式（按住配对键或组合键，直到指示灯闪烁）。
2. 把 keybond 显示的数字敲在**新键盘上**，再按新键盘上的 `Enter`。

就这样。键盘配对完成，以后会自动重连。

## 运行效果

```
  Put the keyboard in pairing mode now.
  ✓ Found Majestouch Convertible 2 (AA:BB:CC:DD:EE:FF)

  Type this ON THE NEW KEYBOARD, then press Enter:

  ╔═══════════════════════════════════════════════════╗
  ║                                                   ║
  ║   █████    ███    ████    █████   █  █    █████   ║
  ║   █       █   █       █      █    █  █       █    ║
  ║   ████     ███     ███      █     █████     █     ║
  ║       █   █   █       █    █         █     █      ║
  ║   ████     ███    ████     █         █     █      ║
  ║                                                   ║
  ╚═══════════════════════════════════════════════════╝

  ✓ Paired
  ✓ Trusted, so it reconnects by itself
  ✓ Connected
```

工具本身的提示是英文的。上面几行的意思依次是：请让键盘进入配对模式；找到了键盘；把这串数字敲在新键盘上再按
Enter；已配对；已设为受信任（以后自动重连）；已连接。

## 第一次没成功怎么办

**找不到键盘。** 检查三件事：

- 键盘的配对指示灯在闪，而且离电脑够近。
- 桌面的蓝牙设置窗口已经关掉。它开着的时候可能会把配对取消掉。
- 这把键盘以前没有和这台电脑配对过。如果配对过，keybond 会告诉你；用下面的命令重新配对：

  ```
  ./keybond.py --again
  ```

找不到键盘时，keybond 会列出它在附近看到了哪些设备，万一你的键盘是以别的名字出现的。

**提示 “Pairing failed”（配对失败）。** keybond 会说明原因，并在键盘重新有响应时自动再试。通常只要让键盘
重新进入配对模式，再敲一次数字就行。

**提示 “Missing system library”（缺少系统库）。** 安装下面两个包，并用系统自带的 Python 运行，不要用
virtualenv 或 conda 里的 Python：

```
sudo apt install python3-dbus python3-gi
/usr/bin/python3 keybond.py
```

**附近有好几把键盘。** keybond 会把它们列出来。带上你想要的那把的地址重新运行：

```
./keybond.py AA:BB:CC:DD:EE:FF
```

## 键盘配对过，但现在连不上

这是另一种常见的麻烦：键盘本来能用，现在没反应了。

```
./keybond.py status
./keybond.py fix
```

`status` 列出和这台电脑配对过的键盘，以及每一把是否已连接。

`fix` 检查其中一把。它会先修好电脑这一侧能修的问题（没被设为“受信任”的键盘不会自动重连），然后请你
按一下键盘上的任意键把它唤醒，并等它连回来。最后告诉你结论：

```
  Checking Convertible 2 TKL (AA:BB:CC:DD:EE:FF)

  ✓ Paired with this computer
  ✓ Trusted, so it may reconnect by itself

  Press any key on the keyboard now, to wake it.
  ✗ Still not connected

  This computer's side is fine. The keyboard is not answering.
    Is it switched on, with charge in its batteries?
    Is it on the slot it used with this computer?
    Is it connected to another computer, phone or tablet right now?
    Is it within a couple of metres?
    If none of that helps, pair it afresh:  keybond --again AA:BB:CC:DD:EE:FF
```

上面的意思是：电脑这一侧没问题，是键盘没有应答；请检查它是否开机有电、是否在原来的配对槽位、是否正连着
别的电脑或手机、是否离得够近；都不行就用 `--again` 重新配对。

它也能认出“键盘已经忘了这台电脑”或“键盘正处于配对模式”这两种情况，并提示你重新配对。`fix` 自己绝不会
删除配对记录。

## 需要什么

- 装有 BlueZ 的 Linux。BlueZ 是标准的蓝牙服务，Ubuntu、Debian、Fedora 等大多数发行版都自带。
- Python 3。Ubuntu 桌面版已经带齐了其余依赖。
- 另一把能用的键盘，用来敲命令：笔记本自带的键盘，或一把 USB 键盘。

不需要 root 权限。keybond 只有一个文件。

---

以下是参考内容，点击标题展开。

<details>
<summary><b>每条提示的含义和对策</b></summary>

| 你看到的 | 意思 | 怎么办 |
|---|---|---|
| `No keyboard in pairing mode showed up` | 规定时间内没找到键盘 | 见上面的“找不到键盘” |
| `Pairing failed (AuthenticationFailed)` | 数字不对，或者没按 Enter | 在新键盘上重新敲一遍，再按它的 Enter |
| `Pairing failed (AuthenticationCanceled)` | 配对被别的程序取消了 | 关掉桌面的蓝牙设置窗口 |
| `Pairing failed (AuthenticationRejected)` | 键盘拒绝了配对 | 清除键盘上的配对槽位 |
| `Pairing failed (AuthenticationTimeout)` | 没有及时敲完数字 | 再试一次，动作快一点 |
| `Pairing failed (ConnectionAttemptFailed)` | 键盘不再响应 | 让它重新进入配对模式 |
| `More than one keyboard is in pairing mode` | 找到了不止一把键盘 | 带上地址重新运行 |
| `… paired without asking for a code` | 没有任何东西能证明应答的是哪台设备 | 只有确定是你自己的键盘才回答 `y` |
| `Bluetooth is switched off` | 蓝牙适配器关着 | 打开蓝牙 |
| `Cannot reach the Bluetooth service` | 蓝牙服务没在运行 | `systemctl status bluetooth` |

真正失败五次，或者等待超时，keybond 就会放弃。

</details>

<details>
<summary><b>安装成命令</b></summary>

keybond 已发布在 [PyPI](https://pypi.org/project/keybond/) 上。用 [pipx](https://pipx.pypa.io)
安装（Debian 或 Ubuntu 上先 `sudo apt install pipx`）：

```
pipx install --system-site-packages keybond
```

装好后，本页所有写 `./keybond.py` 的地方都可以直接用 `keybond` 命令。

`--system-site-packages` 很重要：它让 keybond 能用到发行版自带的 D-Bus 绑定（`python3-dbus`、
`python3-gi`）。keybond 不通过 pip 拉取它们，因为 pip 得从源码编译。

</details>

<details>
<summary><b>选项</b></summary>

| 命令 | 作用 |
|---|---|
| `keybond` | 配对当前唯一处于配对模式的键盘 |
| `keybond AA:BB:CC:DD:EE:FF` | 配对这把键盘 |
| `keybond --again [地址]` | 先删掉旧的配对记录，再重新配对 |
| `keybond status` | 列出已配对的键盘及其状态 |
| `keybond fix [地址]` | 查明已配对的键盘为什么连不上 |

| 选项 | 含义 |
|---|---|
| `--timeout SECONDS` | 配对时等待键盘出现的秒数（默认 180） |
| `--wait SECONDS` | `fix` 等待键盘应答的秒数（默认 30） |
| `--adapter NAME` | 使用哪个蓝牙适配器，例如 `hci0`（默认用第一个） |
| `--log FILE` | 把这次配对的带时间戳记录追加到 `FILE` |
| `--plain` | 不显示标志、大号数字、颜色和倒计时。输出不是终端时自动启用 |
| `--help` | 命令、选项和简短的操作步骤 |
| `--version` | 显示版本号 |

随时可以按 `Ctrl+C` 停止。

退出码：`0` 配对成功或已连接，`1` 配对失败或仍未连接，`2` 没找到键盘（或找到多把），`3` 蓝牙关闭或无法访问。

</details>

<details>
<summary><b>安全吗？</b></summary>

一把已配对、受信任的键盘可以在你的电脑上输入任何内容，所以必须确认被配对的设备真的是你的。

- 在键盘上敲出数字就是证明。看不到你屏幕的设备敲不出这串数字。
- 如果某台设备不需要数字就配对了，或者它自己显示数字而不是让你输入，keybond 会先问你要不要保留。回答“否”
  就会把它删掉。
- 运行期间，keybond 会拒绝任何其他设备的配对请求。
- 设备发来的名称在显示前会去掉控制字符。

</details>

<details>
<summary><b>工作原理</b></summary>

keybond 通过 D-Bus 和蓝牙服务（`bluetoothd`）通信：

1. 注册自己的配对代理（agent），这样索要配对码的请求会发给它，而不是发给桌面；
2. 开始扫描，等待一把此刻可见、尚未配对的键盘；
3. 调用 `Pair`，并显示蓝牙服务交给代理的配对码；
4. 设置 `Trusted`，再调用 `Connect`。

退出时它会停止扫描并注销代理，桌面重新接管。它只是绕开了那个会消失的窗口，并没有修复桌面本身。

</details>

<details>
<summary><b>报告配对问题</b></summary>

无论是报告给 keybond，还是报告给你所用桌面的维护者，一份配对过程的记录都很有帮助：

```
./keybond.py --log pairing.log
```

记录里有版本信息、你的键盘名称和地址、蓝牙服务发来的每个请求，以及结果。附近的其他设备不会被记录。记录中
包含配对码，但配对结束后它就没用了。

维护者通常还会要无线层面的抓包。配对时在另一个终端里运行：

```
sudo btmon -w pairing.btsnoop
```

</details>

<details>
<summary><b>现状与测试</b></summary>

还很早期。在真实硬件上（Ubuntu 24.04、BlueZ 5.72）验证过的有：用老式 PIN 码配对一把 Filco Majestouch
Convertible 2；对一把不在附近的已配对键盘运行 `fix`。其余都只在模拟的蓝牙服务上测试过：较新的 passkey 配对
方式、低功耗蓝牙（BLE）键盘，以及其他失败情形。欢迎提供其他键盘和发行版上的使用反馈。

```
python3 -m unittest discover -s tests
```

`tests/test_keybond.py` 测试辅助函数。`tests/test_flow.py` 在一条私有 D-Bus 上，让工具对着模拟蓝牙服务 `tests/fake_bluez.py`
完整跑一遍，不会碰到真实硬件。大约需要两分钟。

</details>

## 许可证

MIT © Jiahong Dai
