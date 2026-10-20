from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
import html
import hashlib
import json
import re
import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw
from src.cache_parser import parse_cache, CacheParseError
from src.catalog import load_catalog_bytes, match_records, normalize_fetched_catalog, apply_manual_matches, score_signature
from src.catalog_sources import fetch_waterfish, fetch_lxns, fetch_saltmeta, CatalogFetchError
from src.catalog_cache import load_catalog, save_catalog
from src.rating import select_b50, dx_star_count, DX_STAR_COLORS, achievement_rank, achievement_rank_color, rating_tier, rating_tier_for_slots, is_utage_record
from src.upstream_b50_adapter import generate_upstream_b50_png, validate_static_dir
from src.maimai_assets import get_lxns_asset_catalog, ensure_lxns_asset_image, local_level_options
from src.network import SYSTEM_PROXY, DIRECT, CUSTOM_PROXY

st.set_page_config(page_title="AstroDX B50", page_icon="🎵", layout="wide")
st.markdown("""
<style>
:root { --ink:#382f58; --muted:#827a9b; --violet:#9c63e8; --pink:#ed72b7; --blue:#69a9f2; --mint:#83d9d0; }
.stApp { background:linear-gradient(180deg,#e7faff 0%,#f1e8ff 32%,#ffeaf4 70%,#fffaf5 100%); color:var(--ink); }
.block-container { padding-top:.8rem; padding-bottom:3rem; max-width:1700px; }
[data-testid="stVerticalBlock"] { gap:1.15rem!important; }
[data-testid="stHorizontalBlock"] { gap:1rem!important; }
.section-gap { height:16px; }
.setup-top-gap { height:24px; }
.section-separator { height:1px; margin:28px 0 30px; background:linear-gradient(90deg,transparent,#d9cde9,transparent); }
/* Three setup steps share the same panel geometry; their controls no longer float at unrelated heights. */
.st-key-step-cache, .st-key-step-catalog, .st-key-step-rating {
  box-sizing:border-box; min-height:252px; padding:15px 15px 14px;
  border:1px solid rgba(255,255,255,.96); border-radius:18px;
  background:rgba(255,255,255,.58); box-shadow:0 5px 18px #8d7cc512;
}
.st-key-step-cache [data-testid="stFileUploader"] label,
.st-key-step-catalog [data-testid="stSelectbox"] label,
.st-key-step-rating [data-testid="stSelectbox"] label { margin-bottom:10px!important; }
.step-hint { margin-top:13px; min-height:38px; color:#887d9f; font-size:.82rem; line-height:1.55; }
.catalog-count { margin-top:13px; padding:9px 14px 10px; min-height:66px; border:1px solid #ffffffd9; border-radius:14px; background:#ffffff88; box-shadow:0 4px 12px #8d7cc512; }
.catalog-count-label { color:#827795; font-size:.83rem; font-weight:750; margin-bottom:1px; }
.catalog-count-value { color:#41345f; font-size:1.75rem; line-height:1.15; font-weight:850; letter-spacing:-.025em; }
.catalog-count-empty .catalog-count-value { font-size:.95rem; font-weight:650; letter-spacing:0; color:#9b91ad; padding-top:8px; }
.cache-help-box { box-sizing:border-box; min-height:198px; padding:20px 24px; border:1px solid #fff; border-radius:18px; background:rgba(255,255,255,.54); box-shadow:0 5px 18px #8d7cc512; color:#62577f; }
.cache-help-title { font-size:1.03rem; font-weight:900; color:#4b3c68; margin-bottom:12px; }
.cache-help-grid { display:grid; grid-template-columns:1fr 1fr; gap:24px; }
.cache-help-platform { font-weight:900; color:#8561bf; margin-bottom:5px; }
.cache-help-platform p { color:#7e7397; font-weight:500; font-size:.9rem; line-height:1.7; margin:0; overflow-wrap:anywhere; }
.cache-help-foot { border-top:1px solid #ded4ee; margin-top:13px; padding-top:10px; font-size:.78rem; color:#9489a8; }
.renderer-note { margin-top:8px;padding:10px 12px;border-radius:10px;background:#f8f4ff;color:#83779a;font-size:.82rem;line-height:1.65; }
@media(max-width:800px){.cache-help-grid{grid-template-columns:1fr;gap:12px}.cache-help-box{padding:16px;}}
header[data-testid="stHeader"] { background:transparent; }
.top-brand { display:flex; align-items:center; gap:16px; min-height:86px; padding:10px 20px; border:1px solid rgba(255,255,255,.95); border-radius:20px; background:linear-gradient(105deg,rgba(255,255,255,.92),rgba(220,248,255,.86),rgba(255,226,244,.88)); box-shadow:0 8px 28px #9b8cc51f; margin-bottom:0; position:relative; overflow:hidden; }
.brand-logo { width:66px;height:66px;object-fit:contain;flex:0 0 66px;border-radius:20px;overflow:hidden;background:#f6f0ff;box-shadow:0 3px 10px #5369b522; }
.brand-title { color:#41345f;font-size:1.55rem;font-weight:950;letter-spacing:.08em;line-height:1.15; }
.brand-sub { display:none; }
div[data-testid="stPopover"] > button { min-height:70px; border-radius:16px; border:1px solid #ffffff; background:rgba(255,255,255,.78); color:#51466f; font-weight:800; box-shadow:0 5px 16px #8d7cc51a; }
div[data-testid="stPopover"] > button:hover { border-color:#cbb7ed; color:#493767; }
[data-testid="stPopoverBody"] { border-radius:16px!important; }
[data-testid="stFileUploader"], [data-testid="stSelectbox"] > div > div { border-radius:12px!important; }
[data-testid="stFileUploader"] { border:1px dashed #c5b5e7; padding:8px; background:#ffffff8a; }
[data-testid="stSelectbox"] label, [data-testid="stFileUploader"] label { color:#62577f!important;font-weight:750!important; }
.stButton > button, .stDownloadButton > button { border:0; border-radius:11px; background:linear-gradient(100deg,#8e6bea,#e779c0); color:white; font-weight:800; box-shadow:0 4px 12px #aa8ae633; }
.stButton > button:hover, .stDownloadButton > button:hover { color:white; border:0; filter:brightness(1.04); }
.metric-card { background:linear-gradient(135deg,#ffffffed,#f5f0ffed);border:1px solid #fff;padding:14px 17px;min-height:100px;border-radius:16px;box-shadow:0 5px 18px #8d7cc51c;margin-bottom:14px; }
.metric-label { color:#9a8db7;font-size:.7rem;letter-spacing:.1em;text-transform:uppercase;font-weight:850; }
.metric-value { font-size:1.7rem;font-weight:950;line-height:1.35;color:#493767; }
.metric-card.rating-rainbow { border:2px solid transparent; background:linear-gradient(#ffffffed,#f5f0ffed) padding-box,linear-gradient(105deg,#ff5778,#ffbd57,#62d7a5,#5f9fff,#be6bed,#ff77c7) border-box; }
.rating-rainbow .metric-value { background:linear-gradient(90deg,#ed4f69,#dc8b33,#25a87d,#3c83e4,#a04cd2);-webkit-background-clip:text;background-clip:text;color:transparent; }
.metric-card.rating-platinum { border:2px solid #c9d3e4;background:linear-gradient(135deg,#fff,#edf1f8); }
.rating-platinum .metric-value { color:#8292ab; }
.metric-card.rating-gold { border:2px solid #dbb34b;background:linear-gradient(135deg,#fffdf3,#fff2c9); }
.rating-gold .metric-value { color:#b58a13; }
.metric-card.rating-silver { border:2px solid #aeb8c5;background:linear-gradient(135deg,#fff,#edf0f4); }
.rating-silver .metric-value { color:#7d899a; }
.metric-card.rating-bronze { border:2px solid #c58e66;background:linear-gradient(135deg,#fffaf5,#f9e5d4); }
.rating-bronze .metric-value { color:#a96a40; }
.metric-card.rating-purple { border-color:#a996cf; } .rating-purple .metric-value { color:#8961c5; }
.metric-card.rating-red { border-color:#e59caa; } .rating-red .metric-value { color:#ce5268; }
.metric-card.rating-yellow { border-color:#e0cc72; } .rating-yellow .metric-value { color:#a98b16; }
.metric-card.rating-green { border-color:#91c9a0; } .rating-green .metric-value { color:#378d57; }
.metric-card.rating-blue { border-color:#91b9e5; } .rating-blue .metric-value { color:#477fbf; }
.metric-card.rating-white { border-color:#e0dce9; } .rating-white .metric-value { color:#706d7c; }
.small-note, [data-testid="stCaptionContainer"] { display:none!important; }
.section-banner { display:flex;align-items:center;gap:12px;padding:11px 15px;margin:30px 0 18px;border-radius:12px;color:white;font-weight:950;font-size:1.2rem;letter-spacing:.04em;box-shadow:0 5px 14px #9a80c426; }
.section-banner.blue {background:linear-gradient(90deg,#5799ed,#91c9ff);}
.section-banner.pink {background:linear-gradient(90deg,#e965a7,#f3a3d0);}
.section-banner.purple {background:linear-gradient(90deg,#9270e9,#c2a1ff);}
.section-banner .num {font-size:1.55rem;opacity:.85;}
.song-card { display:flex; flex-direction:column; gap:7px; height:100%; min-height:218px; background:linear-gradient(155deg,#fff,#fbf6ff);border:1px solid #fff;padding:8px;border-radius:13px;margin-bottom:16px;box-shadow:0 4px 12px #8d79b51c; position:relative; overflow:hidden; }
.song-cover { width:100%;height:auto;aspect-ratio:1/1;object-fit:cover;background:#e9e3f6;border-radius:8px; }
.song-cover-placeholder { width:100%;aspect-ratio:1/1;background:linear-gradient(135deg,#d9f5f6,#f4dafa);color:#8c75b5;display:flex;align-items:center;justify-content:center;font-size:2rem;font-weight:900;border-radius:8px; }
.song-title-row { display:flex;align-items:flex-start;justify-content:space-between;gap:5px;min-height:2.1em; }
.song-title { flex:1;min-width:0;color:#4b3c68;font-size:.79rem;font-weight:850;line-height:1.25;min-height:2.1em;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden; }
.song-rank { flex:0 0 auto;display:inline-flex;align-items:center;justify-content:center;padding:0;font-size:1.6rem;font-weight:1000;line-height:1;letter-spacing:-.04em;white-space:nowrap;margin-top:-.12rem;border:0;background:transparent; }
.song-rank.rank-rainbow { background:linear-gradient(100deg,#f04467 0%,#e69b33 23%,#38ac77 45%,#428fe5 68%,#a753d6 86%,#f0449b 100%);-webkit-background-clip:text;background-clip:text;color:transparent; }
.song-rank.rank-gold { color:#ad8410; }
.song-rank.rank-red { color:#d94b5b; }
.song-rank.rank-blue { color:#347dca; }
.song-rank.rank-green { color:#249755; }
.song-rank.rank-gray { color:#83808c; }
.song-meta { color:#9286a8;font-size:.68rem;line-height:1.55; }
.dx-score-row { display:flex;align-items:center;justify-content:space-between;gap:4px;white-space:nowrap; }
.dx-stars { font-size:.86rem;font-weight:950;letter-spacing:.015em;white-space:nowrap;text-shadow:0 0 5px #ffffffb3; }
.song-achievement { font-size:1rem;font-weight:950;line-height:1.2;letter-spacing:.005em;margin:0 0 1px;white-space:nowrap; }
.song-achievement.achievement-blue { color:#347dca; }
.song-achievement.achievement-red { color:#d94b5b; }
.song-achievement.achievement-gold { color:#ad8410; }
.song-card-content { flex:1;display:flex;flex-direction:column;min-width:0; }
.song-rating { display:flex;align-items:center;justify-content:space-between;gap:5px;color:#9b56d7;font-size:1rem;font-weight:950;margin-top:auto;border-top:1px solid #eee5fb;padding-top:5px; }
.song-clear-status { flex:0 0 auto;margin-left:auto;font-size:.78rem;font-weight:1000;line-height:1.1;letter-spacing:.015em;white-space:nowrap; }
.song-clear-status.clear-fc { color:#249755; }
.song-clear-status.clear-ap { color:#e27b19; }
.tag { display:inline-block;padding:2px 5px;margin-right:3px;font-size:.61rem;background:#f0e9ff;color:#8663c1;border-radius:5px;font-weight:800; }
hr { border-color:#ffffffb5; }
[data-testid="stDataFrame"] { background:#fff9; border-radius:12px; }
</style>
""", unsafe_allow_html=True)

header_brand, header_network = st.columns([8.5, 1.5], gap="medium")
with header_brand:
    st.markdown("<div class='top-brand'><img class='brand-logo' src='https://images.igdb.com/igdb/image/upload/t_720p/co9ege.jpg' alt='AstroDX logo'/><div><div class='brand-title'>ASTRODX <span style='color:#a66be2'>B50</span></div><div class='brand-sub'>RHYTHM GAME SCORE ANALYZER · MAIMAI DX RATING</div></div></div>", unsafe_allow_html=True)
with header_network:
    with st.popover("⚙ 网络设置", help="管理曲库刷新与曲绘下载的连接方式。", use_container_width=True):
        network_mode_label = st.selectbox(
            "网络连接方式",
            ["跟随系统代理", "直连（忽略代理）", "自定义 HTTP(S) 代理"],
            index=0,
            help="跟随系统代理会使用 Python 当前可见的代理环境变量；直连会忽略环境代理。",
            key="astro_network_mode",
        )
        if network_mode_label == "自定义 HTTP(S) 代理":
            proxy_url = st.text_input("HTTP(S) 代理地址", placeholder="http://127.0.0.1:7890", key="astro_custom_proxy")
        else:
            proxy_url = None
network_mode = {"跟随系统代理": SYSTEM_PROXY, "直连（忽略代理）": DIRECT, "自定义 HTTP(S) 代理": CUSTOM_PROXY}[network_mode_label]

st.markdown("<div class='setup-top-gap'></div>", unsafe_allow_html=True)

# Main controls — consistent, equal-height step panels.
nav1, nav2, nav3 = st.columns([1.2, 1.5, 1.5], gap="large")
with nav1:
    with st.container(key="step-cache"):
        cache_file = st.file_uploader("① AstroDX cache", type=None, help="选择 AstroDX 程序文件夹中的 cache 文件")
        st.markdown("<div class='step-hint'>导入本地存档，读取已游玩成绩；不会上传 cache 内容。</div>", unsafe_allow_html=True)
with nav2:
    with st.container(key="step-catalog"):
        source = st.selectbox("② 曲库数据源", ["SaltMeta · 日本 JP", "SaltMeta · 国际服 INTL", "SaltMeta · 国服 CN", "水鱼（在线）", "落雪（在线）", "上传 CSV / JSON"], index=0, help="在线曲库同步后会保存到本机缓存；上传文件模式不会发出曲库请求。")
        st.markdown("<div class='step-hint'>选择与成绩存档匹配的曲库地区；同步后会缓存谱面元数据。</div>", unsafe_allow_html=True)
with nav3:
    with st.container(key="step-rating"):
        mode_label = st.selectbox(
            "③ Rating 规则",
            ["直接取 Best 50（不区分版本）", "标准 B35 + B15", "仿真 B35 + B15"],
            index=0,
            help=(
                "标准模式：B35 从所有非目标版本中选取，B15 取指定版本；"
                "仿真模式：B35 只从目标版本之前的版本中选取，B15 只取目标版本，"
                "目标版本之后的成绩完全排除。"
            ),
        )
        st.markdown("<div class='step-hint'>标准模式按指定版本拆分；仿真模式进一步排除目标版本及其之后版本对 B35 的影响。</div>", unsafe_allow_html=True)
mode = "simulation" if mode_label.startswith("仿真") else ("split" if mode_label.startswith("标准") else "direct")

refresh_col, catalog_upload_col = st.columns([1.15, 4.5], gap="large")
with refresh_col:
    if st.button("⟳ 获取 / 刷新曲库", use_container_width=True, disabled=source == "上传 CSV / JSON"):
        try:
            with st.spinner("正在同步曲目与谱面元数据…"):
                if source.startswith("SaltMeta"):
                    region = {"SaltMeta · 日本 JP": "jp", "SaltMeta · 国际服 INTL": "intl", "SaltMeta · 国服 CN": "cn"}[source]
                    fetched = fetch_saltmeta(region, network_mode=network_mode, proxy_url=proxy_url)
                elif source.startswith("水鱼"):
                    fetched = fetch_waterfish(network_mode=network_mode, proxy_url=proxy_url)
                else:
                    fetched = fetch_lxns(network_mode=network_mode, proxy_url=proxy_url)
                normalized = normalize_fetched_catalog(fetched)
                if not normalized:
                    raise CatalogFetchError("曲库数据为空，未写入缓存")
                st.session_state["catalog_rows"] = normalized
                st.session_state["catalog_source"] = source
                saved_path = save_catalog(source, normalized)
                st.session_state["catalog_cache_meta"] = {"saved_at": __import__("datetime").datetime.now().astimezone().isoformat(timespec="seconds"), "row_count": len(normalized), "path": str(saved_path)}
            st.success("已同步 {:,} 条谱面，并缓存到本地。".format(len(st.session_state["catalog_rows"])))
        except CatalogFetchError as exc:
            st.error(str(exc))
# Restore a previously downloaded catalogue automatically when switching sources or restarting.
if source != "上传 CSV / JSON" and st.session_state.get("catalog_source") != source:
    cached = load_catalog(source)
    if cached:
        cached_rows, cache_meta = cached
        st.session_state["catalog_rows"] = cached_rows
        st.session_state["catalog_source"] = source
        st.session_state["catalog_cache_meta"] = cache_meta

catalog_file = None
with catalog_upload_col:
    if source == "上传 CSV / JSON":
        catalog_file = st.file_uploader("选择曲库文件", type=["csv", "json"], key="catalog_upload")
    st.markdown("""
    <div class="cache-help-box">
      <div class="cache-help-title">如何找到 AstroDX 的 cache 文件</div>
      <div class="cache-help-grid">
        <div><div class="cache-help-platform">iOS</div><p>打开系统自带的「文件」App，进入 AstroDX 应用文件夹，选择其中名为 <code>cache</code> 的文件上传。</p></div>
        <div><div class="cache-help-platform">Android</div><p>在文件管理器中打开 <code>/storage/emulated/0/Android/data/com.Reflektone.AstroDX/files</code>，选择其中名为 <code>cache</code> 的文件上传。</p></div>
      </div>
      <div class="cache-help-foot">只需要上传单个 cache 文件，不需要整个文件夹。本应用会解析已游玩成绩；不会把成绩发送给第三方查分器或图片生成服务。若 iOS 版本的 cache 编码与当前解析器不同，导入时可能提示格式不受支持。</div>
    </div>
    """, unsafe_allow_html=True)

with refresh_col:
    if st.session_state.get("catalog_source") == source and st.session_state.get("catalog_rows"):
        st.markdown("<div class='catalog-count'><div class='catalog-count-label'>曲库谱面数</div><div class='catalog-count-value'>{:,}</div></div>".format(len(st.session_state["catalog_rows"])), unsafe_allow_html=True)
    else:
        st.markdown("<div class='catalog-count catalog-count-empty'><div class='catalog-count-label'>曲库谱面数</div><div class='catalog-count-value'>尚未加载</div></div>", unsafe_allow_html=True)
st.markdown("<div class='section-separator'></div>", unsafe_allow_html=True)

if not cache_file:
    st.markdown("### 开始使用 ✦")
    a, b, c = st.columns(3)
    with a:
        st.markdown("<div class='metric-card'><div class='metric-label'>STEP 01</div><div class='metric-value'>导入 cache</div></div>", unsafe_allow_html=True)
    with b:
        st.markdown("<div class='metric-card'><div class='metric-label'>STEP 02</div><div class='metric-value'>同步曲库</div></div>", unsafe_allow_html=True)
    with c:
        st.markdown("<div class='metric-card'><div class='metric-label'>STEP 03</div><div class='metric-value'>查看 B50</div></div>", unsafe_allow_html=True)
    st.stop()

try:
    cache_obj, score_rows = parse_cache(cache_file.getvalue())
except CacheParseError as e:
    st.error(str(e)); st.stop()
except Exception as e:
    st.error("读取存档失败：{}: {}".format(type(e).__name__, e)); st.stop()

played = [r for r in score_rows if r["achievement"] > 0]
if source == "上传 CSV / JSON":
    if not catalog_file:
        st.warning("请上传曲库文件。"); st.stop()
    try:
        catalog = load_catalog_bytes(catalog_file.name, catalog_file.getvalue())
    except Exception as exc:
        st.error("读取曲库失败：{}: {}".format(type(exc).__name__, exc)); st.stop()
else:
    if st.session_state.get("catalog_source") != source or not st.session_state.get("catalog_rows"):
        st.warning("当前没有兼容的新版本曲库缓存（旧缓存缺少显示等级字段）。请点击上方「获取 / 刷新曲库」重新同步一次。"); st.stop()
    catalog = st.session_state["catalog_rows"]
if not catalog:
    st.error("没有读取到有效谱面数据。"); st.stop()

def _compact_version_label(value: object) -> str:
    """Compact a version label for tolerant matching across catalogue providers."""
    import unicodedata
    value = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[^\w]", "", value, flags=re.UNICODE)


def _version_rank(value: object, version_source: str) -> int | None:
    """Return chronological rank for a known JP/INTL or CN maimai DX version.

    CN labels use their own DX20xx progression and are never interleaved with
    Japanese/International names. Unknown labels return None so simulation mode
    can fail closed rather than accidentally pulling a future version into B35.
    """
    label = _compact_version_label(value)
    if not label:
        return None

    # These labels identify the CN catalogue even if the user uploaded its CSV
    # instead of selecting SaltMeta's explicit CN source.
    if label == "舞萌dx":
        return 0
    if label == "舞萌":
        return -1

    is_cn_catalogue = version_source == "SaltMeta · 国服 CN"
    # CN catalogue labels commonly use DX2021, DX2022, ...; accept these labels
    # from imported catalogues too, while keeping the region's sequence separate.
    year_match = re.search(r"(20\d{2})", label)
    if is_cn_catalogue or (year_match and ("dx" in label or "舞萌" in label)):
        if year_match:
            return int(year_match.group(1)) - 2020
        if "舞萌dx" in label or label in {"dx", "maimaidx", "deluxe"}:
            return 0
        if label in {"舞萌", "maimai"}:
            return -1
        return None

    # Old maimai generation, then the DX generation. The order is intentionally
    # explicit: sorting version names alphabetically would be incorrect.
    ordered_labels = [
        (0, ("maimai", "初代")),
        (1, ("maimaiplus",)),
        (2, ("green",)),
        (3, ("greenplus",)),
        (4, ("orange",)),
        (5, ("orangeplus",)),
        (6, ("pink",)),
        (7, ("pinkplus",)),
        (8, ("murasaki",)),
        (9, ("murasakiplus",)),
        (10, ("milk",)),
        (11, ("milkplus",)),
        (12, ("finale",)),
        (13, ("dx", "deluxe", "でらっくす")),
        (14, ("dxplus", "deluxeplus", "でらっくすplus")),
        (15, ("splash", "すぷらっしゅ")),
        (16, ("splashplus", "すぷらっしゅplus")),
        (17, ("universe",)),
        (18, ("universeplus",)),
        (19, ("festival",)),
        (20, ("festivalplus",)),
        (21, ("buddies",)),
        (22, ("buddiesplus",)),
        (23, ("prism",)),
        (24, ("prismplus",)),
        (25, ("circle",)),
        (26, ("circleplus",)),
        (27, ("magical",)),
    ]

    # Match newer named generations before generic DX / maimai aliases.
    # This also handles provider labels such as "maimai DX FESTiVAL PLUS".
    for rank, aliases in reversed(ordered_labels[15:]):
        if any(alias in label for alias in aliases):
            return rank
    if "dxplus" in label or "deluxeplus" in label or "でらっくすplus" in label:
        return 14
    if "splash" in label or "すぷらっしゅ" in label:
        return 16 if "plus" in label else 15
    if "dx" in label or "deluxe" in label or "でらっくす" in label:
        return 14 if "plus" in label else 13

    for rank, aliases in reversed(ordered_labels[:13]):
        if any(alias in label for alias in aliases):
            # Avoid treating a plain "maimai DX" label as the original generation.
            if rank == 0 and any(token in label for token in ("dx", "deluxe", "でらっくす")):
                return 13
            if rank == 1 and "dx" in label:
                return 14
            return rank
    if label in {"舞萌", "舞萌dx"}:
        return 0 if label == "舞萌dx" else -1
    return None


def _sort_versions_chronologically(version_labels: list[str], version_source: str) -> list[str]:
    original_positions = {label: index for index, label in enumerate(version_labels)}
    def key(label: str):
        rank = _version_rank(label, version_source)
        if rank is None:
            return (1, label.casefold(), original_positions[label])
        return (0, rank, original_positions[label])
    return sorted(version_labels, key=key)


def _select_simulation_b35_b15(records: list[dict], target_version: str, version_source: str):
    """Select B35 only before target version, and B15 only from target version."""
    target_rank = _version_rank(target_version, version_source)
    if target_rank is None:
        return [], [], 0, "无法识别所选版本「{}」的发行顺序；为避免把较新版本错误计入 B35，仿真模式已停止计算。请使用支持版本标签的曲库。".format(target_version)

    eligible = [row for row in records if not is_utage_record(row)]
    older_pool, target_pool = [], []
    unknown_count = 0
    for row in eligible:
        rank = _version_rank(row.get("version", ""), version_source)
        if rank is None:
            unknown_count += 1
        elif rank < target_rank:
            older_pool.append(row)
        elif rank == target_rank:
            target_pool.append(row)
        # Versions after the selected target are deliberately ignored.

    sort_key = lambda row: (row.get("rating", 0), row.get("achievement", 0), row.get("dx_score", 0))
    return (
        sorted(older_pool, key=sort_key, reverse=True)[:35],
        sorted(target_pool, key=sort_key, reverse=True)[:15],
        unknown_count,
        None,
    )


versions = list(dict.fromkeys(str(r.get("version") or "未知版本").strip() for r in catalog if r.get("version")))
# Infer CN ordering for imported/alternate-source catalogues whose labels look like DX2021, DX2022, etc.
version_order_source = source
if source != "SaltMeta · 国服 CN" and any(
    re.search(r"20\d{2}", _compact_version_label(version))
    and ("dx" in _compact_version_label(version) or "舞萌" in _compact_version_label(version))
    for version in versions
):
    version_order_source = "SaltMeta · 国服 CN"
versions = _sort_versions_chronologically(versions, version_order_source)
if mode in ("split", "simulation"):
    recognized_versions = [version for version in versions if _version_rank(version, version_order_source) is not None]
    default_version = (recognized_versions[-1] if recognized_versions else (versions[-1] if versions else "未知版本"))
    version_help = (
        "仿真模式：B15 只取所选版本，B35 只允许取发行顺序早于所选版本的成绩；"
        "更晚版本不会进入 B35。国服 DX20xx 使用独立的国服顺序。"
        if mode == "simulation"
        else "标准模式：B15 取所选版本，B35 从所有非该版本的成绩中选取。"
    )
    target_version = st.selectbox(
        "B15 所属版本", versions,
        index=versions.index(default_version) if default_version in versions else 0,
        help=version_help,
    )
else:
    target_version = None

matched, unmatched = match_records(score_rows, catalog)
# Read manual choices from Streamlit state before calculating, so the ambiguity editor can
# appear lower on the page without delaying the recalculation after a selection.
manual_choices = {}
ambiguity_items = []
if True:
    _, ambiguity_items = match_records(score_rows, catalog)
    for item in ambiguity_items:
        candidates = item.get("candidates") or []
        if not candidates:
            continue
        labels = ["{} | {} | 等级 {} | {} | {} | {}".format(c.get("title", "?"), c.get("difficulty", "?"), c.get("level_text") or "未知", c.get("constant", "?"), c.get("song_type", "?"), c.get("version", "?")) for c in candidates]
        sig = score_signature(item)
        widget_key = "manual_match_v09_" + str(abs(hash(sig)))
        stored = st.session_state.get(widget_key, "暂不选择")
        if stored in labels:
            manual_choices[sig] = labels.index(stored)
matched, unmatched = match_records(score_rows, catalog)
if manual_choices:
    matched, unmatched = apply_manual_matches(matched, unmatched, manual_choices)
simulation_unknown_versions = 0
simulation_error = None
if mode == "split":
    old, new = select_b50(matched, mode="split", target_version=target_version)
    total_rating = sum(x["rating"] for x in old) + sum(x["rating"] for x in new)
elif mode == "simulation":
    old, new, simulation_unknown_versions, simulation_error = _select_simulation_b35_b15(
        matched, target_version, version_order_source
    )
    total_rating = sum(x["rating"] for x in old) + sum(x["rating"] for x in new)
else:
    top50, _ = select_b50(matched, mode="direct")
    old, new = top50, []
    total_rating = sum(x["rating"] for x in top50)

# Dashboard-style summary cards.
def _b50_preview_canvas(source: str | Path | None, width: int = 320, height: int = 160) -> Image.Image:
    """Render any B50 asset into a same-sized preview canvas without distortion."""
    canvas = Image.new("RGBA", (width, height), (250, 248, 255, 255))
    if source is not None:
        source_path = Path(source)
        if source_path.is_file():
            try:
                with Image.open(source_path) as opened:
                    image = opened.convert("RGBA")
                    image.thumbnail((width - 16, height - 16), Image.Resampling.LANCZOS)
                x = (width - image.width) // 2
                y = (height - image.height) // 2
                canvas.alpha_composite(image, (x, y))
                return canvas
            except (OSError, ValueError):
                pass

    draw = ImageDraw.Draw(canvas)
    draw.text((width // 2, height // 2), "预览不可用", fill=(135, 123, 159, 255), anchor="mm")
    return canvas


def metric_card(label, value, tier=None, tooltip=""):
    css_class = "metric-card" + (" rating-" + tier[0] if tier else "")
    title_attr = " title='{}'".format(html.escape(str(tooltip), quote=True)) if tooltip else ""
    st.markdown("<div class='{}'{}><div class='metric-label'>{}</div><div class='metric-value'>{}</div></div>".format(css_class, title_attr, html.escape(str(label)), html.escape(str(value))), unsafe_allow_html=True)

rating_matches = [r for r in matched if not is_utage_record(r)]
utage_matched = len(matched) - len(rating_matches)
# Keep UTAGE visible in the matching table but never include it in rating values / cards.
for row in matched:
    if is_utage_record(row):
        row["rating"] = 0

m1, m2, m3, m4 = st.columns(4, gap="large")
with m1: metric_card("ESTIMATED DX RATING", "{:,}".format(total_rating), rating_tier(total_rating), "按当前曲库和非 UTAGE 谱面计算。")
with m2: metric_card("MATCHED CHARTS", "{:,}".format(len(rating_matches)), tooltip="已匹配且可参与 Rating 的谱面；已排除 {} 张 UTAGE 宴会场谱面。".format(utage_matched))
with m3: metric_card("UNMATCHED", "{:,}".format(len(unmatched)), tooltip="未匹配或存在多个谱面候选的成绩，需在页面最底部核对。")
with m4:
    metric_card("CACHE / CHARTS", str(cache_obj.get("version", "?")), tooltip="{} 条有成绩 / {} 条谱面。".format(len(played), len(score_rows)))

if mode in ("split", "simulation"):
    if simulation_error:
        st.error(simulation_error)
    elif mode == "simulation":
        st.info(
            "仿真规则：B15 只计算「{}」；B35 只从它之前的版本选取。"
            "「{}」以及之后的版本不会进入 B35。".format(target_version, target_version)
        )
    r1, r2 = st.columns(2, gap="large")
    b35_rating = sum(x["rating"] for x in old)
    b15_rating = sum(x["rating"] for x in new)
    b35_label = "B35 · BEFORE TARGET" if mode == "simulation" else "B35 · OLD CHARTS"
    b35_help = (
        "只使用发行顺序早于 {} 的版本；之后版本以及版本标签无法识别的记录均不计入。".format(target_version)
        if mode == "simulation"
        else "标准模式下所有非目标版本均可参与 B35。"
    )
    with r1: metric_card(b35_label, "{:,}".format(b35_rating), rating_tier_for_slots(b35_rating, 35), "{} / 35 个槽位；{} 颜色门槛按 35/50 比例折算。".format(len(old), b35_help))
    with r2: metric_card("B15 · SELECTED VERSION", "{:,}".format(b15_rating), rating_tier_for_slots(b15_rating, 15), "{} / 15 个槽位 · {}；颜色门槛按 15/50 比例折算。".format(len(new), target_version))
    if mode == "simulation" and simulation_unknown_versions:
        st.warning("仿真模式已排除 {:,} 条版本标签无法识别的成绩，以避免误把未来版本计入 B35。".format(simulation_unknown_versions))
    if len(old) < 35 or len(new) < 15:
        st.warning("B35 / B15 槽位未填满。请检查成绩数量、版本选择或未匹配曲目。")
elif len(old) < 50:
    st.warning("当前只有这些匹配成绩，Best 50 尚未填满。")

# Card grid instead of table/list for the core Best 50 view.
def cover_url(record):
    cover_id = str(record.get("cover_id") or record.get("song_id") or "").strip()
    if not cover_id.isdigit():
        return ""
    return "https://meta.salt.realtvop.top/covers/{}.png".format(cover_id.zfill(6)[-6:])

def render_cards(title, records, key):
    banner_class = "blue" if "B35" in title or "BEST 50" in title else "pink"
    banner_num = "01" if banner_class == "blue" else "02"
    st.markdown("<div class='section-banner {}'><span class='num'>{}</span><span>{}</span><span style='margin-left:auto;font-size:.75rem;opacity:.9'>{} CHARTS</span></div>".format(banner_class, banner_num, html.escape(title), len(records)), unsafe_allow_html=True)
    if not records:
        st.info("暂无可展示的记录")
        return
    for start in range(0, len(records), 5):
        cols = st.columns(5, gap="small")
        for col, rec in zip(cols, records[start:start + 5]):
            with col:
                title_text = html.escape(str(rec.get("title", "未知曲目")))
                diff = html.escape(str(rec.get("difficulty", "")))
                version = html.escape(str(rec.get("version", "未知版本")))
                chart_type = html.escape(str(rec.get("song_type", "")))
                ach = float(rec.get("achievement", 0) or 0)
                rating = int(rec.get("rating", 0) or 0)
                cover = cover_url(rec)
                cover_html = "<img class='song-cover' src='{}' alt='cover'>".format(html.escape(cover, quote=True)) if cover else "<div class='song-cover-placeholder'>♪</div>"
                constant = html.escape(str(rec.get("constant", "—") or "—"))
                dx_score = int(rec.get("dx_score", 0) or 0)
                note_count = rec.get("notes") or rec.get("total_notes") or 0
                stars = dx_star_count(dx_score, note_count)
                if stars is None:
                    # Unknown chart note count: do not fabricate an empty-star rating.
                    star_markup = ""
                elif stars == 0:
                    # No achieved stars means no star glyphs at all, not hollow placeholders.
                    star_markup = "<span class='dx-stars' title='DX 星级：0 / 5'></span>"
                else:
                    # Community renderer palette matching the game's green→orange→gold star progression.
                    star_color = DX_STAR_COLORS[stars]
                    star_markup = "<span class='dx-stars' style='color:{}' title='DX 星级：{} / 5'>{}</span>".format(star_color, stars, "✦" * stars)
                dx_line = "<div class='dx-score-row'><span>DX Score: {}</span>{}</div>".format(dx_score, star_markup)
                rank_label = achievement_rank(ach)
                rank_color = achievement_rank_color(ach)
                rank_markup = "<span class='song-rank rank-{}'>{}</span>".format(rank_color, html.escape(rank_label))
                title_row = "<div class='song-title-row'><div class='song-title'>{}</div>{}</div>".format(title_text, rank_markup)

                # Achievement is deliberately prominent and sits above the chart tags.
                ach_color = "blue" if ach < 80.0 else ("red" if ach < 97.0 else "gold")
                achievement_markup = "<div class='song-achievement achievement-{}'>达成率　{:.4f}%</div>".format(ach_color, ach)

                # AstroDX cache clearType: 3=FC, 4=FC+, 5=AP, 6=AP+.
                try:
                    clear_type = int(rec.get("clear_type") or 0)
                except (TypeError, ValueError):
                    clear_type = 0
                clear_statuses = {
                    3: ("FC", "clear-fc"),
                    4: ("FC+", "clear-fc"),
                    5: ("AP", "clear-ap"),
                    6: ("AP+", "clear-ap"),
                }
                clear_status = clear_statuses.get(clear_type)
                clear_markup = (
                    "<span class='song-clear-status {}'>{}</span>".format(clear_status[1], clear_status[0])
                    if clear_status else ""
                )
                st.markdown(
                    "<div class='song-card'>{}<div class='song-card-content'>{}{}<div class='song-tags'>"
                    "<span class='tag'>{}</span><span class='tag'>{}</span><span class='tag'>{}</span>"
                    "</div><div class='song-meta'>版本：{}</div>{}<div class='song-rating'><span>RATING　{}</span>{}</div></div></div>".format(
                        cover_html, title_row, achievement_markup,
                        diff, chart_type or "MAIMAI DX", constant,
                        version, dx_line, rating, clear_markup,
                    ),
                    unsafe_allow_html=True,
                )
    df = pd.DataFrame(records)
    cols = [c for c in ["title", "difficulty", "constant", "achievement", "rating", "dx_score", "version", "song_type", "song_id"] if c in df.columns]
    st.download_button("导出 {} CSV".format(title), df[cols].to_csv(index=False).encode("utf-8-sig"), file_name=key + ".csv", mime="text/csv")

if mode in ("split", "simulation"):
    b35_card_title = ("B35 · BEFORE " + target_version) if mode == "simulation" else "B35 · OLD"
    render_cards(b35_card_title, old, "b35_simulation" if mode == "simulation" else "b35_old")
    render_cards("B15 · " + target_version, new, "b15_selected")
else:
    render_cards("BEST 50 · ALL VERSIONS", old, "best50")

# B50 poster: use the public Shio796 renderer, adapted to consume these local records.
all_selected = (old + new) if mode in ("split", "simulation") else old

# B50 主题映射：主题素材覆盖原版同名文件，缺失素材回退到原版。
B50_THEMES = {
    "原版": None,
    "CiRCLE PLUS": "circle_plus",
    "PRiSM PLUS": "prism_plus",
    "BUDDiES": "buddies",
}

# Streamlit 会在用户切换控件后更新 session_state，再重新执行脚本。
# 因此这里可以在生成签名之前读取当前主题。
selected_theme_label = st.session_state.get("b50_theme_label", "原版")
if selected_theme_label not in B50_THEMES:
    selected_theme_label = "原版"

theme_dir_name = B50_THEMES[selected_theme_label]
png_signature = hashlib.sha256(json.dumps({
    "scores": [{k: r.get(k) for k in ("title", "difficulty", "constant", "achievement", "rating", "dx_score", "clear_type", "version", "song_id", "cover_id", "song_type", "notes", "total_notes")} for r in all_selected],
    "rating": total_rating, "mode": mode_label, "source": source,
    "theme": theme_dir_name,
    "static_dir": str(Path(__file__).resolve().parent / "static"),
    "display_name": st.session_state.get("b50_display_name_input", "AstroDX Player"),
    "icon_id": st.session_state.get("b50_online_icon_id"),
    "plate_id": st.session_state.get("b50_online_plate_id"),
    "match_level_file": st.session_state.get("b50_match_level_file"),
    "class_level_file": st.session_state.get("b50_class_level_file"),
}, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()

st.markdown("<div class='section-separator'></div>", unsafe_allow_html=True)
st.markdown("<div class='section-banner purple'><span class='num'>03</span><span>B50 图片生成</span><span style='margin-left:auto;font-size:.75rem;opacity:.9'>OPEN-SOURCE RENDERER</span></div>", unsafe_allow_html=True)
with st.container(border=True):
    st.markdown("**使用开源 B50 模板**")
    st.markdown("使用公开 B50 模板绘图；将本页匹配好的本地成绩直接转换为绘图数据，不调用水鱼账号查分流程。")
    selected_theme_label = st.selectbox(
        "B50 主题",
        options=list(B50_THEMES.keys()),
        index=list(B50_THEMES.keys()).index(
            st.session_state.get("b50_theme_label", "原版")
            if st.session_state.get("b50_theme_label", "原版") in B50_THEMES
            else "原版"
        ),
        key="b50_theme_label",
        help="切换 B50 海报模板主题。主题文件夹中的同名素材优先于原版素材，缺失的素材自动回退到原版。",
    )
    static_path = str(Path(__file__).resolve().parent / "static")
    static_valid, static_result = validate_static_dir(static_path)

    st.markdown("**海报外观**")
    force_asset_refresh = st.button("⟳ 刷新在线头像 / 姓名框列表", key="refresh_lxns_asset_catalogs")
    icon_items = st.session_state.get("lxns_icon_catalog", [])
    plate_items = st.session_state.get("lxns_plate_catalog", [])
    icon_catalog_error = ""
    plate_catalog_error = ""
    if not icon_items or force_asset_refresh:
        try:
            with st.spinner("正在加载 LXNS 头像目录…"):
                icon_items = get_lxns_asset_catalog(
                    "icon", network_mode=network_mode, proxy_url=proxy_url, force_refresh=force_asset_refresh
                )
            st.session_state["lxns_icon_catalog"] = icon_items
        except Exception as exc:
            icon_catalog_error = str(exc)
            icon_items = st.session_state.get("lxns_icon_catalog", [])
    if not plate_items or force_asset_refresh:
        try:
            with st.spinner("正在加载 LXNS 姓名框目录…"):
                plate_items = get_lxns_asset_catalog(
                    "plate", network_mode=network_mode, proxy_url=proxy_url, force_refresh=force_asset_refresh
                )
            st.session_state["lxns_plate_catalog"] = plate_items
        except Exception as exc:
            plate_catalog_error = str(exc)
            plate_items = st.session_state.get("lxns_plate_catalog", [])

    icon_name_by_id = {int(item["id"]): str(item["name"]) for item in icon_items}
    plate_name_by_id = {int(item["id"]): str(item["name"]) for item in plate_items}

    # Pin friendly labels for the requested default assets when they exist in the
    # cached catalogue. Their IDs are the stable identifiers used for selection.
    preferred_icon_id = 458022
    preferred_plate_id = 559501
    if preferred_icon_id in icon_name_by_id:
        icon_name_by_id[preferred_icon_id] = "♡百合咲 ミカ♡"
    if preferred_plate_id in plate_name_by_id:
        plate_name_by_id[preferred_plate_id] = "Divide et impera!（ソルト）"

    icon_options = [None] + sorted(icon_name_by_id)
    plate_options = [None] + sorted(plate_name_by_id)
    # Preserve a previously selected ID when a refresh temporarily fails and the
    # on-disk catalogue cannot currently be read.
    previous_icon = st.session_state.get("b50_online_icon_id")
    if previous_icon is not None and previous_icon not in icon_options:
        icon_options.append(previous_icon)
        icon_name_by_id.setdefault(previous_icon, "已保存的头像")
    previous_plate = st.session_state.get("b50_online_plate_id")
    if previous_plate is not None and previous_plate not in plate_options:
        plate_options.append(previous_plate)
        plate_name_by_id.setdefault(previous_plate, "已保存的姓名框")

    # Set each preferred selection once a usable catalogue is available. If no
    # catalogue exists, None remains selected and the renderer uses local assets.
    # The per-kind flags ensure reruns do not overwrite a later manual selection.
    if icon_items and not st.session_state.get("_b50_icon_default_initialized", False):
        if st.session_state.get("b50_online_icon_id") is None:
            st.session_state["b50_online_icon_id"] = (
                preferred_icon_id if preferred_icon_id in icon_name_by_id else None
            )
        st.session_state["_b50_icon_default_initialized"] = True
    if plate_items and not st.session_state.get("_b50_plate_default_initialized", False):
        if st.session_state.get("b50_online_plate_id") is None:
            st.session_state["b50_online_plate_id"] = (
                preferred_plate_id if preferred_plate_id in plate_name_by_id else None
            )
        st.session_state["_b50_plate_default_initialized"] = True

    pic_dir = Path(static_result) / "mai" / "pic" if static_valid else None
    match_files = local_level_options(static_result, "UI_DNM_DaniPlate_") if static_valid else []
    class_files = local_level_options(static_result, "UI_FBR_Class_") if static_valid else []
    match_default = "UI_DNM_DaniPlate_01.png"
    class_default = "UI_FBR_Class_00.png"
    if match_default not in match_files and match_files:
        match_default = match_files[0]
    if class_default not in class_files and class_files:
        class_default = class_files[0]

    option_col1, option_col2 = st.columns(2)
    with option_col1:
        selected_icon_id = st.selectbox(
            "头像", icon_options,
            index=0, key="b50_online_icon_id",
            format_func=lambda value: "默认头像（本地资源）" if value is None else "{} · #{}".format(icon_name_by_id.get(value, "头像"), value),
            help="在线头像目录来自 LXNS；选中的图片会缓存在本机。",
        )
        selected_match_file = st.selectbox(
            "段位", match_files or [match_default],
            index=(match_files.index(match_default) if match_default in match_files else 0),
            key="b50_match_level_file",
            format_func=lambda value: "段位 {}　·　{}".format(Path(value).stem.rsplit("_", 1)[-1], value),
        )
    with option_col2:
        selected_plate_id = st.selectbox(
            "姓名框", plate_options,
            index=0, key="b50_online_plate_id",
            format_func=lambda value: "默认姓名框（本地资源）" if value is None else "{} · #{}".format(plate_name_by_id.get(value, "姓名框"), value),
            help="在线姓名框目录来自 LXNS；选中的图片会缓存在本机。",
        )
        selected_class_file = st.selectbox(
            "友人对战阶级", class_files or [class_default],
            index=(class_files.index(class_default) if class_default in class_files else 0),
            key="b50_class_level_file",
            format_func=lambda value: "阶级 {}　·　{}".format(Path(value).stem.rsplit("_", 1)[-1], value),
        )

    if icon_catalog_error:
        st.caption("在线头像目录暂不可用，仍可使用默认头像。详情：{}".format(icon_catalog_error))
    if plate_catalog_error:
        st.caption("在线姓名框目录暂不可用，仍可使用默认姓名框。详情：{}".format(plate_catalog_error))

    icon_asset_path = None
    plate_asset_path = None
    asset_selection_ready = True

    # Resolve the selected online assets for the renderer, while keeping
    # separate local paths for previews when the default assets are selected.
    icon_preview_path = None
    plate_preview_path = None
    if pic_dir is not None:
        default_icon = pic_dir.parent / "icon" / "UI_Icon_000001.png"
        default_plate = pic_dir.parent / "plate" / "UI_Plate_000001.png"
        if default_icon.is_file():
            icon_preview_path = default_icon
        if default_plate.is_file():
            plate_preview_path = default_plate

    try:
        if selected_icon_id is not None:
            icon_asset_path = ensure_lxns_asset_image(
                "icon", selected_icon_id, network_mode=network_mode, proxy_url=proxy_url
            )
            icon_preview_path = icon_asset_path
    except Exception as exc:
        asset_selection_ready = False
        st.warning("头像预览加载失败：{}".format(exc))

    try:
        if selected_plate_id is not None:
            plate_asset_path = ensure_lxns_asset_image(
                "plate", selected_plate_id, network_mode=network_mode, proxy_url=proxy_url
            )
            plate_preview_path = plate_asset_path
    except Exception as exc:
        asset_selection_ready = False
        st.warning("姓名框预览加载失败：{}".format(exc))

    match_preview_path = (Path(pic_dir) / selected_match_file) if pic_dir is not None else None
    class_preview_path = (Path(pic_dir) / selected_class_file) if pic_dir is not None else None

    # All four previews use the same 2:1 canvas and equal-width columns.
    # Order: icon, nameplate, rating plate, friend-match class.
    preview_specs = [
        ("头像", icon_preview_path, "当前头像：默认" if selected_icon_id is None else "当前头像：{}".format(icon_name_by_id.get(selected_icon_id, selected_icon_id))),
        ("姓名框", plate_preview_path, "当前姓名框：默认" if selected_plate_id is None else "当前姓名框：{}".format(plate_name_by_id.get(selected_plate_id, selected_plate_id))),
        ("段位", match_preview_path, "段位 {}".format(Path(selected_match_file).stem.rsplit("_", 1)[-1])),
        ("友人对战阶级", class_preview_path, "阶级 {}".format(Path(selected_class_file).stem.rsplit("_", 1)[-1])),
    ]
    preview_cols = st.columns(4, gap="small")
    for preview_col, (preview_title, preview_path, preview_detail) in zip(preview_cols, preview_specs):
        with preview_col:
            st.markdown(
                "<div style='text-align:center;font-weight:800;color:#594573;margin:0 0 6px'>{}</div>".format(html.escape(preview_title)),
                unsafe_allow_html=True,
            )
            st.image(_b50_preview_canvas(preview_path), use_container_width=True)
            st.markdown(
                "<div style='text-align:center;color:#827795;font-size:.76rem;line-height:1.35;overflow-wrap:anywhere;margin-top:4px'>{}</div>".format(html.escape(preview_detail)),
                unsafe_allow_html=True,
            )

    if st.button("生成 B50 图片", key="generate_upstream_b50_png", use_container_width=True, disabled=(not all_selected or not static_valid or not asset_selection_ready)):
        try:
            with st.spinner("正在按 B50 模板生成图片…"):
                rating_summary = (
                    "B35 (before {}): {} + B15: {} = {}".format(
                        target_version,
                        sum(x.get("rating", 0) for x in old),
                        sum(x.get("rating", 0) for x in new),
                        total_rating,
                    )
                    if mode == "simulation"
                    else (
                        "B35: {} + B15: {} = {}".format(
                            sum(x.get("rating", 0) for x in old),
                            sum(x.get("rating", 0) for x in new),
                            total_rating,
                        )
                        if mode == "split"
                        else "BEST 50 RATING: {}".format(total_rating)
                    )
                )
                png_bytes = generate_upstream_b50_png(
                    old, new, total_rating, display_name, static_result,
                    network_mode=network_mode, proxy_url=proxy_url,
                    rating_summary=rating_summary,
                    icon_asset_path=icon_asset_path,
                    plate_asset_path=plate_asset_path,
                    match_level_file=selected_match_file,
                    class_level_file=selected_class_file,
                    theme=theme_dir_name,
                )
            st.session_state["upstream_b50_png"] = {"signature": png_signature, "bytes": png_bytes}
            st.success("已使用开源 B50 绘图代码生成图片。成绩没有上传到第三方查分器或绘图服务。")
        except Exception as exc:
            st.error("开源模板生成失败：{}".format(exc))
    result = st.session_state.get("upstream_b50_png")
    if result and result.get("signature") == png_signature:
        st.image(result["bytes"], caption="Shio796 开源 B50 模板 · 本地成绩适配", use_container_width=True)
        st.download_button(
            "下载 B50 PNG", data=result["bytes"], file_name="astrodx-b50.png", mime="image/png",
            key="download_upstream_b50_png", use_container_width=True,
        )

with st.expander("所有已匹配成绩（表格）", expanded=False):
    if matched:
        df = pd.DataFrame(matched)
        cols = [c for c in ["title", "difficulty", "constant", "achievement", "rating", "dx_score", "version", "song_type", "song_id"] if c in df.columns]
        st.dataframe(df[cols], use_container_width=True, hide_index=True)
        st.download_button("导出全部匹配成绩 CSV", df[cols].to_csv(index=False).encode("utf-8-sig"), file_name="all_matched_scores.csv", mime="text/csv")
st.markdown("<div class='section-separator'></div>", unsafe_allow_html=True)

# All ambiguity/manual matching controls are deliberately placed at the very bottom.
if unmatched:
    with st.expander("歧义池 · 手动指定谱面（{} 条）".format(len(unmatched)), expanded=False):
        for item in unmatched:
            candidates = item.get("candidates") or []
            st.markdown("**{} · {} · {:.4f}% · DX {}** — {}".format(html.escape(str(item.get("title", "未知曲目"))), html.escape(str(item.get("difficulty", ""))), float(item.get("achievement", 0) or 0), int(item.get("dx_score", 0) or 0), html.escape(str(item.get("match_status", "未匹配")))))
            if not candidates:
                continue
            labels = ["{} | {} | 等级 {} | {} | {} | {}".format(c.get("title", "?"), c.get("difficulty", "?"), c.get("level_text") or "未知", c.get("constant", "?"), c.get("song_type", "?"), c.get("version", "?")) for c in candidates]
            sig = score_signature(item)
            widget_key = "manual_match_v09_" + str(abs(hash(sig)))
            st.selectbox("选择对应谱面", ["暂不选择"] + labels, key=widget_key, help="选择正确的 SD/DX 谱面后会纳入 Rating 计算。")
        unmatched_df = pd.DataFrame(unmatched)
        cols = [c for c in ["title", "difficulty", "level_text", "achievement", "dx_score", "match_status"] if c in unmatched_df.columns]
        st.dataframe(unmatched_df[cols], use_container_width=True, hide_index=True)
        st.download_button("导出未匹配记录 CSV", unmatched_df[cols].to_csv(index=False).encode("utf-8-sig"), file_name="unmatched_scores.csv", mime="text/csv")
else:
    with st.expander("歧义池 · 手动指定谱面", expanded=False):
        st.success("当前没有未匹配或存在歧义的成绩。")

