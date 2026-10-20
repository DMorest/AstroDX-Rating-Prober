"""图像生成相关；曲绘从 SaltMeta 在线获取。"""

from io import BytesIO
from pathlib import Path
from typing import Any, List, Union, Tuple, Optional
import os
import requests

from PIL import Image, ImageDraw, ImageFont

ChartInfo = Any
UserInfo = Any
from .consts import (
    root, customdir, maimaidir, icondir, platedir, coverdir, HAN, TORUS, fcl, fsl, score_rank_l
)
MusicList = Any
from .tools import dx_score, coloum_width, change_column_width, plate_finder
Config = Any

# SaltMeta documents covers as /covers/00 + zero-padded ID (positions 3-6) + .png.
_SALTMETA_COVER_URL = "https://meta.salt.realtvop.top/covers/00{suffix}.png"
_CACHE_ROOT = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
_COVER_CACHE_DIR = _CACHE_ROOT / "AstroDX-Rating-Prober" / "saltmeta-covers"
_COVER_SESSION: Optional[requests.Session] = None


def configure_cover_network(network_mode: str = "system", proxy_url: Optional[str] = None) -> None:
    """Use the app's selected network route for online cover downloads."""
    global _COVER_SESSION
    from src.network import make_session
    _COVER_SESSION = make_session(network_mode, proxy_url)


def _get_cover_session() -> requests.Session:
    global _COVER_SESSION
    if _COVER_SESSION is None:
        from src.network import make_session
        _COVER_SESSION = make_session("system", None)
    return _COVER_SESSION


def _cover_id_candidates(music_id: Union[int, str]) -> List[int]:
    """Normalize renderer-specific offsets into SaltMeta canonical IDs."""
    pending = [int(music_id)]
    seen = set()
    candidates: List[int] = []
    while pending:
        candidate = pending.pop(0)
        if candidate in seen:
            continue
        seen.add(candidate)
        if 0 < candidate < 10000:
            candidates.append(candidate)
        # Some local records use +100000; DX records may use +10000.
        if candidate > 100000:
            pending.append(candidate - 100000)
        if candidate > 10000:
            pending.append(candidate - 10000)
    return candidates


def _saltmeta_cover_url(canonical_id: int) -> str:
    suffix = str(canonical_id).zfill(6)[2:]
    return _SALTMETA_COVER_URL.format(suffix=suffix)


def _load_cached_cover(cache_path: Path) -> Optional[Image.Image]:
    if not cache_path.is_file():
        return None
    try:
        with Image.open(cache_path) as cached:
            image = cached.convert("RGBA")
            image.load()
            return image
    except (OSError, ValueError):
        try:
            cache_path.unlink()
        except OSError:
            pass
        return None


def _download_cover(canonical_id: int) -> Image.Image:
    # Reuse the application's configured session so custom/direct/system proxy
    # settings also apply to the renderer. Short timeouts prevent a frozen-looking UI.
    response = _get_cover_session().get(
        _saltmeta_cover_url(canonical_id),
        headers={"User-Agent": "AstroDX-Rating-Prober/1.0"},
        timeout=(4, 8),
    )
    response.raise_for_status()
    with Image.open(BytesIO(response.content)) as downloaded:
        image = downloaded.convert("RGBA")
        image.load()
    return image


def music_picture(music_id: Union[int, str]) -> Image.Image:
    """Fetch a cover from SaltMeta and cache it outside the project.

    No local cover files are read. A failed request raises a descriptive error
    instead of silently showing a potentially incorrect jacket.
    """
    candidates = _cover_id_candidates(music_id)
    if not candidates:
        raise RuntimeError(f"无效的歌曲 ID，无法获取 SaltMeta 曲绘：{music_id}")
    try:
        _COVER_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(f"无法创建 SaltMeta 曲绘缓存目录：{_COVER_CACHE_DIR}") from exc

    errors = []
    for canonical_id in candidates:
        cache_path = _COVER_CACHE_DIR / f"{canonical_id}.png"
        cached = _load_cached_cover(cache_path)
        if cached is not None:
            return cached
        try:
            image = _download_cover(canonical_id)
            image.save(cache_path, format="PNG")
            return image
        except (requests.RequestException, TimeoutError, OSError, ValueError) as exc:
            errors.append(f"{canonical_id}: {exc}")

    details = "; ".join(errors[-3:])
    extra = f" 详情：{details}" if details else ""
    raise RuntimeError(
        f"SaltMeta 曲绘获取失败：歌曲 ID {music_id}（尝试的规范 ID：{candidates}）。"
        f"请检查网络连接，或确认该曲绘是否已收录。{extra}"
    )


# pylint: disable-next=too-few-public-methods
class DrawText:
    """Text drawing class"""
    def __init__(self, image: ImageDraw.ImageDraw, font: Path) -> None:
        self._img = image
        self._font = str(font)

    #pylint: disable-next=too-many-arguments, too-many-positional-arguments
    def draw(
        self,
        pos_x: int,
        pos_y: int,
        size: int,
        text: Union[str, int, float],
        color: Tuple[int, int, int, int] = (255, 255, 255, 255),
        anchor: str = 'lt',
        stroke_width: int = 0,
        stroke_fill: Tuple[int, int, int, int] = (0, 0, 0, 0)
    ):
        """Main drawing function"""
        font = ImageFont.truetype(self._font, size)
        self._img.text( # type: ignore
            (pos_x, pos_y), str(text), color, font, anchor,
            stroke_width=stroke_width, stroke_fill=stroke_fill
        )


# pylint: disable-next=too-few-public-methods
class ScoreBaseImage:
    """Score base class"""
    _diff = [
        Image.open(maimaidir / 'b50_score_basic.png'),
        Image.open(maimaidir / 'b50_score_advanced.png'),
        Image.open(maimaidir / 'b50_score_expert.png'),
        Image.open(maimaidir / 'b50_score_master.png'),
        Image.open(maimaidir / 'b50_score_remaster.png')
    ]
    text_color = (124, 129, 255, 255)
    t_color = [
        (255, 255, 255, 255), (255, 255, 255, 255),
        (255, 255, 255, 255), (255, 255, 255, 255),
        (138, 0, 226, 255)
    ]
    id_color = [
        (129, 217, 85, 255), (245, 189, 21, 255),
        (255, 129, 141, 255), (159, 81, 220, 255),
        (138, 0, 226, 255)
    ]

    def __init__(self, image: Image.Image) -> None:
        self._im = image
        dr = ImageDraw.Draw(self._im)
        self._ha = DrawText(dr, HAN)
        self._to = DrawText(dr, TORUS)

    # pylint: disable-next=too-many-locals
    def whiledraw(
        self,
        data: List[ChartInfo],
        best: bool,
        music_list: MusicList,
        height: int = 0,
    ) -> None:
        """Main drawing function"""
        dy = 114
        x = 0
        y = (235 if best else 1085) if data else height
        for num, info in enumerate(data):
            if num % 5 == 0:
                x = 16
                y += dy if num != 0 else 0
            else:
                x += 276

            cover = music_picture(info.song_id).resize((75, 75))
            version = Image.open(maimaidir / f'{info.type.upper()}.png').resize((37, 14))
            if info.rate.islower():
                rate = Image.open(
                    maimaidir / f'UI_TTR_Rank_{score_rank_l[info.rate]}.png'
                ).resize((63, 28))
            else:
                rate = Image.open(maimaidir / f'UI_TTR_Rank_{info.rate}.png').resize((63, 28))

            self._im.alpha_composite(self._diff[info.level_index], (x, y))
            self._im.alpha_composite(cover, (x + 12, y + 12))
            self._im.alpha_composite(version, (x + 51, y + 91))
            self._im.alpha_composite(rate, (x + 92, y + 78))
            if info.fc:
                fc = Image.open(
                    maimaidir / f'UI_MSS_MBase_Icon_{fcl[info.fc]}.png'
                ).resize((34, 34))
                self._im.alpha_composite(fc, (x + 154, y + 77))
            if info.fs:
                fs = Image.open(
                    maimaidir / f'UI_MSS_MBase_Icon_{fsl[info.fs]}.png'
                ).resize((34, 34))
                self._im.alpha_composite(fs, (x + 185, y + 77))

            dxscore = sum(music_list.by_id(str(info.song_id)).charts[info.level_index].notes) * 3
            dxnum = dx_score(info.dxScore / dxscore * 100)
            if dxnum:
                self._im.alpha_composite(
                    Image.open(maimaidir / f'UI_GAM_Gauge_DXScoreIcon_0{dxnum}.png').resize((47, 26)),
                    (x + 217, y + 80)
                )

            # Display ID differs from the canonical ID for DX charts: show +10000.
            display_song_id = int(info.song_id)
            if str(info.type).upper() == "DX" and 0 < display_song_id < 10000:
                display_song_id += 10000
            self._to.draw(
                x + 26, y + 98, 13, display_song_id,
                self.id_color[info.level_index], anchor='mm'
            )
            title = info.title
            if coloum_width(title) > 18:
                title = change_column_width(title, 17) + '...'
            self._ha.draw(
                x + 93, y + 14, 14, title,
                self.t_color[info.level_index], anchor='lm'
            )
            self._to.draw(
                x + 93, y + 38, 30, f'{info.achievements:.4f}%',
                self.t_color[info.level_index], anchor='lm'
            )
            self._to.draw(
                x + 219, y + 65, 15, f'{info.dxScore}/{dxscore}',
                self.t_color[info.level_index], anchor='mm'
            )
            self._to.draw(
                x + 93, y + 65, 15, f'{info.ds} -> {info.ra}',
                self.t_color[info.level_index], anchor='lm'
            )


class DrawBest(ScoreBaseImage):
    """B50 drawing class"""
    def __init__(self, user_info: UserInfo) -> None:
        super().__init__(Image.open(maimaidir / 'b50_bg.png').convert('RGBA'))
        self.user_name = user_info.nickname
        self.plate = user_info.plate
        self.add_rating = user_info.additional_rating
        self.rating = user_info.rating
        self.sd_best = user_info.charts.sd
        self.dx_best = user_info.charts.dx

    def _find_rating_picture(self) -> str:
        if self.rating < 1000:
            num = '01'
        elif self.rating < 2000:
            num = '02'
        elif self.rating < 4000:
            num = '03'
        elif self.rating < 7000:
            num = '04'
        elif self.rating < 10000:
            num = '05'
        elif self.rating < 12000:
            num = '06'
        elif self.rating < 13000:
            num = '07'
        elif self.rating < 14000:
            num = '08'
        elif self.rating < 14500:
            num = '09'
        elif self.rating < 15000:
            num = '10'
        else:
            num = '11'
        return f'UI_CMN_DXRating_{num}.png'

    def _find_match_level_picture(self) -> str:
        if self.add_rating <= 10:
            num = f'{self.add_rating:02d}'
        else:
            num = f'{self.add_rating + 1:02d}'
        return f'UI_DNM_DaniPlate_{num}.png'

    # pylint: disable-next=too-many-locals, too-many-branches, too-many-statements
    async def draw(self, music_list_data: MusicList, config: dict[str, Config]) -> Image.Image:
        """Draw B50 async"""
        plate_name = config['plate']
        icon_name = config['icon']
        override = config['plate_override']

        logo = Image.open(maimaidir / 'logo.png').resize((249, 120))
        dx_rating = Image.open(maimaidir / self._find_rating_picture()).resize((186, 35))
        name = Image.open(maimaidir / 'Name.png')
        match_level_file = config.get('match_level_file') or self._find_match_level_picture()
        match_level = Image.open(maimaidir / match_level_file).convert('RGBA').resize((80, 32))
        class_level_file = config.get('class_level_file') or 'UI_FBR_Class_00.png'
        class_level = Image.open(maimaidir / class_level_file).convert('RGBA').resize((90, 54))
        rating = Image.open(maimaidir / 'UI_CMN_Shougou_Rainbow.png').resize((270, 27))

        self._im.alpha_composite(logo, (14, 60))

        if isinstance(plate_name, str) and Path(plate_name).is_file():
            plate = Image.open(plate_name).convert('RGBA')
        elif isinstance(plate_name, int):
            try:
                plate = Image.open(platedir / f'UI_Plate_{plate_name:06d}.png')
            except FileNotFoundError:
                print(f"[WARNING]无法找到编号为{plate_name}的内置姓名框，将用默认姓名框代替。")
                plate = Image.open(platedir / 'UI_Plate_000001.png')
        elif isinstance(plate_name, str):
            try:
                plate = Image.open(platedir / plate_name).convert("RGBA")
            except FileNotFoundError:
                try:
                    plate = Image.open(root / plate_name).convert("RGBA")
                except FileNotFoundError:
                    print(f"[WARNING]无法找到姓名框{plate_name}，将用默认姓名框代替。")
                    plate = Image.open(platedir / 'UI_Plate_300501.png')
                else:
                    print("[WARNING]姓名框的加载位置已经更改。请参阅README。")
            else:
                if (abs(130 * plate.size[0] - 800 * plate.size[1]) >
                    min(13 * plate.size[0], 80 * plate.size[1])):
                    print("[WARNING]姓名框成功加载，但与目标形状偏离过大，显示效果可能与预期不符。")
        elif plate_name is None:
            plate = Image.open(icondir / 'UI_Icon_000001.png')
        if self.plate and not override:
            plate = Image.open(platedir / f'UI_Plate_{plate_finder(self.plate)}.png')
            if plate_name is not None:
                print("[INFO]服务器上的牌子设置已覆盖姓名框设置。")
        plate = plate.resize((800, 130))
        self._im.alpha_composite(plate, (300, 60))

        if isinstance(icon_name, str) and Path(icon_name).is_file():
            icon = Image.open(icon_name).convert('RGBA')
        elif isinstance(icon_name, int):
            try:
                icon = Image.open(icondir / f'UI_Icon_{icon_name:06d}.png')
            except FileNotFoundError:
                print(f"[WARNING]无法找到编号为{icon_name}的内置头像，将用默认头像代替。")
                icon = Image.open(icondir / 'UI_Icon_000001.png')
        elif isinstance(icon_name, str):
            try:
                icon = Image.open(customdir / f'{icon_name}.png').convert("RGBA")
            except FileNotFoundError:
                try:
                    icon = Image.open(root / icon_name).convert("RGBA")
                except FileNotFoundError:
                    print(f"[WARNING]无法找到头像{icon_name}，将用默认头像代替。")
                    icon = Image.open(icondir / 'UI_Icon_000001.png')
                else:
                    print("[WARNING]头像的加载位置已经更改。请参阅README。")
            else:
                if 10 * abs(icon.size[0] - icon.size[1]) > min(icon.size[0], icon.size[1]):
                    print("[WARNING]头像成功加载，但与目标形状偏离过大，显示效果可能与预期不符。")
        elif icon_name is None:
            icon = Image.open(icondir / 'UI_Icon_000001.png')
        icon = icon.resize((120, 120))
        self._im.alpha_composite(icon, (305, 65))
        self._im.alpha_composite(dx_rating, (435, 72))
        rating_value = f'{self.rating:05d}'
        for n, i in enumerate(rating_value):
            self._im.alpha_composite(
                Image.open(maimaidir / f'UI_NUM_Drating_{i}.png').resize((17, 20)),
                (520 + 15 * n, 80)
            )
        self._im.alpha_composite(name, (435, 115))
        self._im.alpha_composite(match_level, (625, 120))
        self._im.alpha_composite(class_level, (620, 60))
        self._im.alpha_composite(rating, (435, 160))

        self._ha.draw(445, 135, 25, self.user_name, (0, 0, 0, 255), 'lm')
        sdrating, dxrating = sum((_.ra for _ in self.sd_best)), sum((_.ra for _ in self.dx_best))
        rating_summary = config.get('rating_summary') or f'B35: {sdrating} + B15: {dxrating} = {self.rating}'
        self._to.draw(
            570, 172, 17,
            rating_summary,
            (0, 0, 0, 255), 'mm', 3, (255, 255, 255, 255)
        )
        self._ha.draw(
            700, 1550, 22,
            'Designed by Yuri-YuzuChaN & BlueDeer233.',
            self.text_color, 'mm', 4, (255, 255, 255, 255)
        )
        self._ha.draw(
            700, 1590, 22,
            "Generated by DM's ADX Prober",
            self.text_color, 'mm', 4, (255, 255, 255, 255)
        )

        self.whiledraw(self.sd_best, True, music_list_data)
        self.whiledraw(self.dx_best, False, music_list_data)

        return self._im
