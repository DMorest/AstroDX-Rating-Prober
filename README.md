# AstroDX B50 v0.19

从 AstroDX 本地 `cache` 解析游玩成绩，匹配曲库后计算 Rating，并显示 B35/B15 或全局 Best 50 成绩卡片与图片。

## v0.19 更新

- 项目 ZIP **不包含 `static/`**，由打包者自行放入素材。读取路径仍是项目根目录的 `static/`，无需更改或额外配置代码。
- 默认 Rating 规则为 **直接取 Best 50（不区分版本）**，仍可切换标准 B35 + B15。
- 每张成绩卡片在曲名右侧显示评级：SSS+（100.5% 起）、SSS（100% 起）、SS+（99.5% 起）、SS（99% 起）、S+（98% 起）、S（97% 起），以下依次为 AAA、AA、A、BBB、BB、B、C、D。
- 评级颜色：SSS+/SSS 彩色；SS+/SS/S+/S 金色；AAA/AA/A 红色；BBB/BB/B 蓝色；C 绿色；D 灰色。
- B50 绘图器改为从项目内的本地开源源码目录初始化，不会运行时访问 GitHub。

## B50 绘图器源码放置位置

源码仓库：[Shio796/maimai-b50-image-generator](https://github.com/Shio796/maimai-b50-image-generator)（MIT License）。

下载 v1.2.1 源码 ZIP：

`https://github.com/Shio796/maimai-b50-image-generator/archive/refs/tags/v1.2.1.zip`

解压后将 `maimai-b50-image-generator-1.2.1` 文件夹放到项目根目录的 `vendor/` 目录下。结构类似：

```text
astrodx-b50/
├─ app.py
├─ vendor/
│  └─ maimai-b50-image-generator-1.2.1/
│     ├─ LICENSE
│     └─ libs/
│        ├─ __init__.py
│        ├─ consts.py
│        ├─ image.py
│        └─ tools.py
└─ static/   # 由打包者提供，不包含在本项目 ZIP 中
```

首次生成时，应用会从 `vendor/` 中拷贝所需源码到 `data/upstream_b50/v1.2.1/` 并在该工作副本中做本地成绩适配，**原始下载目录不会被改写**。绘图使用本地 AstroDX 成绩，不调用水鱼账号查分服务，也不会把 cache 上传到第三方图片服务。

## static 素材目录

将完整 `static` 文件夹放到项目根目录，与 `app.py` 同级。至少需要包含 `mai/pic`、`mai/cover`、`mai/icon`、两种字体及绘图器要求的 PNG 素材。项目 ZIP 不会压缩或重新编码这些文件，因为它不包含 `static/`。

## cache 文件路径

- **iOS**：打开系统自带的「文件」App，进入 AstroDX 应用文件夹，选择其中名为 `cache` 的文件。
- **Android**：在文件管理器中进入 `/storage/emulated/0/Android/data/com.Reflektone.AstroDX/files`，选择其中名为 `cache` 的文件。

只需选择 `cache` 文件本身，不需要上传整个文件夹。

## 安装与运行

建议使用 Python 3.11 或更新版本：

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## 测试

```powershell
python -m unittest discover -s tests -v
```

## 许可证与资源说明

本项目绘图适配器基于 [Shio796/maimai-b50-image-generator](https://github.com/Shio796/maimai-b50-image-generator) 的 MIT 代码。其源代码应随打包分发并保留原 `LICENSE`。`static/` 游戏美术/曲绘资源的权利与代码 MIT 许可证不同，不应将代码许可证理解为对这些美术资源的授权。
