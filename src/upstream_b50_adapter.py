
"""Adapter for Shio796's MIT-licensed maimai B50 image generator.

The public renderer's score lookup path is not used. AstroDX's already-matched local
records are converted to the renderer's in-memory objects and passed directly to DrawBest.
The upstream static resource pack is supplied locally under the project root and validated locally.
Theme assets override the original pic assets on a per-file basis; missing files fall back
to the original resources without modifying the original asset directories.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.network import SYSTEM_PROXY

UPSTREAM_NAME = "Shio796/maimai-b50-image-generator"
UPSTREAM_VERSION = "v1.2.1"
ROOT = Path(__file__).resolve().parents[1]
VENDOR_DIR = ROOT / "data" / "upstream_b50" / UPSTREAM_VERSION
LOCAL_SOURCE_DIR = ROOT / "vendor" / "maimai-b50-image-generator"
SETTINGS_FILE = ROOT / "data" / "upstream_b50_settings.json"
SOURCE_FILES = ("libs/__init__.py", "libs/consts.py", "libs/image.py", "libs/tools.py", "LICENSE")

# Keys are the folder names under static/mai/pic/.
SUPPORTED_THEMES = {
    "circle_plus",
    "prism_plus",
    "buddies",
}

DIFFICULTY_INDEX = {
    "BASIC": 0,
    "ADVANCED": 1,
    "EXPERT": 2,
    "MASTER": 3,
    "RE:MASTER": 4,
    "REMASTER": 4,
}


def saved_static_dir() -> str:
    """Return the last user-selected upstream static directory, if any."""
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        value = data.get("static_dir") if isinstance(data, dict) else None
        return str(value) if isinstance(value, str) and value.strip() else str(ROOT / "static")
    except (OSError, ValueError, TypeError):
        return str(ROOT / "static")


def save_static_dir(path: str) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = SETTINGS_FILE.with_suffix(".tmp")
    temp.write_text(
        json.dumps({"static_dir": path}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp.replace(SETTINGS_FILE)


def resolve_static_dir(path: str | Path) -> Path:
    """Accept either the static folder itself or its parent directory."""
    static = Path(path).expanduser()
    try:
        static = static.resolve()
    except OSError:
        pass
    if (static / "mai" / "pic").is_dir():
        return static
    if (static / "static" / "mai" / "pic").is_dir():
        return static / "static"
    return static


def validate_static_dir(path: str | Path) -> tuple[bool, str]:
    """Validate the original static resource directory."""
    static = resolve_static_dir(path)
    pic = static / "mai" / "pic"
    cover = static / "mai" / "cover"
    icon = static / "mai" / "icon"

    if not pic.is_dir() or not cover.is_dir() or not icon.is_dir():
        return False, "static 资源结构不完整：需要 mai/pic、mai/cover、mai/icon。"

    required = [
        "b50_bg.png",
        "b50_score_basic.png",
        "b50_score_advanced.png",
        "b50_score_expert.png",
        "b50_score_master.png",
        "b50_score_remaster.png",
        "logo.png",
        "Name.png",
        "SD.png",
        "DX.png",
        "UI_FBR_Class_00.png",
        "UI_CMN_Shougou_Rainbow.png",
        "UI_DNM_DaniPlate_01.png",
        "UI_FBR_Class_00.png",
        *[f"UI_CMN_DXRating_{i:02d}.png" for i in range(1, 12)],
        *[f"UI_NUM_Drating_{i}.png" for i in range(10)],
        *[
            f"UI_TTR_Rank_{name}.png"
            for name in (
                "D", "C", "B", "BB", "BBB", "A", "AA", "AAA",
                "S", "Sp", "SS", "SSp", "SSS", "SSSp",
            )
        ],
    ]

    missing = [name for name in required if not (pic / name).is_file()]

    fallback_cover = cover / "11000.png"
    if not fallback_cover.is_file():
        missing.append("mai/cover/11000.png")

    if not (icon / "UI_Icon_000001.png").is_file():
        missing.append("mai/icon/UI_Icon_000001.png")

    han = [
        static / "ResourceHanRoundedCN-Bold.ttf",
        static / "font" / "ResourceHanRoundedCN-Bold.ttf",
    ]
    torus = [
        static / "Torus SemiBold.otf",
        static / "font" / "Torus SemiBold.otf",
    ]

    if not any(p.is_file() for p in han):
        missing.append("ResourceHanRoundedCN-Bold.ttf")
    if not any(p.is_file() for p in torus):
        missing.append("Torus SemiBold.otf")

    if missing:
        return False, "static 缺少必要文件：" + ", ".join(missing[:8])

    return True, str(static)


def _build_theme_pic_dir(static: Path, theme: str | None = None) -> Path:
    """Build an isolated pic directory with theme-first, original-second assets.

    Original static/mai/pic and the theme directory are read-only inputs.
    The merged result lives under data/upstream_b50/theme_pic/<theme>.
    Rebuild it on each render so switching themes cannot leave stale assets behind.
    """
    original_pic = static / "mai" / "pic"

    if not theme:
        return original_pic

    if theme not in SUPPORTED_THEMES:
        raise ValueError(
            f"不支持的 B50 主题：{theme}。可用主题："
            + ", ".join(sorted(SUPPORTED_THEMES))
        )

    theme_pic = original_pic / theme
    if not theme_pic.is_dir():
        # A missing theme directory gracefully falls back to the original assets.
        return original_pic

    merged_pic = ROOT / "data" / "upstream_b50" / "theme_pic" / theme
    merged_pic.parent.mkdir(parents=True, exist_ok=True)

    # Rebuild the directory to prevent old theme files surviving a switch or update.
    if merged_pic.exists():
        shutil.rmtree(merged_pic)
    merged_pic.mkdir(parents=True, exist_ok=True)

    # Copy all original files first; these are the fallback for missing theme assets.
    for source in original_pic.iterdir():
        if source.is_file():
            shutil.copy2(source, merged_pic / source.name)

    # Overlay theme files. Same-name theme assets take priority over originals.
    for source in theme_pic.iterdir():
        if source.is_file():
            shutil.copy2(source, merged_pic / source.name)

    return merged_pic


def _source_root_is_valid(path: Path) -> bool:
    return all((path / relative).is_file() for relative in SOURCE_FILES)


def _find_local_upstream_source() -> Path | None:
    """Find a locally supplied copy of the upstream repository; never access the network."""
    vendor_root = ROOT / "vendor"
    candidates: list[Path] = [LOCAL_SOURCE_DIR]

    if vendor_root.is_dir():
        candidates.extend(sorted(vendor_root.glob("maimai-b50-image-generator*")))

    seen: set[Path] = set()

    for candidate in candidates:
        try:
            candidate = candidate.resolve()
        except OSError:
            continue

        if candidate in seen or not candidate.is_dir():
            continue

        seen.add(candidate)

        if _source_root_is_valid(candidate):
            return candidate

        # GitHub's downloaded source archive may have one enclosing versioned directory.
        try:
            children = sorted(p for p in candidate.iterdir() if p.is_dir())
        except OSError:
            children = []

        for child in children:
            if _source_root_is_valid(child):
                return child

    return None


def _ensure_upstream_source(
    network_mode: str | None = None,
    proxy_url: str | None = None,
) -> Path:
    """Prepare a patched working copy from the locally supplied upstream repository.

    The packaged app never fetches renderer code from GitHub at runtime.
    """
    libs_dir = VENDOR_DIR / "libs"
    needed = [
        libs_dir / "consts.py",
        libs_dir / "image.py",
        libs_dir / "tools.py",
    ]

    if all(file.is_file() for file in needed):
        return VENDOR_DIR

    source_root = _find_local_upstream_source()
    if source_root is None:
        raise RuntimeError("本地 B50 绘图引擎文件不完整，无法生成图片。")

    temp_dir = VENDOR_DIR.with_name(VENDOR_DIR.name + ".tmp")
    if temp_dir.exists():
        shutil.rmtree(temp_dir)

    try:
        for relative in SOURCE_FILES:
            source = source_root / relative
            if not source.is_file():
                raise RuntimeError("本地 B50 绘图引擎文件不完整，无法生成图片。")

            destination = temp_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

        source_hash = hashlib.sha256()
        for relative in SOURCE_FILES:
            source_hash.update((temp_dir / relative).read_bytes())

        (temp_dir / "UPSTREAM_SOURCE.json").write_text(
            json.dumps(
                {
                    "repository": UPSTREAM_NAME,
                    "version": UPSTREAM_VERSION,
                    "source": "local vendor directory",
                    "sha256": source_hash.hexdigest(),
                    "adapter": "AstroDX local-record adapter; remote prober lookups disabled",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        if VENDOR_DIR.exists():
            shutil.rmtree(VENDOR_DIR)

        VENDOR_DIR.parent.mkdir(parents=True, exist_ok=True)
        temp_dir.replace(VENDOR_DIR)

    except Exception:
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise

    return VENDOR_DIR


def _patch_upstream_source(source_dir: Path) -> None:
    """Adapt only the upstream module boundaries needed for in-memory local records."""
    libs_dir = source_dir / "libs"

    # Keep importing this package from triggering upstream CLI/account query imports.
    (libs_dir / "__init__.py").write_text(
        '"""Shio796 B50 renderer loaded through the AstroDX local-score adapter.\n'
        'Original project is MIT licensed; see the adjacent LICENSE file.\n"""\n',
        encoding="utf-8",
    )

    consts_path = libs_dir / "consts.py"
    consts = consts_path.read_text(encoding="utf-8")

    consts = consts.replace(
        "static: Path = root / 'static'",
        "static: Path = Path(os.environ.get('ASTRODX_B50_STATIC', root / 'static'))",
    )
    consts = consts.replace(
        "HAN: Path = static / 'ResourceHanRoundedCN-Bold.ttf'",
        "HAN: Path = next((p for p in (static / 'ResourceHanRoundedCN-Bold.ttf', "
        "static / 'font' / 'ResourceHanRoundedCN-Bold.ttf') if p.is_file()), "
        "static / 'ResourceHanRoundedCN-Bold.ttf')",
    )
    consts = consts.replace(
        "TORUS: Path = static / 'Torus SemiBold.otf'",
        "TORUS: Path = next((p for p in (static / 'Torus SemiBold.otf', "
        "static / 'font' / 'Torus SemiBold.otf') if p.is_file()), "
        "static / 'Torus SemiBold.otf')",
    )

    # Redirect the upstream renderer's pic directory to the merged theme assets.
    # Handle common quote/type annotation variations in upstream consts.py.
    maimai_pattern = re.compile(
        r"(?m)^(?P<indent>[ \t]*)maimaidir[ \t]*(?::[^=\n]+)?=[^\n]*$"
    )
    maimai_replacement = (
        r"\g<indent>maimaidir: Path = "
        "Path(os.environ.get('ASTRODX_B50_PIC', static / 'mai' / 'pic'))"
    )
    consts, maimai_count = maimai_pattern.subn(maimai_replacement, consts, count=1)

    if (
        "ASTRODX_B50_STATIC" not in consts
        or "from pathlib import Path" not in consts
        or maimai_count != 1
    ):
        raise RuntimeError(
            "无法安全适配上游 consts.py 的素材目录定义；"
            "请检查本地上游版本的 maimaidir 定义。"
        )

    consts_path.write_text(consts, encoding="utf-8")

    image_path = libs_dir / "image.py"
    image = image_path.read_text(encoding="utf-8")

    image = image.replace(
        "from typing import List, Union, Tuple",
        "from typing import Any, List, Union, Tuple",
    )
    image = image.replace(
        "from .models import ChartInfo, UserInfo",
        "ChartInfo = Any\nUserInfo = Any",
    )
    image = image.replace("from .api import MusicList", "MusicList = Any")
    image = image.replace("from .config import Config", "Config = Any")

    old_summary = """        self._to.draw(
            570, 172, 17,
            f'B35: {sdrating} + B15: {dxrating} = {self.rating}',
            (0, 0, 0, 255), 'mm', 3, (255, 255, 255, 255)
        )"""

    new_summary = """        rating_summary = config.get('rating_summary') or f'B35: {sdrating} + B15: {dxrating} = {self.rating}'
        self._to.draw(
            570, 172, 17,
            rating_summary,
            (0, 0, 0, 255), 'mm', 3, (255, 255, 255, 255)
        )"""

    if old_summary in image:
        image = image.replace(old_summary, new_summary, 1)

    # Let the app override local Dan rank / friend-versus-class badges.
    old_match = (
        "        match_level = Image.open("
        "maimaidir / self._find_match_level_picture()).resize((80, 32))"
    )
    new_match = (
        "        match_level_file = config.get('match_level_file') "
        "or self._find_match_level_picture()\n"
        "        match_level = Image.open("
        "maimaidir / match_level_file).convert('RGBA').resize((80, 32))"
    )
    if old_match in image:
        image = image.replace(old_match, new_match, 1)

    old_class = (
        "        class_level = Image.open("
        "maimaidir / 'UI_FBR_Class_00.png').resize((90, 54))"
    )
    new_class = (
        "        class_level_file = config.get('class_level_file') "
        "or 'UI_FBR_Class_00.png'\n"
        "        class_level = Image.open("
        "maimaidir / class_level_file).convert('RGBA').resize((90, 54))"
    )
    if old_class in image:
        image = image.replace(old_class, new_class, 1)

    # Absolute image paths are used for selected LXNS assets cached outside static/.
    old_plate_branch = "        if isinstance(plate_name, int):"
    new_plate_branch = (
        "        if isinstance(plate_name, str) and Path(plate_name).is_file():\n"
        "            plate = Image.open(plate_name).convert('RGBA')\n"
        "        elif isinstance(plate_name, int):"
    )
    if old_plate_branch in image:
        image = image.replace(old_plate_branch, new_plate_branch, 1)

    old_icon_branch = "        if isinstance(icon_name, int):"
    new_icon_branch = (
        "        if isinstance(icon_name, str) and Path(icon_name).is_file():\n"
        "            icon = Image.open(icon_name).convert('RGBA')\n"
        "        elif isinstance(icon_name, int):"
    )
    if old_icon_branch in image:
        image = image.replace(old_icon_branch, new_icon_branch, 1)

    if (
        "from .models import ChartInfo, UserInfo" in image
        or "from .api import MusicList" in image
        or "from .config import Config" in image
    ):
        raise RuntimeError("无法安全适配上游 image.py 的本地数据入口。")

    if "rating_summary = config.get('rating_summary')" not in image:
        raise RuntimeError("无法安全适配上游图片中的 Rating 说明文字。")

    image_path.write_text(image, encoding="utf-8")

    # Avoid stale bytecode when regenerating after a renderer update.
    shutil.rmtree(libs_dir / "__pycache__", ignore_errors=True)


def _rank_label(achievement: float) -> str:
    """Match the icon names expected by Shio796's renderer."""
    ranks = [
        (100.5, "sssp"),
        (100.0, "SSS"),
        (99.5, "ssp"),
        (99.0, "SS"),
        (98.0, "sp"),
        (97.0, "S"),
        (94.0, "AAA"),
        (90.0, "AA"),
        (80.0, "A"),
        (75.0, "bbb"),
        (70.0, "bb"),
        (60.0, "b"),
        (50.0, "c"),
        (0.0, "d"),
    ]
    return next(label for threshold, label in ranks if achievement >= threshold)


def _song_id(record: dict[str, Any], index: int) -> int:
    for key in ("song_id", "cover_id", "id"):
        value = str(record.get(key) or "").strip()
        if value.isdigit():
            return int(value)

    # Use a stable numeric display id when the catalog provider has no numeric id.
    identity = "|".join(
        str(record.get(k, ""))
        for k in ("title", "difficulty", "song_type", "version")
    )
    return 900000 + int(hashlib.sha256(identity.encode("utf-8")).hexdigest()[:7], 16) + index


def _difficulty_index(record: dict[str, Any]) -> int:
    difficulty = re.sub(r"\s+", "", str(record.get("difficulty") or "")).upper()
    difficulty = {"REMASTER": "RE:MASTER"}.get(difficulty, difficulty)

    if difficulty not in DIFFICULTY_INDEX:
        raise ValueError(
            f"上游 B50 模板不支持难度：{difficulty}（只支持 BASIC 至 Re:MASTER）。"
        )

    return DIFFICULTY_INDEX[difficulty]


def _song_type(record: dict[str, Any]) -> str:
    raw = str(record.get("song_type") or record.get("type") or "").strip().upper()

    if raw in {"SD", "STD", "STANDARD"}:
        return "SD"
    if raw in {"DX", "DELUXE"}:
        return "DX"

    # Some sources do not identify SD/DX consistently; prefer the chart row's explicit marker.
    if "SD" in raw and "DX" not in raw:
        return "SD"

    return "DX"


def _clear_type_to_fc(record: dict[str, Any]) -> str:
    """Translate AstroDX cache clearType into the renderer/API FC badge codes.

    AstroDX cache uses 2=clear, 3=FC, 4=FC+, 5=AP, 6=AP+.
    Only FC/AP achievements are surfaced by the score cards and B50 poster.
    """
    try:
        clear_type = int(record.get("clear_type") or 0)
    except (TypeError, ValueError):
        return ""

    return {
        3: "fc",
        4: "fcp",
        5: "ap",
        6: "app",
    }.get(clear_type, "")


def _record_to_chart_info(record: dict[str, Any], song_id: int) -> SimpleNamespace:
    try:
        achievement = float(record.get("achievement") or 0)
        constant = float(record.get("constant") or record.get("ds") or 0)
        score = int(record.get("dx_score") or 0)
        rating = int(record.get("rating") or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"成绩记录字段格式不正确：{record.get('title', '未知曲目')}"
        ) from exc

    if constant <= 0 or achievement <= 0:
        raise ValueError(
            f"成绩记录缺少有效定数或达成率：{record.get('title', '未知曲目')}"
        )

    return SimpleNamespace(
        achievements=achievement,
        ds=constant,
        dxScore=score,
        # The public renderer consumes API-style values: fc / fcp / ap / app.
        fc=_clear_type_to_fc(record),
        fs="",
        level=str(
            record.get("level_text")
            or record.get("level")
            or record.get("difficulty")
            or ""
        ),
        level_index=_difficulty_index(record),
        level_label=str(record.get("level_text") or record.get("difficulty") or ""),
        ra=rating,
        rate=_rank_label(achievement),
        song_id=song_id,
        title=str(record.get("title") or "未知曲目"),
        type=_song_type(record),
    )


def _music_list_for(
    records: list[dict[str, Any]],
    old_records: list[dict[str, Any]],
    new_records: list[dict[str, Any]],
):
    note_map: dict[int, list[int]] = {}
    indexed = [(row, i) for i, row in enumerate(records)]
    record_ids = {id(row): _song_id(row, i) for row, i in indexed}

    for row, i in indexed:
        sid = record_ids[id(row)]
        notes = row.get("notes") or row.get("total_notes") or 0

        try:
            note_count = int(notes or 0)
        except (TypeError, ValueError):
            note_count = 0

        if note_count <= 0:
            raise ValueError(
                f"《{row.get('title', '未知曲目')}》没有可用的谱面音符数，无法计算上游 DX 星徽。"
                "请换用包含 note count 的曲库数据源后刷新曲库。"
            )

        per_diff = note_map.setdefault(sid, [0, 0, 0, 0, 0])
        per_diff[_difficulty_index(row)] = note_count

    class LocalMusic:
        def __init__(self, sid: int, note_counts: list[int]):
            self.id = str(sid)
            # Shio796's renderer only sums this tuple to calculate the DX score maximum.
            self.charts = [
                SimpleNamespace(notes=(0, 0, 0, 0, max(1, count)))
                for count in note_counts
            ]

    class LocalMusicList:
        def __init__(self, data: dict[int, list[int]]):
            self._music = {
                str(sid): LocalMusic(sid, counts)
                for sid, counts in data.items()
            }

        def by_id(self, music_id: str | int):
            key = str(music_id)
            if key not in self._music:
                raise ValueError(f"本地 B50 记录缺少曲目元数据：{key}")
            return self._music[key]

    chart_items = [
        _record_to_chart_info(row, record_ids[id(row)])
        for row in records
    ]
    old_ids = {id(row) for row in old_records}

    sd_best = [
        item
        for row, item in zip(records, chart_items)
        if id(row) in old_ids
    ]
    dx_best = [
        item
        for row, item in zip(records, chart_items)
        if id(row) not in old_ids
    ]

    # Return the upstream UserInfo shape as attribute objects; no prober JSON is loaded.
    return sd_best, dx_best, LocalMusicList(note_map)


def generate_upstream_b50_png(
    old_records: list[dict[str, Any]],
    new_records: list[dict[str, Any]],
    total_rating: int,
    display_name: str,
    static_path: str,
    *,
    network_mode: str = SYSTEM_PROXY,
    proxy_url: str | None = None,
    rating_summary: str | None = None,
    icon_asset_path: str | None = None,
    plate_asset_path: str | None = None,
    match_level_file: str | None = None,
    class_level_file: str | None = None,
    theme: str | None = None,
) -> bytes:
    """Render selected local records with Shio796's published B50 renderer.

    `theme` accepts None (original) or one of:
    `circle_plus`, `prism_plus`, `buddies`.
    """
    valid, description = validate_static_dir(static_path)
    if not valid:
        raise ValueError(description)

    static = Path(description)
    save_static_dir(str(static))

    # Construct theme assets before importing upstream modules, because consts.py
    # resolves maimaidir during import.
    theme_pic = _build_theme_pic_dir(static, theme)

    source_dir = _ensure_upstream_source(network_mode, proxy_url)
    _patch_upstream_source(source_dir)

    # Modules cache asset paths at import time, so reload only the isolated upstream namespace.
    for module_name in list(sys.modules):
        if module_name == "libs" or module_name.startswith("libs."):
            del sys.modules[module_name]

    source_str = str(source_dir)
    if source_str in sys.path:
        sys.path.remove(source_str)
    sys.path.insert(0, source_str)

    os.environ["ASTRODX_B50_STATIC"] = str(static)
    os.environ["ASTRODX_B50_PIC"] = str(theme_pic)

    image_module = importlib.import_module("libs.image")

    configure_cover_network = getattr(image_module, "configure_cover_network", None)
    if callable(configure_cover_network):
        configure_cover_network(network_mode, proxy_url)

    DrawBest = image_module.DrawBest
    all_records = list(old_records) + list(new_records)

    sd_best, dx_best, local_music = _music_list_for(
        all_records,
        list(old_records),
        list(new_records),
    )

    user_info = SimpleNamespace(
        nickname=(display_name or "AstroDX Player").strip()[:24] or "AstroDX Player",
        plate=None,
        additional_rating=1,
        rating=int(total_rating),
        charts=SimpleNamespace(sd=sd_best, dx=dx_best),
    )

    drawer = DrawBest(user_info)

    summary = rating_summary or (
        f"B35: {sum(x.ra for x in sd_best)} + "
        f"B15: {sum(x.ra for x in dx_best)} = {int(total_rating)}"
    )

    # The selected badge files are resolved against the merged theme directory.
    # Since that directory contains original fallback files, existing behavior is retained.
    for selected_file, label in (
        (match_level_file, "段位"),
        (class_level_file, "友人对战阶级"),
    ):
        if selected_file is not None and (
            Path(selected_file).name != selected_file
            or not (theme_pic / selected_file).is_file()
        ):
            raise ValueError(f"所选{label}素材不存在或路径无效：{selected_file}")

    config = {
        "plate": plate_asset_path if plate_asset_path else 1,
        "icon": icon_asset_path if icon_asset_path else None,
        "plate_override": True,
        "rating_summary": summary,
        "match_level_file": match_level_file,
        "class_level_file": class_level_file,
    }

    image = asyncio.run(drawer.draw(local_music, config))

    from io import BytesIO as _BytesIO

    output = _BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
