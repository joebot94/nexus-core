"""MGP video-wall composition layer — topology, builder/combiner MGP roles, and
end-to-end tile signal-path resolution across the DMS fabric.

Ported from GlitchWall (`Core/Topology.swift`) and grounded in Joe's real signal
chain (docs/VIDEOWALL-MGP-DESIGN.md in GlitchBoard). Sits ABOVE the MTPX cascade
layer (`wallplan.py`) and feeds the scenes/coordination plane. Pure planning —
fires nothing; resolves what each tile's path IS and which moves are possible at
what rate, so the generator can build valid, synced cross-device scenes.

The physical truth this encodes (the DMS is the central fabric, every path hubs
through it):
  digital 3×3: source → DMS(1-9) → builder MGP row → DMS(17-19) → combiner MGP5
               → DMS(22) → out
  rgb:  source → SMX → MTPX (skew, 2ns/step ≤62ns) → builder MGP → …same tail
  composite: DMS out → HDMI→composite → 12800 → builder MGP → …same tail
Skew is RGB-path only. Builder MGPs render a row/column; the combiner assembles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Signal(str, Enum):
    """Which signal type — decides the input-side path and whether skew exists."""
    DIGITAL = "digital"      # DVI/HDMI: source → DMS → builder
    RGB = "rgb"              # analog RGBHV: source → SMX → MTPX(skew) → builder
    COMPOSITE = "composite"  # source → DMS → HDMI2composite → 12800 → builder


class Orientation(str, Enum):
    """How builder MGPs divide the wall (from GlitchWall's WallMode)."""
    HORIZONTAL = "horizontal"   # builders own ROWS; window = col + 1
    VERTICAL = "vertical"       # builders own COLUMNS; window = row + 1


class Mechanism(str, Enum):
    """A way to move a tile. Each carries a bench-measured rate ceiling and a
    reach. The generator picks the cheapest mechanism that satisfies a move."""
    INPUT_REMAP = "input_remap"       # swap source feeding a window; can't leave the square
    ANALOG_ROUTE = "analog_route"     # 12800 / SMX-VGA; no handshake
    DVI_CROSSPOINT = "dvi_crosspoint" # DMS crosspoint; usably fast (no re-handshake)
    WINDOW_MOVE = "window_move"       # MGP window geometry; re-handshake territory


# Bench-measured usable switch rates (Hz). Only INPUT_REMAP is Joe-confirmed
# (~15 Hz on MGP input-move, tearing acceptable). The rest are placeholders to
# be filled at the bench — mark verified=False until then.
@dataclass(frozen=True)
class MechanismSpec:
    max_hz: float
    crosses_mgp: bool     # can it move a tile to a different MGP?
    leaves_square: bool   # can it move a tile out of its screen position?
    verified: bool = False


MECHANISMS: dict[Mechanism, MechanismSpec] = {
    Mechanism.INPUT_REMAP:    MechanismSpec(max_hz=15.0, crosses_mgp=False, leaves_square=False, verified=True),
    Mechanism.ANALOG_ROUTE:   MechanismSpec(max_hz=12.0, crosses_mgp=True, leaves_square=True),
    Mechanism.DVI_CROSSPOINT: MechanismSpec(max_hz=12.0, crosses_mgp=True, leaves_square=True),
    Mechanism.WINDOW_MOVE:    MechanismSpec(max_hz=4.0, crosses_mgp=False, leaves_square=True),
}


@dataclass(frozen=True)
class LayoutSpec:
    """GlitchWall §5 layout table, keyed by total tile count."""
    rows: int
    cols: int
    builder_preset: int    # the window preset a builder MGP runs (its row/col)
    combiner_preset: int   # the preset the combiner MGP runs to assemble
    builders_used: int


# One MGP has 4 windows, so a grid of ≤4 tiles is done entirely by a single MGP
# (Joe: "in 2×2 mode it is the assembler and everything all in one"). Larger
# grids need builder MGPs (one per row/col) plus a combiner. NB: GlitchWall's
# LayoutSpec.builders_used differs for 4 tiles — Joe's real rig does 2×2 in one
# MGP, and that rule (window capacity) governs single-vs-multi here.
MGP_WINDOWS = 4

LAYOUTS: dict[int, LayoutSpec] = {
    1:  LayoutSpec(1, 1, 1, 1, 1),
    2:  LayoutSpec(1, 2, 2, 1, 1),
    3:  LayoutSpec(1, 3, 3, 1, 1),
    4:  LayoutSpec(2, 2, 2, 2, 2),
    6:  LayoutSpec(2, 3, 3, 2, 2),
    8:  LayoutSpec(2, 4, 4, 2, 2),
    9:  LayoutSpec(3, 3, 3, 3, 3),
    12: LayoutSpec(3, 4, 4, 3, 3),
    16: LayoutSpec(4, 4, 4, 4, 4),   # added for Joe's 4×4 (four-wide rows)
}


@dataclass(frozen=True)
class Tile:
    row: int
    col: int


@dataclass
class DMSPorts:
    """DMS port map for the wall (seeded with Joe's confirmed 3×3 digital)."""
    source_base: int = 1        # source→DMS occupies in/out source_base..+tiles-1
    builder_return_base: int = 17  # builder→DMS returns at in/out 17,18,19,…
    combiner_out: int = 22      # combiner MGP output lands on this DMS input


@dataclass
class WallConfig:
    """One resolved wall: grid size, orientation, signal style, MGP roles, and
    the fabric wiring. `builder_devices` are the row/column MGPs (registry ids);
    `combiner_device` assembles. For 2×2 the single MGP is both."""
    tiles: int
    orientation: Orientation = Orientation.HORIZONTAL
    signal: Signal = Signal.DIGITAL
    builder_devices: list[str] = field(default_factory=list)
    combiner_device: str = ""
    source_device: str = ""          # the IR/IPCP 16-port HDMI controller
    dms_device: str = "device.dms.main"
    smx_device: str = "device.smx.main"
    mtpx_devices: list[str] = field(default_factory=list)
    matrix_device: str = "device.matrix.main"   # the 12800 (composite router)
    ports: DMSPorts = field(default_factory=DMSPorts)

    @property
    def layout(self) -> LayoutSpec:
        if self.tiles not in LAYOUTS:
            raise VideowallError(f"no layout for {self.tiles} tiles "
                                 f"(known: {sorted(LAYOUTS)})")
        return LAYOUTS[self.tiles]

    @property
    def is_single_mgp(self) -> bool:
        """≤4 tiles: one MGP builds AND combines (it has 4 windows)."""
        return self.tiles <= MGP_WINDOWS


class VideowallError(ValueError):
    pass


# ---- tile → (builder, window) resolution (ported resolveTarget) ------------

def cells(spec: LayoutSpec) -> list[Tile]:
    return [Tile(r, c) for r in range(spec.rows) for c in range(spec.cols)]


def resolve_builder(tile: Tile, orientation: Orientation) -> tuple[int, int]:
    """Return (builder_index, window) that owns this tile in a MULTI-MGP wall.
    Horizontal: builder owns the row, window = col+1. Vertical: the reverse."""
    if orientation is Orientation.HORIZONTAL:
        return tile.row, tile.col + 1
    return tile.col, tile.row + 1


def builder_window(tile: Tile, wall: WallConfig) -> tuple[int, int]:
    """(builder_index, window) for a tile, honoring single-MGP walls where every
    tile lands on the one MGP's four windows in order."""
    if wall.is_single_mgp:
        return 0, cells(wall.layout).index(tile) + 1
    return resolve_builder(tile, wall.orientation)


# ---- signal-path resolution ------------------------------------------------

@dataclass
class Hop:
    """One stage of a tile's journey through the rig."""
    stage: str
    device: str
    detail: str


def tile_path(tile: Tile, wall: WallConfig) -> list[Hop]:
    """Resolve one tile's full signal chain, source → wall output, honoring the
    signal style's ingest path and the DMS builder→combiner tail. This is what
    lets a skew/scramble target the RIGHT square and keep sync."""
    spec = wall.layout
    tiles_in_order = cells(spec)
    if tile not in tiles_in_order:
        raise VideowallError(f"{tile} not in a {spec.rows}×{spec.cols} wall")
    index = tiles_in_order.index(tile)            # 0-based tile number
    builder_i, window = builder_window(tile, wall)
    builder = wall.builder_devices[builder_i] if builder_i < len(wall.builder_devices) else f"builder[{builder_i}]"
    p = wall.ports
    hops: list[Hop] = []

    # --- ingest: source → (style-specific) → builder MGP input `window` ---
    src_port = p.source_base + index
    if wall.signal is Signal.DIGITAL:
        hops.append(Hop("source", wall.source_device or "wall-controller",
                        f"tile {index + 1} out → DMS in {src_port}"))
        hops.append(Hop("route", wall.dms_device,
                        f"DMS out {src_port} → {builder} DVI in {window}"))
    elif wall.signal is Signal.RGB:
        hops.append(Hop("source", wall.source_device or "rgb-source", f"tile {index + 1} RGB out → SMX"))
        hops.append(Hop("route", wall.smx_device, "SMX → MTPX"))
        mtpx = wall.mtpx_devices[builder_i] if builder_i < len(wall.mtpx_devices) else "mtpx"
        hops.append(Hop("skew", mtpx, f"MTPX skew (0–31 = 0–62ns line delay) → {builder} RGBHV in {window}"))
    elif wall.signal is Signal.COMPOSITE:
        hops.append(Hop("source", wall.source_device or "wall-controller",
                        f"tile {index + 1} out → DMS in {src_port}"))
        hops.append(Hop("route", wall.dms_device, f"DMS out {src_port} → HDMI→composite adapter"))
        hops.append(Hop("route", wall.matrix_device, f"12800 composite route → {builder} composite in {window}"))

    hops.append(Hop("build", builder, f"row/col build, window {window} (preset {spec.builder_preset})"))

    # --- tail: single-MGP assembles inline; multi-MGP goes back through DMS ---
    if wall.is_single_mgp:
        hops.append(Hop("assemble", builder, f"same MGP combines (preset {spec.combiner_preset}) → out"))
        return hops

    ret = p.builder_return_base + builder_i
    hops.append(Hop("route", wall.dms_device, f"{builder} out → DMS in {ret}"))
    hops.append(Hop("route", wall.dms_device, f"DMS out {ret} → {wall.combiner_device} in {builder_i + 1}"))
    hops.append(Hop("assemble", wall.combiner_device,
                    f"assemble full {spec.rows}×{spec.cols} (preset {spec.combiner_preset}) → DMS in {p.combiner_out}"))
    hops.append(Hop("output", wall.dms_device, f"DMS out {p.combiner_out} → wall"))
    return hops


# ---- move mechanisms -------------------------------------------------------

def mechanisms_for_move(src: Tile, dst: Tile, wall: WallConfig) -> list[Mechanism]:
    """Which mechanisms can carry a tile's content from `src`'s position to
    `dst`'s position, cheapest first. Same square → input-remap (fast). Same MGP,
    different square → window move. Different MGP → routing."""
    if src == dst:
        return [Mechanism.INPUT_REMAP]
    src_builder, _ = builder_window(src, wall)
    dst_builder, _ = builder_window(dst, wall)
    if src_builder == dst_builder:
        # Same MGP, different position — only a window move relocates within it.
        return [Mechanism.WINDOW_MOVE]
    # Cross-MGP — needs a route. Analog (no handshake) preferred; DVI works too.
    if wall.signal is Signal.RGB or wall.signal is Signal.COMPOSITE:
        return [Mechanism.ANALOG_ROUTE, Mechanism.DVI_CROSSPOINT]
    return [Mechanism.DVI_CROSSPOINT]


def max_rate_hz(mechanism: Mechanism) -> float:
    return MECHANISMS[mechanism].max_hz


def clamp_rate(requested_hz: float, mechanism: Mechanism) -> float:
    """A cue can't drive a mechanism past its usable switch rate."""
    return min(requested_hz, MECHANISMS[mechanism].max_hz)


# ---- baseline scene generation ---------------------------------------------

def baseline_steps(wall: WallConfig) -> list[dict]:
    """Ordered scene steps that recall the wall's 'normal' baseline — the
    known-good reference all chaos deviates from and returns to:
      1. source grid mode (IR via the IPCP),
      2. builder MGP preset(s) + the combiner preset,
      3. identity DMS routing (source→builders, builders→combiner, combiner→out).

    Returned as plain step dicts (target/action/parameters/note) so this stays
    free of the scenes module. The source-mode step is IR-via-IPCP and stays
    un-fireable until the EIR scan wires it — present + dry-runnable regardless.
    """
    spec = wall.layout
    steps: list[dict] = []

    steps.append({"target": wall.source_device, "action": "set_wall_mode",
                  "parameters": {"tiles": wall.tiles},
                  "note": f"{spec.rows}×{spec.cols} mode — IR via IPCP (pending EIR scan)"})

    if wall.is_single_mgp:
        mgp = wall.combiner_device or (wall.builder_devices[0] if wall.builder_devices else "")
        if mgp:
            steps.append({"target": mgp, "action": "recall_preset",
                          "parameters": {"preset": spec.combiner_preset},
                          "note": "one MGP builds + assembles"})
    else:
        for builder in wall.builder_devices[:spec.builders_used]:
            steps.append({"target": builder, "action": "recall_preset",
                          "parameters": {"preset": spec.builder_preset},
                          "note": "builder row/col preset"})
        if wall.combiner_device:
            steps.append({"target": wall.combiner_device, "action": "recall_preset",
                          "parameters": {"preset": spec.combiner_preset},
                          "note": "combiner assemble preset"})

    # Identity DMS routing (moves/scrambles are deltas on this).
    p = wall.ports
    for i in range(wall.tiles):
        port = p.source_base + i
        steps.append({"target": wall.dms_device, "action": "tie",
                      "parameters": {"input": port, "output": port},
                      "note": f"source tile {i + 1} through DMS"})
    if not wall.is_single_mgp:
        for b in range(spec.builders_used):
            port = p.builder_return_base + b
            steps.append({"target": wall.dms_device, "action": "tie",
                          "parameters": {"input": port, "output": port},
                          "note": f"builder {b + 1} → combiner"})
        steps.append({"target": wall.dms_device, "action": "tie",
                      "parameters": {"input": p.combiner_out, "output": p.combiner_out},
                      "note": "combiner → wall"})
    return steps


# ---- procedural glitch generation ------------------------------------------

def _windows_per_builder(wall: WallConfig) -> int:
    """How many windows a single builder MGP drives."""
    if wall.is_single_mgp:
        return wall.tiles
    spec = wall.layout
    return spec.cols if wall.orientation is Orientation.HORIZONTAL else spec.rows


def _builder_device(wall: WallConfig, builder_index: int) -> str:
    if wall.is_single_mgp:
        return wall.combiner_device or (wall.builder_devices[0] if wall.builder_devices else "")
    if builder_index < len(wall.builder_devices):
        return wall.builder_devices[builder_index]
    return f"builder[{builder_index}]"


def scramble_steps(wall: WallConfig, builders: list[int] | None = None,
                   seed: int = 0) -> list[dict]:
    """Input-remap scramble — the fast, clean glitch. On each chosen builder MGP,
    permute which input feeds each window as a **derangement** (every tile shows a
    different source than baseline; nothing stays put), deterministic from `seed`.
    Emits `route_input_to_window` steps: input remap, ~15 Hz, no handshake, tiles
    keep their screen position. `builders` selects which regions to scramble —
    pass one builder index for "that quadrant goes crazy, the rest stays clean."
    """
    n = _windows_per_builder(wall)
    if n < 2:
        return []                      # nothing to permute
    if builders is None:
        builders = [0] if wall.is_single_mgp else list(range(wall.layout.builders_used))
    steps: list[dict] = []
    for builder_index in builders:
        device = _builder_device(wall, builder_index)
        # A non-zero rotation is always a derangement — no window keeps its input.
        shift = 1 + ((seed + builder_index) % (n - 1))
        for window in range(1, n + 1):
            source_input = ((window - 1 + shift) % n) + 1
            steps.append({"target": device, "action": "route_input_to_window",
                          "parameters": {"input": source_input, "window": window},
                          "note": f"scramble: input {source_input} → window {window}"})
    return steps


def _rand_skew(seed: int, tile: Tile, salt: int, ceiling: int) -> int:
    """Deterministic per-tile per-channel skew value in 0..ceiling."""
    x = (seed * 2654435761 + tile.row * 40503 + tile.col * 97 + salt * 131) & 0xFFFFFFFF
    x ^= x >> 13
    x = (x * 1274126177) & 0xFFFFFFFF
    x ^= x >> 16
    return x % (ceiling + 1)


def skew_burst_steps(wall: WallConfig, tiles: list[Tile] | None = None, *,
                     r: int = 0, g: int = 0, b: int = 0,
                     random_seed: int | None = None, max_skew: int = 31) -> list[dict]:
    """Apply MTPX RGB line-skew (0-31 = 0-62ns) to chosen tiles — the signature
    Joebot glitch. **RGB-path only** (skew ghosts on composite/digital), so this
    returns [] for any other signal type. Each tile resolves to its builder's
    MTPX and the input feeding its window (via `builder_window`); channels are
    grouped into one `set_input_skew_batch` per MTPX so a burst fans across that
    unit's lane pool. `random_seed` gives deterministic per-tile skew up to
    `max_skew`; otherwise every chosen tile gets the same (r,g,b)."""
    if wall.signal is not Signal.RGB:
        return []
    targets = tiles if tiles is not None else cells(wall.layout)
    by_device: dict[str, list[dict]] = {}
    for tile in targets:
        builder_index, window = builder_window(tile, wall)
        device = (wall.mtpx_devices[builder_index]
                  if builder_index < len(wall.mtpx_devices) else f"mtpx[{builder_index}]")
        if random_seed is not None:
            rr = _rand_skew(random_seed, tile, 1, max_skew)
            gg = _rand_skew(random_seed, tile, 2, max_skew)
            bb = _rand_skew(random_seed, tile, 3, max_skew)
        else:
            rr, gg, bb = r, g, b
        by_device.setdefault(device, []).append(
            {"input": window, "r": rr, "g": gg, "b": bb})
    return [{"target": device, "action": "set_input_skew_batch",
             "parameters": {"channels": channels},
             "note": f"skew burst — {len(channels)} input(s), RGB line delay"}
            for device, channels in by_device.items()]


def freeze_steps(wall: WallConfig, tiles: list[Tile] | None = None, *,
                 mode: str = "freeze", on: bool = True) -> list[dict]:
    """Freeze or blank chosen tiles at their builder MGP window — the FX-chase
    stutter (GlitchWall-verified `{w}*{0|1}F` / `{w}*{0|1}B`). Applied to the
    builder's window (before assembly), so it holds/kills exactly that tile.
    `mode` = "freeze" | "blank"; `on=False` releases."""
    if mode not in ("freeze", "blank"):
        raise VideowallError(f"mode must be 'freeze' or 'blank', got {mode!r}")
    action = "set_window_freeze" if mode == "freeze" else "set_window_blank"
    targets = tiles if tiles is not None else cells(wall.layout)
    steps: list[dict] = []
    for tile in targets:
        builder_index, window = builder_window(tile, wall)
        device = _builder_device(wall, builder_index)
        steps.append({"target": device, "action": action,
                      "parameters": {"window": window, "on": 1 if on else 0},
                      "note": f"{mode} {'on' if on else 'off'} — window {window}"})
    return steps


@dataclass
class RegionChaos:
    """How chaotic one builder region (MGP) should be. Absent regions stay
    clean (baseline) — that's the "one quadrant crazy, rest untouched" control."""
    builder: int
    scramble: bool = False
    skew: int = 0          # 0 = none; else max per-tile RGB skew (RGB walls only)
    freeze: bool = False   # freeze the region's tiles


def _region_tiles(wall: WallConfig, builder_index: int) -> list[Tile]:
    return [t for t in cells(wall.layout)
            if builder_window(t, wall)[0] == builder_index]


def chaos_steps(wall: WallConfig, regions: list[RegionChaos], seed: int = 0) -> list[dict]:
    """Compose the glitch toolkit per region — scramble (input-remap), skew
    (MTPX RGB), and freeze (MGP FX) — into ONE delta scene, so you can crank one
    quadrant to full chaos and leave the rest on the clean baseline.
    Deterministic from `seed`. Skew is silently dropped on non-RGB walls."""
    steps: list[dict] = []
    for region in regions:
        if region.scramble:
            steps += scramble_steps(wall, builders=[region.builder], seed=seed)
        if region.skew > 0 and wall.signal is Signal.RGB:
            steps += skew_burst_steps(wall, tiles=_region_tiles(wall, region.builder),
                                      random_seed=seed, max_skew=region.skew)
        if region.freeze:
            steps += freeze_steps(wall, tiles=_region_tiles(wall, region.builder),
                                  mode="freeze")
    return steps
