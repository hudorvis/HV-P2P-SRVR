from __future__ import annotations

import math
import os
import time
import tkinter as tk
from tkinter import ttk, messagebox

# Locked grey theme derived from the approved Run / Free-D renders.
BG = "#0b0f12"
BG2 = "#0f1418"
PANEL = "#151a1e"
PANEL_2 = "#191f23"
FIELD = "#171c20"
FIELD_2 = "#1d2327"
BORDER = "#41484d"
BORDER_SOFT = "#30373b"
TEXT = "#f0f1f2"
TEXT_2 = "#c6c9cb"
MUTED = "#92989c"
GREEN = "#66e53a"
GREEN_DARK = "#12361b"
GREEN_SOFT = "#244b2a"
RED = "#e34848"
AMBER = "#d49b29"
WHITE = "#f4f4f4"
RAMP = "#343a3e"
RAMP_EDGE = "#737a7e"

FONT_FAMILY = "Helvetica Neue"
APP_VERSION = "v26.08.17.01"


def install_modern_ui(AppClass, G):
    """Install the locked-design UI while leaving the proven backend untouched.

    The legacy UI is still built into an unmanaged compatibility frame so all
    existing StringVars/callbacks/timers continue to exist. The visible UI is
    then drawn independently to match the approved renders.
    """

    tk_mod = G.get("tk", tk)
    ttk_mod = G.get("ttk", ttk)
    legacy_build_layout = AppClass._build_layout
    legacy_preset_refresh = AppClass._refresh_preset_confirm_buttons
    legacy_limit_refresh = AppClass._refresh_limit_confirm_buttons
    legacy_to_config = AppClass._to_config_dict
    legacy_apply_freed_config = AppClass._apply_freed_config

    def _font(size=12, weight="normal"):
        return (FONT_FAMILY, size, weight)

    def _safe_float(value, default=0.0):
        try:
            return float(value)
        except Exception:
            return float(default)

    def _safe_int(value, default=0):
        try:
            return int(float(value))
        except Exception:
            return int(default)

    def _config_style(self):
        style = ttk_mod.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(
            "HV.TCombobox",
            background=FIELD,
            fieldbackground=FIELD,
            foreground=TEXT,
            arrowcolor=TEXT_2,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=(7, 3),
            font=_font(11),
        )
        style.map(
            "HV.TCombobox",
            fieldbackground=[("readonly", FIELD)],
            foreground=[("readonly", TEXT)],
            selectbackground=[("readonly", FIELD)],
            selectforeground=[("readonly", TEXT)],
        )
        style.configure(
            "HV.TCheckbutton",
            background=PANEL,
            foreground=TEXT,
            indicatorbackground=FIELD,
            indicatorforeground=GREEN,
            bordercolor=BORDER,
            focusthickness=0,
            font=_font(11),
        )
        style.map("HV.TCheckbutton", background=[("active", PANEL)])
        style.configure("HV.Vertical.TScrollbar", background=PANEL_2, troughcolor=BG2, bordercolor=BORDER)
        return style

    def _panel(parent, **kwargs):
        f = tk_mod.Frame(parent, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, bd=0, **kwargs)
        return f

    def _label(parent, text="", *, size=11, fg=TEXT, bg=None, weight="normal", anchor="w", **kwargs):
        return tk_mod.Label(
            parent,
            text=text,
            fg=fg,
            bg=bg if bg is not None else parent.cget("bg"),
            font=_font(size, weight),
            anchor=anchor,
            bd=0,
            **kwargs,
        )

    def _value_label(parent, text="", textvariable=None, *, size=11, anchor="center", fg=TEXT, width=None):
        kw = dict(
            fg=fg,
            bg=FIELD,
            font=_font(size),
            anchor=anchor,
            bd=0,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=7,
            pady=3,
        )
        if width is not None:
            kw["width"] = width
        if textvariable is not None:
            kw["textvariable"] = textvariable
        else:
            kw["text"] = text
        return tk_mod.Label(parent, **kw)

    def _entry(parent, var, *, width=10, justify="left", size=11):
        return tk_mod.Entry(
            parent,
            textvariable=var,
            width=width,
            justify=justify,
            bg=FIELD,
            fg=TEXT,
            insertbackground=TEXT,
            selectbackground=GREEN_SOFT,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=GREEN,
            font=_font(size),
        )

    def _button(parent, text="", command=None, *, var=None, compact=False, selected=False, width=None, fg=TEXT):
        btn = tk_mod.Button(
            parent,
            text=text if var is None else "",
            textvariable=var,
            command=command,
            bg=GREEN_DARK if selected else FIELD_2,
            activebackground=GREEN_SOFT if selected else "#262d31",
            fg=GREEN if selected else fg,
            activeforeground=GREEN if selected else TEXT,
            font=_font(10 if compact else 11),
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground=GREEN if selected else BORDER,
            highlightcolor=GREEN,
            padx=7 if compact else 10,
            pady=2 if compact else 4,
            cursor="hand2",
        )
        if width is not None:
            btn.configure(width=width)
        return btn

    def _set_selected(btn, selected: bool):
        try:
            btn.configure(
                bg=GREEN_DARK if selected else FIELD_2,
                activebackground=GREEN_SOFT if selected else "#262d31",
                fg=GREEN if selected else TEXT,
                activeforeground=GREEN if selected else TEXT,
                highlightbackground=GREEN if selected else BORDER,
            )
        except Exception:
            pass

    def _separator(parent, y=None):
        f = tk_mod.Frame(parent, bg=BORDER_SOFT, height=1)
        return f

    def _draw_logo(canvas):
        canvas.delete("all")
        w, h = max(1, canvas.winfo_width()), max(1, canvas.winfo_height())
        canvas.create_round_rectangle = getattr(canvas, "create_round_rectangle", None)
        # Tk has no rounded rectangle primitive; use a clean rectangular outline with corner arcs.
        pad = 4
        r = 10
        x0, y0, x1, y1 = pad, pad, w-pad, h-pad
        canvas.create_arc(x0, y0, x0+2*r, y0+2*r, start=90, extent=90, style="arc", outline=GREEN, width=1)
        canvas.create_arc(x1-2*r, y0, x1, y0+2*r, start=0, extent=90, style="arc", outline=GREEN, width=1)
        canvas.create_arc(x0, y1-2*r, x0+2*r, y1, start=180, extent=90, style="arc", outline=GREEN, width=1)
        canvas.create_arc(x1-2*r, y1-2*r, x1, y1, start=270, extent=90, style="arc", outline=GREEN, width=1)
        canvas.create_line(x0+r, y0, x1-r, y0, fill=GREEN)
        canvas.create_line(x0+r, y1, x1-r, y1, fill=GREEN)
        canvas.create_line(x0, y0+r, x0, y1-r, fill=GREEN)
        canvas.create_line(x1, y0+r, x1, y1-r, fill=GREEN)
        canvas.create_text(w/2, h*0.40, text="P2P", fill=TEXT, font=_font(19, "bold"))
        canvas.create_text(w/2, h*0.70, text="SRVR", fill=TEXT_2, font=_font(11, "bold"))

    def _status_card(self, parent, title, subtitle_var, dot_canvas_attr):
        card = _panel(parent)
        card.grid_propagate(False)
        card.configure(height=58)
        card.columnconfigure(1, weight=1)
        dot = tk_mod.Canvas(card, width=20, height=20, bg=PANEL, highlightthickness=0)
        dot.grid(row=0, column=0, rowspan=2, padx=(12, 8), pady=10)
        setattr(self, dot_canvas_attr, dot)
        _label(card, title, size=13, weight="normal").grid(row=0, column=1, sticky="sw", pady=(7, 0))
        _label(card, textvariable=subtitle_var, size=10, fg=TEXT_2).grid(row=1, column=1, sticky="nw", pady=(0, 6))
        return card

    def _dot(canvas, color):
        try:
            canvas.delete("all")
            canvas.create_oval(3, 3, 17, 17, fill=color, outline=color)
        except Exception:
            pass

    def _build_header(self, root):
        hdr = tk_mod.Frame(root, bg=BG, height=72)
        hdr.grid(row=0, column=0, sticky="ew", padx=14, pady=(8, 4))
        hdr.grid_propagate(False)
        hdr.columnconfigure(2, weight=1)
        hdr.columnconfigure(3, minsize=115)

        logo = tk_mod.Canvas(hdr, width=80, height=58, bg=BG, highlightthickness=0)
        logo.grid(row=0, column=0, sticky="w")
        logo.bind("<Configure>", lambda _e: _draw_logo(logo))
        _label(hdr, "HV P2P  |  SRVR", size=22, weight="bold", bg=BG).grid(row=0, column=1, sticky="w", padx=(10, 30))

        cards = tk_mod.Frame(hdr, bg=BG)
        cards.grid(row=0, column=2, sticky="ew")
        for i in range(3):
            cards.columnconfigure(i, weight=1, uniform="status")
        self.modern_ctrl_sub = tk_mod.StringVar(value="Disconnected   172.20.1.101")
        self.modern_w1p_sub = tk_mod.StringVar(value="Disconnected   172.20.1.102")
        self.modern_freed_sub = tk_mod.StringVar(value="Inactive   0.000 fps")
        c1 = _status_card(self, cards, "CTRL", self.modern_ctrl_sub, "modern_ctrl_dot")
        c2 = _status_card(self, cards, "W1P", self.modern_w1p_sub, "modern_w1p_dot")
        c3 = _status_card(self, cards, "Free-D", self.modern_freed_sub, "modern_freed_dot")
        c1.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        c2.grid(row=0, column=1, sticky="ew", padx=5)
        c3.grid(row=0, column=2, sticky="ew", padx=(5, 0))
        _label(hdr, APP_VERSION, size=11, fg=TEXT_2, bg=BG, anchor="e").grid(row=0, column=3, sticky="e", padx=(28, 8))

    def _build_banner(self, root):
        self.modern_banner = tk_mod.Frame(root, bg="#102b18", highlightbackground="#2d6c36", highlightthickness=1, height=48)
        self.modern_banner.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 7))
        self.modern_banner.grid_propagate(False)
        self.modern_banner_text = tk_mod.StringVar(value="SYSTEM READY")
        _label(self.modern_banner, "♢", size=25, fg=GREEN, bg="#102b18", anchor="e").pack(side="left", expand=True, fill="x")
        _label(self.modern_banner, textvariable=self.modern_banner_text, size=20, fg=GREEN, bg="#102b18", weight="bold", anchor="w").pack(side="left", expand=True, fill="x", padx=(10, 0))

    def _show_page(self, page_name):
        self.modern_page = page_name
        try:
            self.modern_pages[page_name].tkraise()
        except Exception:
            return
        for name, btn in self.modern_nav_buttons.items():
            selected = name == page_name
            _set_selected(btn, False)
            btn.configure(fg=TEXT, highlightbackground=BORDER)
            line = self.modern_nav_lines.get(name)
            if line is not None:
                line.configure(bg=TEXT if selected else BG2)
        # Page-specific footer controls.
        if hasattr(self, "modern_freed_footer_actions"):
            if page_name == "Free-D":
                self.modern_freed_footer_actions.place(relx=0.5, rely=0.5, anchor="center")
            else:
                self.modern_freed_footer_actions.place_forget()
        if page_name in ("Run", "Free-D"):
            self.root.after(20, self._modern_redraw_all)

    def _build_nav(self, root):
        nav = _panel(root, height=50)
        nav.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 8))
        nav.grid_propagate(False)
        for i in range(4):
            nav.columnconfigure(i, weight=1, uniform="nav")
        names = [("Run", "▷"), ("Setup", "⚙"), ("Free-D", "⌖"), ("Log", "▤")]
        self.modern_nav_buttons = {}
        self.modern_nav_lines = {}
        for i, (name, icon) in enumerate(names):
            cell = tk_mod.Frame(nav, bg=PANEL)
            cell.grid(row=0, column=i, sticky="nsew")
            cell.rowconfigure(0, weight=1)
            cell.columnconfigure(0, weight=1)
            btn = tk_mod.Button(
                cell, text=f"{icon}   {name}", command=lambda n=name: _show_page(self, n),
                bg=PANEL, activebackground=PANEL_2, fg=TEXT, activeforeground=TEXT,
                font=_font(14), relief="flat", bd=0, highlightthickness=0, cursor="hand2"
            )
            btn.grid(row=0, column=0, sticky="nsew")
            line = tk_mod.Frame(cell, bg=TEXT if name == "Run" else BG2, height=1)
            line.grid(row=1, column=0, sticky="ew")
            self.modern_nav_buttons[name] = btn
            self.modern_nav_lines[name] = line
            if i:
                tk_mod.Frame(nav, bg=BORDER_SOFT, width=1).grid(row=0, column=i, sticky="nsw")

    def _build_footer(self, root):
        footer = _panel(root, height=48)
        footer.grid(row=4, column=0, sticky="ew", padx=14, pady=(8, 10))
        footer.grid_propagate(False)
        footer.columnconfigure(1, weight=1)
        self.modern_time_var = tk_mod.StringVar(value="--")
        self.modern_uptime_var = tk_mod.StringVar(value="--")
        _label(footer, "SRVR Time:", size=11, fg=TEXT_2).grid(row=0, column=0, sticky="w", padx=(12, 8))
        _label(footer, textvariable=self.modern_time_var, size=11, fg=TEXT_2).grid(row=0, column=1, sticky="w")
        self.modern_freed_footer_actions = tk_mod.Frame(footer, bg=PANEL)
        _button(self.modern_freed_footer_actions, "Apply", self._modern_freed_apply, width=12).pack(side="left", padx=5)
        _button(self.modern_freed_footer_actions, "Reset", self._modern_freed_reset, width=12).pack(side="left", padx=5)
        _label(footer, "Uptime:", size=11, fg=TEXT_2).grid(row=0, column=3, sticky="e", padx=(8, 8))
        _label(footer, textvariable=self.modern_uptime_var, size=11, fg=TEXT_2, anchor="e").grid(row=0, column=4, sticky="e", padx=(0, 12))

    def _tower(canvas, x, y, scale=1.0):
        col = "#d6d8da"
        h = 54*scale
        w = 20*scale
        canvas.create_line(x, y, x-w/2, y+h, fill=col, width=1)
        canvas.create_line(x, y, x+w/2, y+h, fill=col, width=1)
        canvas.create_line(x-w/2, y+h, x+w/2, y+h, fill=col, width=1)
        for frac in (0.22, 0.44, 0.66, 0.84):
            yy = y+h*frac
            half = w*frac/2
            canvas.create_line(x-half, yy, x+half, yy, fill=col, width=1)
        canvas.create_line(x-w/2, y+h, x+w/2, y+h*0.42, fill=col, width=1)
        canvas.create_line(x+w/2, y+h, x-w/2, y+h*0.42, fill=col, width=1)

    def _camera_icon(canvas, x, y, color="#d7d9da"):
        canvas.create_rectangle(x-10, y-7, x+10, y+7, outline=color, width=1)
        canvas.create_rectangle(x-6, y-11, x+6, y-7, outline=color, width=1)
        canvas.create_oval(x-3, y-3, x+3, y+3, outline=color, width=1)

    def _draw_run_diagram(self, canvas, side=False):
        try:
            canvas.delete("all")
            w = max(500, canvas.winfo_width())
            h = max(120, canvas.winfo_height())
            left = 96
            right = w - 96
            top = 34
            bottom = h - 24
            span = max(0.1, _safe_float(getattr(self.state, "total_length_m", 100.0), 100.0))
            try:
                near_abs = _safe_float(self.state.near_limit.position_m, 0.0)
                far_abs = _safe_float(self.state.far_limit.position_m, near_abs + span)
                span = max(0.1, abs(far_abs - near_abs))
            except Exception:
                near_abs, far_abs = 0.0, span

            def x_for(rel):
                return left + max(0.0, min(1.0, rel/span))*(right-left)

            # Cable / path.
            if side:
                sag = max(10.0, min(34.0, h*0.18))
                y_end = top + 28
                y_mid = y_end + sag
                pts = []
                for i in range(61):
                    t = i/60
                    x = left + t*(right-left)
                    y = y_end + sag*(4*t*(1-t))
                    pts.extend((x, y))
                canvas.create_line(*pts, fill="#cfd2d3", width=1, smooth=True)
                cable_y = lambda rel: y_end + sag*(4*(rel/span)*(1-rel/span))
            else:
                y_line = top + 32
                canvas.create_line(left, y_line, right, y_line, fill="#cfd2d3", width=1)
                cable_y = lambda rel: y_line

            # Ramp zones as subtle wedges at each end, no text label.
            near_ramp = max(0.0, min(span, _safe_float(getattr(self.state, "ramp_zone_near", 0.0))))
            far_ramp = max(0.0, min(span, _safe_float(getattr(self.state, "ramp_zone_far", 0.0))))
            # fall back to limit-point values if available
            if near_ramp <= 0:
                near_ramp = max(0.0, min(span, _safe_float(getattr(self.state.near_limit, "ramp_distance_m", 0.0))))
            if far_ramp <= 0:
                far_ramp = max(0.0, min(span, _safe_float(getattr(self.state.far_limit, "ramp_distance_m", 0.0))))
            ramp_y = bottom - 2
            if near_ramp > 0:
                nx = x_for(near_ramp)
                canvas.create_polygon(left, cable_y(0), nx, cable_y(near_ramp), nx, ramp_y, left, ramp_y,
                                      fill="#23292d", outline="")
                canvas.create_line(nx, cable_y(near_ramp), nx, ramp_y, fill=BORDER, dash=(4,4))
            if far_ramp > 0:
                fx = x_for(span-far_ramp)
                canvas.create_polygon(fx, cable_y(span-far_ramp), right, cable_y(span), right, ramp_y, fx, ramp_y,
                                      fill="#23292d", outline="")
                canvas.create_line(fx, cable_y(span-far_ramp), fx, ramp_y, fill=BORDER, dash=(4,4))

            # End towers / labels / limit lines.
            _tower(canvas, 42, top+36, 0.78)
            _tower(canvas, w-42, top+36, 0.78)
            canvas.create_text(42, top+20, text="NEAR", fill=TEXT_2, font=_font(9, "bold"))
            canvas.create_text(w-42, top+20, text="FAR", fill=TEXT_2, font=_font(9, "bold"))
            canvas.create_text(left, top+2, text="NEAR LIMIT", fill=TEXT_2, font=_font(9, "bold"), anchor="n")
            canvas.create_text(right, top+2, text="FAR LIMIT", fill=TEXT_2, font=_font(9, "bold"), anchor="n")
            canvas.create_line(left, top+15, left, bottom, fill="#aaaeb0", dash=(4,4))
            canvas.create_line(right, top+15, right, bottom, fill="#aaaeb0", dash=(4,4))

            # Reference point.
            try:
                ref_abs = _safe_float(self.state.ref_point.position_m, near_abs + span/2)
                ref_rel = max(0.0, min(span, ref_abs-near_abs))
            except Exception:
                ref_rel = span/2
            rx = x_for(ref_rel)
            ry = cable_y(ref_rel)
            canvas.create_polygon(rx, ry-5, rx+5, ry, rx, ry+5, rx-5, ry, fill=GREEN, outline="")
            canvas.create_text(rx, ry-22, text="REF", fill=GREEN, font=_font(10, "bold"))

            # Preset markers follow actual positions and visibility. If no preset has
            # ever been configured, show slot guides evenly spaced as a design aid.
            presets = list(getattr(self, "preset_positions", []) or [])
            visible = list(getattr(self, "preset_visible", []) or [])
            any_set = any(p is not None for p in presets[:10])
            for i in range(10):
                if i < len(presets) and presets[i] is not None:
                    rel = max(0.0, min(span, _safe_float(presets[i])))
                    show = bool(visible[i]) if i < len(visible) else True
                    if not show:
                        continue
                elif not any_set:
                    rel = span*(i+1)/11.0
                else:
                    continue
                px = x_for(rel)
                py = cable_y(rel)
                canvas.create_oval(px-4, py-4, px+4, py+4, fill=BG2, outline="#d8dadb", width=1)
                canvas.create_text(px, py-19, text=f"P{i+1}", fill=TEXT_2, font=_font(9))

            # Live skate.
            try:
                rel_pos = _safe_float(self._current_position_relative_m(), span/2)
            except Exception:
                rel_pos = span/2
            rel_pos = max(0.0, min(span, rel_pos))
            sx = x_for(rel_pos)
            sy = cable_y(rel_pos)
            canvas.create_polygon(sx, sy-22, sx-9, sy-39, sx+9, sy-39, fill=GREEN, outline="")
            canvas.create_line(sx, sy-22, sx, sy+23, fill=GREEN, width=2)
            _camera_icon(canvas, sx, sy+30)
            canvas.create_text(sx, sy-50, text="SKATE", fill=GREEN, font=_font(10, "bold"))

            # FOV projection lines retained, label intentionally omitted per final design.
            canvas.create_line(sx, sy+8, x_for(max(0.0, near_ramp)), ramp_y-8, fill="#5e6467", dash=(4,5))
            canvas.create_line(sx, sy+8, x_for(min(span, span-far_ramp)), ramp_y-8, fill="#5e6467", dash=(4,5))
        except Exception:
            pass

    def _run_chart_card(self, parent, title, side=False):
        card = _panel(parent)
        card.columnconfigure(0, weight=1)
        card.rowconfigure(1, weight=1)
        hdr = tk_mod.Frame(card, bg=PANEL)
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(9, 1))
        _label(hdr, title, size=16, weight="bold").pack(side="left")
        subtitle = "X (Tracking) / Y (Sag)" if side else "X (Tracking) / Z (Offset)"
        _label(hdr, subtitle, size=11, fg=MUTED).pack(side="left", padx=(14,0), pady=(3,0))
        cv = tk_mod.Canvas(card, bg=PANEL, highlightthickness=0, height=128)
        cv.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 6))
        if side:
            self.modern_run_side_canvas = cv
        else:
            self.modern_run_top_canvas = cv
        cv.bind("<Configure>", lambda _e, c=cv, s=side: _draw_run_diagram(self, c, s))
        return card

    def _build_run_cards(self, parent):
        row = tk_mod.Frame(parent, bg=BG)
        row.grid(row=2, column=0, sticky="nsew")
        row.rowconfigure(0, weight=1)
        row.grid_propagate(False)
        # Locked fixed ratio: 20% / 25% / 25% / 30%.
        # Use place percentages rather than grid weights so child content can NEVER
        # expand Shortcuts beyond its 30% segment. Gaps are subtracted inside each segment.

        # DRIVE 20%
        drive = _panel(row)
        drive.place(relx=0.00, rely=0, relwidth=0.20, relheight=1, x=0, width=-4)
        drive.columnconfigure(0, weight=1)
        _label(drive, "⚙  DRIVE", size=15, fg=GREEN, weight="bold").grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(12, 9))
        self.modern_drive_mode_var = tk_mod.StringVar(value="Mode 1")
        self.modern_accel_var = tk_mod.StringVar(value="Power")
        self.modern_batt_var = tk_mod.StringVar(value="Off")
        for r, (name, var) in enumerate((("Drive Mode", self.modern_drive_mode_var), ("Acceleration Mode", self.modern_accel_var), ("Battery Change Mode", self.modern_batt_var)), start=1):
            _label(drive, name, size=11, fg=TEXT_2).grid(row=r, column=0, sticky="w", padx=18, pady=12)
            _label(drive, textvariable=var, size=12, anchor="e").grid(row=r, column=1, sticky="e", padx=18, pady=12)
            if r < 3:
                _separator(drive).grid(row=r, column=0, columnspan=2, sticky="sew", padx=18)

        # SPEED 25%
        speed = _panel(row)
        speed.place(relx=0.20, rely=0, relwidth=0.25, relheight=1, x=4, width=-8)
        speed.columnconfigure(0, weight=1)
        speed.columnconfigure(1, weight=1)
        _label(speed, "◴  SPEED", size=15, fg=GREEN, weight="bold").grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(12, 14))
        self.modern_speed_mps = tk_mod.StringVar(value="0.0")
        self.modern_speed_kmh = tk_mod.StringVar(value="0.0")
        self.modern_max_mps = tk_mod.StringVar(value="0.0")
        self.modern_max_kmh = tk_mod.StringVar(value="0.0")
        _label(speed, "CURRENT SPEED", size=9, fg=MUTED).grid(row=1, column=0, sticky="w", padx=20)
        _label(speed, "MAX SPEED", size=9, fg=MUTED).grid(row=1, column=1, sticky="w", padx=20)
        _label(speed, textvariable=self.modern_speed_mps, size=26).grid(row=2, column=0, sticky="w", padx=20, pady=(4,0))
        _label(speed, textvariable=self.modern_max_mps, size=26).grid(row=2, column=1, sticky="w", padx=20, pady=(4,0))
        _label(speed, "m/s", size=11, fg=MUTED).grid(row=2, column=0, sticky="e", padx=22, pady=(8,0))
        _label(speed, "m/s", size=11, fg=MUTED).grid(row=2, column=1, sticky="e", padx=22, pady=(8,0))
        _label(speed, textvariable=self.modern_speed_kmh, size=15, fg=GREEN).grid(row=3, column=0, sticky="w", padx=20, pady=(12,0))
        _label(speed, textvariable=self.modern_max_kmh, size=15, fg=GREEN).grid(row=3, column=1, sticky="w", padx=20, pady=(12,0))
        _label(speed, "km/h", size=10, fg=MUTED).grid(row=3, column=0, sticky="e", padx=22, pady=(12,0))
        _label(speed, "km/h", size=10, fg=MUTED).grid(row=3, column=1, sticky="e", padx=22, pady=(12,0))
        tk_mod.Frame(speed, bg=BORDER_SOFT, width=1).place(relx=0.5, rely=0.34, relheight=0.54)

        # POSITION 25%
        pos = _panel(row)
        pos.place(relx=0.45, rely=0, relwidth=0.25, relheight=1, x=4, width=-8)
        pos.columnconfigure(0, weight=1)
        pos.columnconfigure(1, weight=1)
        _label(pos, "⌖  POSITION", size=15, fg=GREEN, weight="bold").grid(row=0, column=0, columnspan=2, sticky="w", padx=18, pady=(12, 10))
        self.modern_pos_var = tk_mod.StringVar(value="0.00")
        self.modern_to_near = tk_mod.StringVar(value="0.00")
        self.modern_to_far = tk_mod.StringVar(value="0.00")
        _label(pos, "CURRENT POSITION", size=9, fg=MUTED, anchor="center").grid(row=1, column=0, columnspan=2, pady=(2,0))
        _label(pos, textvariable=self.modern_pos_var, size=25, anchor="center").grid(row=2, column=0, columnspan=2, pady=(2,6))
        _label(pos, "m", size=10, fg=MUTED).grid(row=2, column=1, sticky="w", padx=(28,0))
        _separator(pos).grid(row=3, column=0, columnspan=2, sticky="ew", padx=18)
        _label(pos, "TO NEAR", size=9, fg=MUTED, anchor="center").grid(row=4, column=0, pady=(10,0))
        _label(pos, "TO FAR", size=9, fg=MUTED, anchor="center").grid(row=4, column=1, pady=(10,0))
        _label(pos, textvariable=self.modern_to_near, size=15, fg=GREEN, anchor="center").grid(row=5, column=0, pady=(5,0))
        _label(pos, textvariable=self.modern_to_far, size=15, fg=GREEN, anchor="center").grid(row=5, column=1, pady=(5,0))
        tk_mod.Frame(pos, bg=BORDER_SOFT, width=1).place(relx=0.5, rely=0.68, relheight=0.25)

        # SHORTCUTS 30%
        shortcuts = _panel(row)
        shortcuts.place(relx=0.70, rely=0, relwidth=0.30, relheight=1, x=4, width=-4)
        shortcuts.columnconfigure(0, weight=1)
        shortcuts.rowconfigure(2, weight=1)
        self.modern_shortcuts = shortcuts
        head = tk_mod.Frame(shortcuts, bg=PANEL)
        head.grid(row=0, column=0, sticky="ew", padx=12, pady=(9, 0))
        head.columnconfigure(0, weight=1)
        _label(head, "▱  SHORTCUTS", size=14, fg=GREEN, weight="bold").grid(row=0, column=0, sticky="w")
        tabs = tk_mod.Frame(shortcuts, bg=PANEL)
        tabs.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 3))
        for i in range(4):
            tabs.columnconfigure(i, weight=1, uniform="shortcut_tabs")
        self.modern_shortcut_tab_buttons = {}
        self.modern_shortcut_tab_lines = {}
        for i, name in enumerate(("Preset 1-5", "Preset 6-10", "Limits", "System")):
            btn = tk_mod.Button(tabs, text=name, command=lambda n=name: self._modern_show_shortcut_tab(n), bg=PANEL, activebackground=PANEL, fg=TEXT, activeforeground=TEXT, relief="flat", bd=0, highlightthickness=0, font=_font(10), cursor="hand2")
            btn.grid(row=0, column=i, sticky="ew", pady=(0,3))
            ln = tk_mod.Frame(tabs, bg=GREEN if i == 0 else PANEL, height=2)
            ln.grid(row=1, column=i, sticky="ew", padx=4)
            self.modern_shortcut_tab_buttons[name] = btn
            self.modern_shortcut_tab_lines[name] = ln
        self.modern_shortcut_body = tk_mod.Frame(shortcuts, bg=PANEL)
        self.modern_shortcut_body.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0,8))
        self.modern_shortcut_body.rowconfigure(0, weight=1)
        self.modern_shortcut_body.columnconfigure(0, weight=1)
        self.modern_shortcut_pages = {}
        for name in ("Preset 1-5", "Preset 6-10", "Limits", "System"):
            f = tk_mod.Frame(self.modern_shortcut_body, bg=PANEL)
            f.grid(row=0, column=0, sticky="nsew")
            self.modern_shortcut_pages[name] = f
        self._modern_build_preset_tab(self.modern_shortcut_pages["Preset 1-5"], 0, 5)
        self._modern_build_preset_tab(self.modern_shortcut_pages["Preset 6-10"], 5, 10)
        self._modern_build_limits_tab(self.modern_shortcut_pages["Limits"])
        self._modern_build_system_tab(self.modern_shortcut_pages["System"])
        self._modern_show_shortcut_tab("Preset 1-5")

    def _modern_build_preset_tab(self, parent, start, end):
        parent.columnconfigure(1, weight=1)
        self.modern_preset_name_vars = getattr(self, "modern_preset_name_vars", [None]*10)
        self.modern_preset_dist_vars = getattr(self, "modern_preset_dist_vars", [None]*10)
        self.modern_preset_save_vars = getattr(self, "modern_preset_save_vars", [None]*10)
        self.modern_preset_recall_vars = getattr(self, "modern_preset_recall_vars", [None]*10)
        self.modern_preset_eye_buttons = getattr(self, "modern_preset_eye_buttons", [None]*10)
        for row, idx in enumerate(range(start, end)):
            _label(parent, f"P{idx+1}", size=10, fg=TEXT_2).grid(row=row, column=0, sticky="w", padx=(0,6), pady=2)
            nv = tk_mod.StringVar(value=(self.preset_names[idx] if idx < len(self.preset_names) else f"P{idx+1}"))
            dv = tk_mod.StringVar(value=("" if idx >= len(self.preset_positions) or self.preset_positions[idx] is None else f"{float(self.preset_positions[idx]):.2f}"))
            sv = tk_mod.StringVar(value="Save")
            rv = tk_mod.StringVar(value="Recall")
            self.modern_preset_name_vars[idx] = nv
            self.modern_preset_dist_vars[idx] = dv
            self.modern_preset_save_vars[idx] = sv
            self.modern_preset_recall_vars[idx] = rv
            e1 = _entry(parent, nv, width=17, size=10)
            e1.grid(row=row, column=1, sticky="ew", padx=(0,6), pady=2, ipady=2)
            e2 = _entry(parent, dv, width=7, justify="center", size=10)
            e2.grid(row=row, column=2, sticky="ew", padx=(0,6), pady=2, ipady=2)
            _button(parent, var=sv, compact=True, command=lambda i=idx: self.on_preset_set(i)).grid(row=row, column=3, sticky="ew", padx=(0,4), pady=2)
            _button(parent, var=rv, compact=True, command=lambda i=idx: self.on_preset_goto(i)).grid(row=row, column=4, sticky="ew", padx=(0,4), pady=2)
            eye = _button(parent, "◉", compact=True, command=lambda i=idx: self.on_preset_toggle_visible(i), width=2)
            eye.grid(row=row, column=5, sticky="e", pady=2)
            self.modern_preset_eye_buttons[idx] = eye
            e1.bind("<FocusOut>", lambda _e, i=idx: self._modern_commit_preset_name(i))
            e1.bind("<Return>", lambda _e, i=idx: self._modern_commit_preset_name(i))
            e2.bind("<FocusOut>", lambda _e, i=idx: self._modern_commit_preset_distance(i))
            e2.bind("<Return>", lambda _e, i=idx: self._modern_commit_preset_distance(i))

    def _modern_commit_preset_name(self, idx):
        try:
            name = self.modern_preset_name_vars[idx].get().strip() or f"P{idx+1}"
            while len(self.preset_names) < 10:
                self.preset_names.append(f"P{len(self.preset_names)+1}")
            self.preset_names[idx] = name
            if idx < len(getattr(self, "preset_name_vars", [])):
                self.preset_name_vars[idx].set(name)
            self._save_config()
            self._modern_redraw_all()
        except Exception:
            pass

    def _modern_commit_preset_distance(self, idx):
        try:
            text = self.modern_preset_dist_vars[idx].get().strip()
            while len(self.preset_positions) < 10:
                self.preset_positions.append(None)
            self.preset_positions[idx] = None if text == "" else float(text)
            if self.preset_positions[idx] is not None:
                self.modern_preset_dist_vars[idx].set(f"{float(self.preset_positions[idx]):.2f}")
            self._save_config()
            self._modern_redraw_all()
        except Exception:
            try:
                self.modern_preset_dist_vars[idx].set("" if self.preset_positions[idx] is None else f"{float(self.preset_positions[idx]):.2f}")
            except Exception:
                pass

    def _modern_show_shortcut_tab(self, name):
        try:
            self.modern_shortcut_pages[name].tkraise()
            self.modern_shortcut_tab = name
            for n, ln in self.modern_shortcut_tab_lines.items():
                ln.configure(bg=GREEN if n == name else PANEL)
                self.modern_shortcut_tab_buttons[n].configure(fg=GREEN if n == name else TEXT)
        except Exception:
            pass

    def _modern_build_limits_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(2, weight=1)
        parent.columnconfigure(3, weight=1)
        self.modern_limit_button_vars = {}
        def action_row(row, label, lp):
            key = "near" if "Near" in label else "far" if "Far" in label else "ref"
            _label(parent, label.upper(), size=10, fg=TEXT_2).grid(row=row, column=0, sticky="w", padx=(0,8), pady=(3,2))
            sv, rv, slv = tk_mod.StringVar(value="Save"), tk_mod.StringVar(value="Recall"), tk_mod.StringVar(value="Slip")
            self.modern_limit_button_vars[(key,"set")] = sv
            self.modern_limit_button_vars[(key,"goto")] = rv
            self.modern_limit_button_vars[(key,"slip")] = slv
            _button(parent, var=sv, compact=True, command=lambda l=lp: self.on_limit_set_button(l)).grid(row=row, column=1, sticky="ew", padx=3, pady=2)
            _button(parent, var=rv, compact=True, command=lambda l=lp: self.on_limit_goto_button(l)).grid(row=row, column=2, sticky="ew", padx=3, pady=2)
            _button(parent, var=slv, compact=True, command=lambda l=lp: self.on_limit_slip_button(l)).grid(row=row, column=3, sticky="ew", padx=3, pady=2)
        action_row(0, "Near Limit", self.state.near_limit)
        self.modern_near_ramp_mode = tk_mod.StringVar(value=str(getattr(self.state.near_limit, "ramp_mode", "Distance") or "Distance"))
        self.modern_near_ramp_value = tk_mod.StringVar(value="2.00")
        _label(parent, "Ramping", size=10, fg=TEXT_2).grid(row=1, column=0, sticky="w", padx=(0,8), pady=(2,6))
        cb = ttk_mod.Combobox(parent, textvariable=self.modern_near_ramp_mode, values=["Distance", "Percentage"], state="readonly", style="HV.TCombobox", width=10)
        cb.grid(row=1, column=1, columnspan=2, sticky="ew", padx=3, pady=(2,6))
        e = _entry(parent, self.modern_near_ramp_value, width=7, justify="center", size=10)
        e.grid(row=1, column=3, sticky="ew", padx=3, pady=(2,6), ipady=2)
        cb.bind("<<ComboboxSelected>>", lambda _e: self._modern_commit_ramp("near"))
        e.bind("<FocusOut>", lambda _e: self._modern_commit_ramp("near"))
        e.bind("<Return>", lambda _e: self._modern_commit_ramp("near"))
        _separator(parent).grid(row=2, column=0, columnspan=4, sticky="ew", pady=2)
        action_row(3, "Far Limit", self.state.far_limit)
        self.modern_far_ramp_mode = tk_mod.StringVar(value=str(getattr(self.state.far_limit, "ramp_mode", "Distance") or "Distance"))
        self.modern_far_ramp_value = tk_mod.StringVar(value="2.00")
        _label(parent, "Ramping", size=10, fg=TEXT_2).grid(row=4, column=0, sticky="w", padx=(0,8), pady=(2,6))
        cb2 = ttk_mod.Combobox(parent, textvariable=self.modern_far_ramp_mode, values=["Distance", "Percentage"], state="readonly", style="HV.TCombobox", width=10)
        cb2.grid(row=4, column=1, columnspan=2, sticky="ew", padx=3, pady=(2,6))
        e2 = _entry(parent, self.modern_far_ramp_value, width=7, justify="center", size=10)
        e2.grid(row=4, column=3, sticky="ew", padx=3, pady=(2,6), ipady=2)
        cb2.bind("<<ComboboxSelected>>", lambda _e: self._modern_commit_ramp("far"))
        e2.bind("<FocusOut>", lambda _e: self._modern_commit_ramp("far"))
        e2.bind("<Return>", lambda _e: self._modern_commit_ramp("far"))
        _separator(parent).grid(row=5, column=0, columnspan=4, sticky="ew", pady=2)
        action_row(6, "Ref Point", self.state.ref_point)
        self._modern_sync_ramp_vars()

    def _modern_sync_ramp_vars(self):
        try:
            for side, lp, mode_var, val_var in (
                ("near", self.state.near_limit, getattr(self, "modern_near_ramp_mode", None), getattr(self, "modern_near_ramp_value", None)),
                ("far", self.state.far_limit, getattr(self, "modern_far_ramp_mode", None), getattr(self, "modern_far_ramp_value", None)),
            ):
                if mode_var is None or val_var is None:
                    continue
                mode = str(getattr(lp, "ramp_mode", "Distance") or "Distance")
                mode = "Percentage" if mode.lower().startswith("percent") else "Distance"
                mode_var.set(mode)
                if mode == "Percentage":
                    v = getattr(lp, "ramp_percentage", None)
                    if v is None:
                        dist = _safe_float(getattr(lp, "ramp_distance_m", 0.0))
                        span = max(0.1, _safe_float(getattr(self.state, "total_length_m", 100.0)))
                        v = dist/span*100.0
                    val_var.set(f"{_safe_float(v):.2f}")
                else:
                    v = getattr(lp, "ramp_distance_m", None)
                    if v is None:
                        v = getattr(self.state, "ramp_zone_near" if side=="near" else "ramp_zone_far", 0.0)
                    val_var.set(f"{_safe_float(v):.2f}")
        except Exception:
            pass

    def _modern_commit_ramp(self, side):
        try:
            lp = self.state.near_limit if side == "near" else self.state.far_limit
            mode_var = self.modern_near_ramp_mode if side == "near" else self.modern_far_ramp_mode
            val_var = self.modern_near_ramp_value if side == "near" else self.modern_far_ramp_value
            mode = mode_var.get()
            value = max(0.0, float(val_var.get()))
            span = max(0.1, _safe_float(getattr(self.state, "total_length_m", 100.0)))
            if mode == "Percentage":
                value = min(100.0, value)
                lp.ramp_mode = "Percentage"
                lp.ramp_percentage = value
                lp.ramp_distance_m = span*value/100.0
            else:
                value = min(span, value)
                lp.ramp_mode = "Distance"
                lp.ramp_distance_m = value
                lp.ramp_percentage = (value/span*100.0)
            if side == "near":
                self.state.ramp_zone_near = lp.ramp_distance_m
            else:
                self.state.ramp_zone_far = lp.ramp_distance_m
            val_var.set(f"{value:.2f}")
            self._sync_limits_to_winch()
            self._save_config()
            self._modern_redraw_all()
        except Exception:
            self._modern_sync_ramp_vars()

    def _modern_build_system_tab(self, parent):
        parent.columnconfigure(1, weight=1)
        parent.columnconfigure(2, weight=1)
        parent.columnconfigure(3, weight=1)
        # Acceleration Mode
        _label(parent, "Acceleration Mode", size=10, fg=TEXT_2).grid(row=0, column=0, sticky="w", padx=(0,8), pady=4)
        self.modern_power_btn = _button(parent, "Power", lambda: self._modern_set_accel("Power"), compact=True)
        self.modern_speed_btn = _button(parent, "Speed", lambda: self._modern_set_accel("Speed"), compact=True)
        self.modern_power_btn.grid(row=0, column=1, sticky="ew", padx=3, pady=4)
        self.modern_speed_btn.grid(row=0, column=2, sticky="ew", padx=3, pady=4)
        # Battery
        _label(parent, "Battery Change Mode", size=10, fg=TEXT_2).grid(row=1, column=0, sticky="w", padx=(0,8), pady=4)
        self.modern_batt_off_btn = _button(parent, "Off", lambda: self._modern_set_batt(False), compact=True)
        self.modern_batt_on_btn = _button(parent, "On", lambda: self._modern_set_batt(True), compact=True)
        self.modern_batt_off_btn.grid(row=1, column=1, sticky="ew", padx=3, pady=4)
        self.modern_batt_on_btn.grid(row=1, column=2, sticky="ew", padx=3, pady=4)
        # Drive Mode single row including editable names.
        _label(parent, "Drive Mode", size=10, fg=TEXT_2).grid(row=2, column=0, sticky="w", padx=(0,8), pady=4)
        drive = tk_mod.Frame(parent, bg=PANEL)
        drive.grid(row=2, column=1, columnspan=3, sticky="ew", padx=3, pady=4)
        for i in range(4):
            drive.columnconfigure(i, weight=1 if i in (1,3) else 0)
        self.modern_mode_buttons = []
        self.modern_mode_name_vars = []
        for idx in range(2):
            b = _button(drive, f"Mode {idx+1}", lambda i=idx: self._modern_select_drive_mode(i), compact=True)
            b.grid(row=0, column=idx*2, sticky="ew", padx=(0,4 if idx==0 else 4))
            name = str(self.drive_modes[idx].get("name", f"Mode {idx+1}")) if idx < len(self.drive_modes) else f"Mode {idx+1}"
            v = tk_mod.StringVar(value=name)
            ent = _entry(drive, v, width=11, size=10)
            ent.grid(row=0, column=idx*2+1, sticky="ew", padx=(0,8 if idx==0 else 0), ipady=2)
            ent.bind("<FocusOut>", lambda _e, i=idx: self._modern_commit_mode_name(i))
            ent.bind("<Return>", lambda _e, i=idx: self._modern_commit_mode_name(i))
            self.modern_mode_buttons.append(b)
            self.modern_mode_name_vars.append(v)
        # Calibration
        _label(parent, "Calibration Mode", size=10, fg=TEXT_2).grid(row=3, column=0, sticky="w", padx=(0,8), pady=4)
        _button(parent, "Limit Calibration", self._modern_open_limit_calibration, compact=True).grid(row=3, column=1, columnspan=2, sticky="ew", padx=3, pady=4)
        _button(parent, "Winch Calibration", self._modern_start_winch_calibration, compact=True).grid(row=3, column=3, sticky="ew", padx=3, pady=4)

    def _modern_set_accel(self, mode):
        try:
            cur = self._display_accel_type()
            if cur != mode:
                self._toggle_accel_type(save_config=True)
            self._modern_refresh_system_controls()
        except Exception:
            pass

    def _modern_set_batt(self, enabled):
        try:
            self._set_battery_change_mode(bool(enabled), save_config=True)
            self._modern_refresh_system_controls()
        except Exception:
            pass

    def _modern_select_drive_mode(self, idx):
        try:
            self._set_active_drive_mode(idx, save_config=True)
            self._modern_refresh_system_controls()
        except Exception:
            pass

    def _modern_commit_mode_name(self, idx):
        try:
            name = self.modern_mode_name_vars[idx].get().strip() or f"Mode {idx+1}"
            self.drive_modes[idx]["name"] = name
            if idx < len(getattr(self, "drive_mode_name_vars", [])):
                self.drive_mode_name_vars[idx].set(name)
            self._sync_drive_mode_legacy_name_keys()
            self._save_config()
            self._modern_refresh_system_controls()
        except Exception:
            pass

    def _modern_refresh_system_controls(self):
        try:
            accel = self._display_accel_type()
            _set_selected(self.modern_power_btn, accel == "Power")
            _set_selected(self.modern_speed_btn, accel == "Speed")
            batt = bool(getattr(self, "battery_change_mode", False))
            _set_selected(self.modern_batt_on_btn, batt)
            _set_selected(self.modern_batt_off_btn, not batt)
            active = int(getattr(self, "active_drive_mode", 0) or 0)
            for i, b in enumerate(getattr(self, "modern_mode_buttons", [])):
                _set_selected(b, i == active)
                if i < len(self.drive_modes):
                    name = str(self.drive_modes[i].get("name", f"Mode {i+1}"))
                    if i < len(self.modern_mode_name_vars) and self.modern_mode_name_vars[i].get() != name:
                        # Avoid disrupting active typing.
                        try:
                            if self.root.focus_get() is not None and self.root.focus_get().cget("textvariable") == str(self.modern_mode_name_vars[i]):
                                continue
                        except Exception:
                            pass
                        self.modern_mode_name_vars[i].set(name)
        except Exception:
            pass

    def _modern_start_winch_calibration(self):
        try:
            self._begin_winch_calibration()
            messagebox.showinfo(
                "Winch Calibration",
                "Winch Calibration has started using the proven backend process.\n\n"
                "This test build keeps that process functional while its final popup design is still pending."
            )
        except Exception as exc:
            messagebox.showerror("Winch Calibration", str(exc))

    def _build_run_page(self, parent):
        parent.rowconfigure(0, weight=1)
        parent.rowconfigure(1, weight=1)
        parent.rowconfigure(2, weight=0, minsize=246)
        parent.columnconfigure(0, weight=1)
        top = _run_chart_card(self, parent, "Top View", side=False)
        side = _run_chart_card(self, parent, "Side View", side=True)
        top.grid(row=0, column=0, sticky="nsew", pady=(0,4))
        side.grid(row=1, column=0, sticky="nsew", pady=4)
        _build_run_cards(self, parent)

    def _free_d_section_header(parent, title):
        _label(parent, title, size=15, weight="bold", anchor="center").grid(row=0, column=0, columnspan=8, sticky="ew", pady=(9, 7))

    def _tiny_check(parent, var):
        return ttk_mod.Checkbutton(parent, variable=var, style="HV.TCheckbutton")

    def _modern_set_onoff_var(self, var, value):
        try:
            var.set("ON" if value else "OFF")
        except Exception:
            pass

    def _build_freed_input_card(self, parent):
        card = _panel(parent)
        _free_d_section_header(card, "FREE-D INPUT")
        for c in range(5):
            card.columnconfigure(c, weight=1 if c in (1,2,3) else 0)
        net = tk_mod.Frame(card, bg=PANEL)
        net.grid(row=1, column=0, columnspan=5, sticky="ew", padx=8, pady=(0,7))
        net.columnconfigure(3, weight=1)
        _label(net, "Input:", size=9, fg=TEXT_2).grid(row=0,column=0,sticky="w")
        self.modern_freed_input_toggle = _button(net, "ON", lambda: self._modern_toggle_freed_input(), compact=True, selected=True)
        self.modern_freed_input_toggle.grid(row=0,column=1,sticky="w",padx=(4,7))
        _label(net, "IP Address:", size=9, fg=TEXT_2).grid(row=0,column=2,sticky="e",padx=(0,4))
        _entry(net, self._freed_input_bind_var, width=10, size=9).grid(row=0,column=3,sticky="ew",ipady=2)
        _label(net, "Port:", size=9, fg=TEXT_2).grid(row=0,column=4,sticky="e",padx=(6,3))
        _entry(net, self._freed_input_port_var, width=5, justify="center", size=9).grid(row=0,column=5,sticky="w",ipady=2)
        headers = ["Parameter", "Raw", "Decoded", "Offset", "Invert"]
        for c, text in enumerate(headers):
            _label(card, text, size=9, fg=TEXT_2, anchor="center").grid(row=2, column=c, sticky="ew", padx=2, pady=3)
        fields = ["Cam ID", "Pan", "Tilt", "Roll", "Zoom", "Focus", "FPS"]
        for r, name in enumerate(fields, start=3):
            _label(card, name, size=10, fg=TEXT_2).grid(row=r, column=0, sticky="ew", padx=(9,3), pady=1)
            raw_var, dec_var = self._freed_input_field_vars.get(name, (tk_mod.StringVar(value="--"), tk_mod.StringVar(value="--")))
            _value_label(card, textvariable=raw_var, size=9).grid(row=r, column=1, sticky="ew", padx=2, pady=1)
            _value_label(card, textvariable=dec_var, size=9).grid(row=r, column=2, sticky="ew", padx=2, pady=1)
            if name in getattr(self, "_freed_input_offset_vars", {}):
                _entry(card, self._freed_input_offset_vars[name], width=7, justify="center", size=9).grid(row=r, column=3, sticky="ew", padx=2, pady=1, ipady=2)
            else:
                _value_label(card, "", size=9).grid(row=r, column=3, sticky="ew", padx=2, pady=1)
            if name in getattr(self, "_freed_input_invert_vars", {}):
                _tiny_check(card, self._freed_input_invert_vars[name]).grid(row=r, column=4, padx=8)
        self.modern_freed_input_rate = tk_mod.StringVar(value="0.000 fps")
        self.modern_freed_input_status = tk_mod.StringVar(value="Waiting")
        foot = tk_mod.Frame(card, bg=PANEL)
        foot.grid(row=10, column=0, columnspan=5, sticky="ew", padx=10, pady=(8,8))
        _label(foot, "Input Rate:", size=10, fg=TEXT_2).pack(side="left")
        _value_label(foot, textvariable=self.modern_freed_input_rate, size=9).pack(side="left", padx=(7,18))
        _label(foot, "Status:", size=10, fg=TEXT_2).pack(side="left")
        _value_label(foot, textvariable=self.modern_freed_input_status, size=9, fg=GREEN).pack(side="left", padx=7)
        return card

    def _modern_toggle_freed_input(self):
        try:
            new = str(self._freed_input_enabled_var.get()).upper() != "ON"
            self._freed_input_enabled_var.set("ON" if new else "OFF")
            self._modern_refresh_freed_toggle_buttons()
        except Exception:
            pass

    def _build_freed_output_card(self, parent):
        card = _panel(parent)
        _free_d_section_header(card, "FREE-D OUTPUT")
        for c in range(5):
            card.columnconfigure(c, weight=1 if c in (1,2,3) else 0)
        net = tk_mod.Frame(card, bg=PANEL)
        net.grid(row=1, column=0, columnspan=5, sticky="ew", padx=8, pady=(0,7))
        net.columnconfigure(3, weight=1)
        _label(net, "Output:", size=9, fg=TEXT_2).grid(row=0,column=0,sticky="w")
        self.modern_freed_output_toggle = _button(net, "OFF", lambda: self._modern_toggle_freed_output(), compact=True)
        self.modern_freed_output_toggle.grid(row=0,column=1,sticky="w",padx=(4,7))
        _label(net, "IP Address:", size=9, fg=TEXT_2).grid(row=0,column=2,sticky="e",padx=(0,4))
        _entry(net, self._freed_ip_var, width=10, size=9).grid(row=0,column=3,sticky="ew",ipady=2)
        _label(net, "Port:", size=9, fg=TEXT_2).grid(row=0,column=4,sticky="e",padx=(6,3))
        _entry(net, self._freed_port_var, width=5, justify="center", size=9).grid(row=0,column=5,sticky="w",ipady=2)
        for c, text in enumerate(["Parameter", "Raw", "Decoded", "Offset", "Invert"]):
            _label(card, text, size=9, fg=TEXT_2, anchor="center").grid(row=2, column=c, sticky="ew", padx=2, pady=3)
        for r, name in enumerate(["X", "Y", "Z", "FPS"], start=3):
            _label(card, name, size=10, fg=TEXT_2).grid(row=r, column=0, sticky="ew", padx=(9,3), pady=1)
            raw_var, dec_var = self._freed_output_field_vars.get(name, (tk_mod.StringVar(value="--"), tk_mod.StringVar(value="--")))
            if name == "FPS":
                _entry(card, self._freed_rate_var, width=7, justify="center", size=9).grid(row=r, column=1, sticky="ew", padx=2, pady=1, ipady=2)
            else:
                _value_label(card, textvariable=raw_var, size=9).grid(row=r, column=1, sticky="ew", padx=2, pady=1)
            _value_label(card, textvariable=dec_var, size=9).grid(row=r, column=2, sticky="ew", padx=2, pady=1)
            if name in getattr(self, "_freed_output_offset_vars", {}):
                _entry(card, self._freed_output_offset_vars[name], width=7, justify="center", size=9).grid(row=r, column=3, sticky="ew", padx=2, pady=1, ipady=2)
                _tiny_check(card, self._freed_output_invert_vars[name]).grid(row=r, column=4, padx=8)
            else:
                _value_label(card, "", size=9).grid(row=r, column=3, sticky="ew", padx=2, pady=1)
        self.modern_freed_output_rate = tk_mod.StringVar(value="0.000 fps")
        self.modern_freed_output_status = tk_mod.StringVar(value="Stopped")
        foot = tk_mod.Frame(card, bg=PANEL)
        foot.grid(row=7, column=0, columnspan=5, sticky="ew", padx=10, pady=(8,8))
        _label(foot, "Output Rate:", size=10, fg=TEXT_2).pack(side="left")
        _value_label(foot, textvariable=self.modern_freed_output_rate, size=9).pack(side="left", padx=(7,18))
        _label(foot, "Status:", size=10, fg=TEXT_2).pack(side="left")
        _value_label(foot, textvariable=self.modern_freed_output_status, size=9, fg=GREEN).pack(side="left", padx=7)
        return card

    def _modern_toggle_freed_output(self):
        try:
            new = str(self._freed_enabled_var.get()).upper() != "ON"
            self._freed_enabled_var.set("ON" if new else "OFF")
            self._modern_refresh_freed_toggle_buttons()
        except Exception:
            pass

    def _modern_refresh_freed_toggle_buttons(self):
        try:
            i_on = str(self._freed_input_enabled_var.get()).upper() == "ON"
            o_on = str(self._freed_enabled_var.get()).upper() == "ON"
            self.modern_freed_input_toggle.configure(text="ON" if i_on else "OFF")
            self.modern_freed_output_toggle.configure(text="ON" if o_on else "OFF")
            _set_selected(self.modern_freed_input_toggle, i_on)
            _set_selected(self.modern_freed_output_toggle, o_on)
        except Exception:
            pass

    def _build_geometry_card(self, parent):
        card = _panel(parent)
        _free_d_section_header(card, "GEOMETRY")
        _label(card, "Cable Geometry Points", size=9, fg=TEXT_2).grid(row=1, column=0, columnspan=4, sticky="w", padx=10, pady=(0,4))
        for c, text in enumerate(["", "X (m)", "Y (m)", "Z (m)"]):
            _label(card, text, size=9, fg=TEXT_2, anchor="center").grid(row=2, column=c, sticky="ew", padx=2, pady=2)
        for i, row in enumerate(self._freed_point_vars[:5]):
            rr = i+3
            label = "P1 (Near)" if i==0 else "P5 (Far)" if i==4 else f"P{i+1}"
            _label(card, label, size=9, fg=TEXT_2).grid(row=rr, column=0, sticky="w", padx=(10,4), pady=1)
            _entry(card, row["x"], width=6, justify="center", size=9).grid(row=rr, column=1, sticky="ew", padx=2, pady=1, ipady=1)
            _entry(card, row["y"], width=6, justify="center", size=9).grid(row=rr, column=2, sticky="ew", padx=2, pady=1, ipady=1)
            if i in (0,4):
                _entry(card, row["z"], width=6, justify="center", size=9).grid(row=rr, column=3, sticky="ew", padx=2, pady=1, ipady=1)
            else:
                _value_label(card, "—", size=9).grid(row=rr, column=3, sticky="ew", padx=2, pady=1)
        _separator(card).grid(row=8, column=0, columnspan=4, sticky="ew", padx=10, pady=(7,5))
        _label(card, "Weights & Tension", size=9, fg=TEXT_2).grid(row=9, column=0, columnspan=4, sticky="w", padx=10, pady=(0,3))

        self.modern_weight_unit = tk_mod.StringVar(value=str(getattr(self,"modern_saved_weight_unit","kg")))
        self.modern_cable_unit = tk_mod.StringVar(value=str(getattr(self,"modern_saved_cable_unit","kg/100m")))
        self.modern_tension_unit = tk_mod.StringVar(value=str(getattr(self,"modern_saved_tension_unit","kg")))
        self.modern_static_weight = tk_mod.StringVar(value=f"{_safe_float(self._freed_skate_weight_var.get(),25.0):.2f}")
        self.modern_cable_weight = tk_mod.StringVar(value=f"{_safe_float(self._freed_weight_per_100m_var.get(),4.5):.2f}")
        self.modern_tension = tk_mod.StringVar(value=f"{_safe_float(self._freed_tension_var.get(),100.0):.2f}")
        rows = [
            ("Static Weight:", self.modern_static_weight, self.modern_weight_unit, ["kg","lbs"]),
            ("Cable Weight:", self.modern_cable_weight, self.modern_cable_unit, ["kg/100m","lbs/100m"]),
            ("Cable Tension:", self.modern_tension, self.modern_tension_unit, ["kg","lbs"]),
        ]
        for j,(lab,v,u,opts) in enumerate(rows,start=10):
            _label(card, lab, size=9, fg=TEXT_2).grid(row=j, column=0, sticky="e", padx=(8,4), pady=2)
            ent=_entry(card,v,width=8,justify="center",size=9); ent.grid(row=j,column=1,columnspan=2,sticky="ew",padx=2,pady=2,ipady=1)
            cb=ttk_mod.Combobox(card,textvariable=u,values=opts,state="readonly",style="HV.TCombobox",width=8); cb.grid(row=j,column=3,sticky="ew",padx=(2,8),pady=2)
            ent.bind("<FocusOut>", lambda _e: self._modern_commit_weight_units())
            ent.bind("<Return>", lambda _e: self._modern_commit_weight_units())
            cb.bind("<<ComboboxSelected>>", lambda _e: self._modern_weight_unit_changed())
        _label(card, "Highline Mode:", size=9, fg=TEXT_2).grid(row=13, column=0, sticky="e", padx=(8,4), pady=(4,7))
        ttk_mod.Combobox(card, textvariable=self._freed_highline_mode_var, values=["Single Highline","Dual Highline"], state="readonly", style="HV.TCombobox", width=14).grid(row=13,column=1,columnspan=3,sticky="ew",padx=(2,8),pady=(4,7))
        return card

    def _modern_weight_unit_changed(self):
        # Preserve underlying kilograms while re-rendering visible values in selected units.
        try:
            kg = _safe_float(self._freed_skate_weight_var.get())
            cw = _safe_float(self._freed_weight_per_100m_var.get())
            tn = _safe_float(self._freed_tension_var.get())
            self.modern_static_weight.set(f"{kg*(2.2046226218 if self.modern_weight_unit.get()=='lbs' else 1):.2f}")
            self.modern_cable_weight.set(f"{cw*(2.2046226218 if self.modern_cable_unit.get().startswith('lbs') else 1):.2f}")
            self.modern_tension.set(f"{tn*(2.2046226218 if self.modern_tension_unit.get()=='lbs' else 1):.2f}")
        except Exception:
            pass

    def _modern_commit_weight_units(self):
        try:
            sw = max(0.0, float(self.modern_static_weight.get()))
            cw = max(0.0, float(self.modern_cable_weight.get()))
            tn = max(0.1, float(self.modern_tension.get()))
            if self.modern_weight_unit.get() == "lbs": sw /= 2.2046226218
            if self.modern_cable_unit.get().startswith("lbs"): cw /= 2.2046226218
            if self.modern_tension_unit.get() == "lbs": tn /= 2.2046226218
            self._freed_skate_weight_var.set(f"{sw:.3f}")
            self._freed_weight_per_100m_var.set(f"{cw:.3f}")
            self._freed_tension_var.set(f"{tn:.3f}")
            self._modern_weight_unit_changed()
        except Exception:
            self._modern_weight_unit_changed()

    def _build_lens_card(self, parent):
        card = _panel(parent)
        _free_d_section_header(card, "LENS CALIBRATION")
        for c in range(4):
            card.columnconfigure(c, weight=1 if c in (1,3) else 0)
        _label(card,"Data Type:",size=9,fg=TEXT_2).grid(row=1,column=0,sticky="e",padx=(8,4),pady=2)
        ttk_mod.Combobox(card,textvariable=self._freed_lens_type_var,values=["i16","u16","i24","u24"],state="readonly",style="HV.TCombobox",width=7).grid(row=1,column=1,sticky="ew",padx=2,pady=2)
        _label(card,"Data Scale:",size=9,fg=TEXT_2).grid(row=1,column=2,sticky="e",padx=(8,4),pady=2)
        self.modern_lens_scale = tk_mod.StringVar(value="Full Scale" if str(self._freed_lens_scale_var.get()).lower().startswith("full") else self._freed_lens_scale_var.get())
        scale_cb=ttk_mod.Combobox(card,textvariable=self.modern_lens_scale,values=["Auto","Manual","Full Scale"],state="readonly",style="HV.TCombobox",width=9)
        scale_cb.grid(row=1,column=3,sticky="ew",padx=(2,8),pady=2)
        scale_cb.bind("<<ComboboxSelected>>", lambda _e: self._modern_commit_lens_scale())
        self.modern_wide_fov = tk_mod.StringVar(value=getattr(self,"modern_saved_wide_fov","82.0°"))
        self.modern_tele_fov = tk_mod.StringVar(value=getattr(self,"modern_saved_tele_fov","4.85°"))
        _label(card,"Wide FOV:",size=9,fg=TEXT_2).grid(row=2,column=0,sticky="e",padx=(8,4),pady=2)
        _entry(card,self.modern_wide_fov,width=7,justify="center",size=9).grid(row=2,column=1,sticky="ew",padx=2,pady=2,ipady=1)
        _label(card,"Tele FOV:",size=9,fg=TEXT_2).grid(row=2,column=2,sticky="e",padx=(8,4),pady=2)
        _entry(card,self.modern_tele_fov,width=7,justify="center",size=9).grid(row=2,column=3,sticky="ew",padx=(2,8),pady=2,ipady=1)
        _separator(card).grid(row=3,column=0,columnspan=4,sticky="ew",padx=8,pady=(7,4))
        _label(card,"LIVE LENS VALUES",size=9,fg=TEXT_2).grid(row=4,column=0,columnspan=4,sticky="w",padx=8,pady=(0,4))
        self.modern_zoom_live = tk_mod.StringVar(value="--")
        self.modern_focus_live = tk_mod.StringVar(value="--")
        _label(card,"Zoom:",size=9,fg=TEXT_2).grid(row=5,column=0,sticky="e",padx=(8,4),pady=2)
        _value_label(card,textvariable=self.modern_zoom_live,size=9).grid(row=5,column=1,sticky="ew",padx=2,pady=2)
        _label(card,"Focus:",size=9,fg=TEXT_2).grid(row=5,column=2,sticky="e",padx=(8,4),pady=2)
        _value_label(card,textvariable=self.modern_focus_live,size=9).grid(row=5,column=3,sticky="ew",padx=(2,8),pady=2)
        _separator(card).grid(row=6,column=0,columnspan=4,sticky="ew",padx=8,pady=(6,4))
        _label(card,"ZOOM (Wide ↔ Tele)",size=9,fg=TEXT_2).grid(row=7,column=0,columnspan=4,sticky="w",padx=8,pady=(0,3))
        _label(card,"Position",size=8,fg=MUTED).grid(row=8,column=0,sticky="w",padx=8)
        _label(card,"Raw Value",size=8,fg=MUTED,anchor="center").grid(row=8,column=1,sticky="ew")
        _label(card,"Decoded",size=8,fg=MUTED,anchor="center").grid(row=8,column=2,sticky="ew")
        _label(card,"Calibrate",size=8,fg=MUTED,anchor="center").grid(row=8,column=3,sticky="ew")
        self.modern_zoom_wide_dec = tk_mod.StringVar(value="0.00 %")
        self.modern_zoom_tele_dec = tk_mod.StringVar(value="100.00 %")
        self.modern_focus_near_dec = tk_mod.StringVar(value="0.00 %")
        self.modern_focus_far_dec = tk_mod.StringVar(value="100.00 %")
        for rr,label,rawvar,decvar,endpoint in (
            (9,"Wide",self._freed_zoom_wide_var,self.modern_zoom_wide_dec,"zoom_wide"),
            (10,"Tele",self._freed_zoom_tele_var,self.modern_zoom_tele_dec,"zoom_tele"),
        ):
            _label(card,label,size=9,fg=TEXT_2).grid(row=rr,column=0,sticky="w",padx=8,pady=1)
            _entry(card,rawvar,width=8,justify="center",size=9).grid(row=rr,column=1,sticky="ew",padx=2,pady=1,ipady=1)
            _value_label(card,textvariable=decvar,size=9).grid(row=rr,column=2,sticky="ew",padx=2,pady=1)
            _button(card,"Cal",lambda ep=endpoint:self._capture_lens_endpoint(ep),compact=True).grid(row=rr,column=3,sticky="ew",padx=(2,8),pady=1)
        _label(card,"FOCUS (Near ↔ Far)",size=9,fg=TEXT_2).grid(row=11,column=0,columnspan=4,sticky="w",padx=8,pady=(7,3))
        for rr,label,rawvar,decvar,endpoint in (
            (12,"Near",self._freed_focus_near_var,self.modern_focus_near_dec,"focus_near"),
            (13,"Far",self._freed_focus_far_var,self.modern_focus_far_dec,"focus_far"),
        ):
            _label(card,label,size=9,fg=TEXT_2).grid(row=rr,column=0,sticky="w",padx=8,pady=1)
            _entry(card,rawvar,width=8,justify="center",size=9).grid(row=rr,column=1,sticky="ew",padx=2,pady=1,ipady=1)
            _value_label(card,textvariable=decvar,size=9).grid(row=rr,column=2,sticky="ew",padx=2,pady=1)
            _button(card,"Cal",lambda ep=endpoint:self._capture_lens_endpoint(ep),compact=True).grid(row=rr,column=3,sticky="ew",padx=(2,8),pady=1)
        return card

    def _modern_commit_lens_scale(self):
        try:
            v = self.modern_lens_scale.get()
            self._freed_lens_scale_var.set("Full scale" if v == "Full Scale" else v)
        except Exception:
            pass

    def _draw_freed_geometry(self, canvas, side=False):
        try:
            canvas.delete("all")
            w=max(300,canvas.winfo_width()); h=max(120,canvas.winfo_height())
            left=65; right=w-65; top=28; bottom=h-20
            pts=[]
            for i,row in enumerate(self._freed_point_vars[:5]):
                x=_safe_float(row["x"].get(), i*25)
                y=_safe_float(row["y"].get(), 0)
                z=_safe_float(row["z"].get(),0) if i in (0,4) else None
                pts.append((x,y,z))
            xs=[p[0] for p in pts] or [0,100]
            xmin=min(xs); xmax=max(xs); span=max(0.1,xmax-xmin)
            def mx(x): return left+(x-xmin)/span*(right-left)
            if side:
                ys=[p[1] for p in pts]
                ymin=min(ys); ymax=max(ys); yr=max(1.0,ymax-ymin)
                def my(y): return top+18+(ymax-y)/yr*(h-top-50)
            else:
                z0=pts[0][2] or 0; z1=pts[-1][2] or 0
                zr=max(1.0,abs(z1-z0),abs(z0),abs(z1))
                def myz(x):
                    t=(x-xmin)/span
                    z=z0+(z1-z0)*t
                    return (top+h-20)/2 - z/zr*(h*0.22)
            _tower(canvas,35,top+25,0.72); _tower(canvas,w-35,top+25,0.72)
            canvas.create_text(35,top+7,text="NEAR LIMIT",fill=TEXT_2,font=_font(8,"bold"),anchor="n")
            canvas.create_text(w-35,top+7,text="FAR LIMIT",fill=TEXT_2,font=_font(8,"bold"),anchor="n")
            # FOV wedges at ends, matching locked Free-D reference, drawn behind cable/points.
            ymid=(top+bottom)/2
            canvas.create_polygon(left-2,ymid-20,left+72,ymid-3,left+72,ymid+3,left-2,ymid+20,fill="#3a4044",outline="#62696d")
            canvas.create_polygon(right+2,ymid-20,right-72,ymid-3,right-72,ymid+3,right+2,ymid+20,fill="#3a4044",outline="#62696d")
            coords=[]
            for i,p in enumerate(pts):
                x=mx(p[0]); y=my(p[1]) if side else myz(p[0]); coords.extend((x,y))
            if len(coords)>=4: canvas.create_line(*coords,fill="#cfd2d3",width=1,smooth=side)
            for i,p in enumerate(pts):
                x=mx(p[0]); y=my(p[1]) if side else myz(p[0])
                canvas.create_oval(x-4,y-4,x+4,y+4,fill=WHITE,outline=WHITE)
                canvas.create_text(x,y+16,text=f"P{i+1}",fill=TEXT_2,font=_font(9))
        except Exception:
            pass

    def _build_freed_page(self, parent):
        parent.rowconfigure(0, weight=3)
        parent.rowconfigure(1, weight=2)
        parent.columnconfigure(0, weight=1)
        top=tk_mod.Frame(parent,bg=BG)
        top.grid(row=0,column=0,sticky="nsew",pady=(0,4))
        top.grid_propagate(False)
        self.modern_freed_input_card=_build_freed_input_card(self,top); self.modern_freed_input_card.place(relx=0.00,rely=0,relwidth=0.25,relheight=1,width=-4)
        self.modern_freed_output_card=_build_freed_output_card(self,top); self.modern_freed_output_card.place(relx=0.25,rely=0,relwidth=0.25,relheight=1,x=4,width=-8)
        self.modern_geometry_card=_build_geometry_card(self,top); self.modern_geometry_card.place(relx=0.50,rely=0,relwidth=0.25,relheight=1,x=4,width=-8)
        self.modern_lens_card=_build_lens_card(self,top); self.modern_lens_card.place(relx=0.75,rely=0,relwidth=0.25,relheight=1,x=4,width=-4)
        bottom=tk_mod.Frame(parent,bg=BG)
        bottom.grid(row=1,column=0,sticky="nsew",pady=(4,0))
        bottom.grid_propagate(False)
        for col,(title,side) in enumerate((("Top View  X (Tracking) / Z (Offset)",False),("Side View  X (Tracking) / Y (Sag)",True))):
            card=_panel(bottom); card.place(relx=0.0 if col==0 else 0.5,rely=0,relwidth=0.5,relheight=1,x=0 if col==0 else 4,width=-4 if col==0 else -4); card.rowconfigure(1,weight=1); card.columnconfigure(0,weight=1)
            _label(card,title,size=12,weight="bold").grid(row=0,column=0,sticky="w",padx=14,pady=(8,0))
            cv=tk_mod.Canvas(card,bg=PANEL,highlightthickness=0); cv.grid(row=1,column=0,sticky="nsew",padx=7,pady=(0,6)); cv.bind("<Configure>",lambda _e,c=cv,s=side:_draw_freed_geometry(self,c,s))
            if side:self.modern_freed_side_canvas=cv
            else:self.modern_freed_top_canvas=cv

    def _modern_freed_apply(self):
        try:
            self._modern_commit_weight_units()
            self._modern_commit_lens_scale()
            self.modern_saved_wide_fov=self.modern_wide_fov.get(); self.modern_saved_tele_fov=self.modern_tele_fov.get()
            self._save_freed_tab_settings()
            self._modern_refresh_freed_toggle_buttons()
            self._modern_redraw_all()
        except Exception as exc:
            messagebox.showerror("Free-D", f"Apply failed:\n{exc}")

    def _modern_freed_reset(self):
        try:
            self._revert_freed_tab_settings()
            self._modern_weight_unit_changed()
            self.modern_lens_scale.set("Full Scale" if str(self._freed_lens_scale_var.get()).lower().startswith("full") else self._freed_lens_scale_var.get())
            self._modern_refresh_freed_toggle_buttons()
            self._modern_redraw_all()
        except Exception as exc:
            messagebox.showerror("Free-D", f"Reset failed:\n{exc}")

    def _build_setup_page(self, parent):
        # Interim functional page: same locked shell/theme, legacy settings preserved.
        parent.columnconfigure(0,weight=1); parent.columnconfigure(1,weight=1)
        parent.rowconfigure(0,weight=1); parent.rowconfigure(1,weight=1)
        cards=[]
        for r,c,title in ((0,0,"CONTROLLER"),(0,1,"WINCH"),(1,0,"MOTION PROFILES"),(1,1,"ACTIONS / STATUS")):
            card=_panel(parent); card.grid(row=r,column=c,sticky="nsew",padx=(0,4) if c==0 else (4,0),pady=(0,4) if r==0 else (4,0)); card.columnconfigure(1,weight=1)
            _label(card,title,size=15,fg=GREEN,weight="bold").grid(row=0,column=0,columnspan=3,sticky="w",padx=18,pady=(14,12)); cards.append(card)
        ctrl,winch,motion,actions=cards
        _label(ctrl,"CTRL IP",size=11,fg=TEXT_2).grid(row=1,column=0,sticky="w",padx=18,pady=6); _entry(ctrl,self._tab_ctrl_ip,width=18).grid(row=1,column=1,sticky="ew",padx=(8,18),pady=6,ipady=2)
        _label(ctrl,"Direction",size=11,fg=TEXT_2).grid(row=2,column=0,sticky="w",padx=18,pady=6); ttk_mod.Combobox(ctrl,textvariable=self._tab_ctrl_dir,values=["Normal","Inverted"],state="readonly",style="HV.TCombobox").grid(row=2,column=1,sticky="ew",padx=(8,18),pady=6)
        _button(ctrl,"Apply Controller",self._save_controller_tab_settings).grid(row=3,column=0,columnspan=2,sticky="ew",padx=18,pady=(14,6))
        _label(winch,"W1P IP",size=11,fg=TEXT_2).grid(row=1,column=0,sticky="w",padx=18,pady=6); _entry(winch,self._tab_winch_ip,width=18).grid(row=1,column=1,sticky="ew",padx=(8,18),pady=6,ipady=2)
        _label(winch,"Direction",size=11,fg=TEXT_2).grid(row=2,column=0,sticky="w",padx=18,pady=6); ttk_mod.Combobox(winch,textvariable=self._tab_winch_dir,values=["Normal","Inverted"],state="readonly",style="HV.TCombobox").grid(row=2,column=1,sticky="ew",padx=(8,18),pady=6)
        _label(winch,"CMD Units Per M",size=11,fg=TEXT_2).grid(row=3,column=0,sticky="w",padx=18,pady=6); _entry(winch,self._tab_winch_units_var,width=18).grid(row=3,column=1,sticky="ew",padx=(8,18),pady=6,ipady=2)
        _button(winch,"Apply Winch",self._save_winch_tab_settings).grid(row=4,column=0,columnspan=2,sticky="ew",padx=18,pady=(14,6))
        for i in range(2):
            _label(motion,f"Mode {i+1}",size=11,fg=TEXT_2).grid(row=i+1,column=0,sticky="w",padx=18,pady=6)
            v=self.drive_mode_name_vars[i] if i<len(getattr(self,"drive_mode_name_vars",[])) else tk_mod.StringVar(value=f"Mode {i+1}")
            _entry(motion,v,width=16).grid(row=i+1,column=1,sticky="ew",padx=(8,18),pady=6,ipady=2)
        _label(motion,"Max Speed / Accel / Decel remain the proven values from the previous build.",size=10,fg=MUTED,wraplength=430,justify="left").grid(row=4,column=0,columnspan=2,sticky="w",padx=18,pady=10)
        self.modern_setup_status=tk_mod.StringVar(value="Functional interim Setup page — visual redesign not yet locked.")
        _label(actions,textvariable=self.modern_setup_status,size=11,fg=TEXT_2,wraplength=430,justify="left").grid(row=1,column=0,columnspan=2,sticky="nw",padx=18,pady=8)
        _button(actions,"Save Config",self.on_save_config).grid(row=2,column=0,columnspan=2,sticky="ew",padx=18,pady=5)
        _button(actions,"Load Config",self.on_load_config_dialog).grid(row=3,column=0,columnspan=2,sticky="ew",padx=18,pady=5)

    def _build_log_page(self, parent):
        parent.columnconfigure(0,weight=1); parent.rowconfigure(1,weight=1)
        head=tk_mod.Frame(parent,bg=BG); head.grid(row=0,column=0,sticky="ew",pady=(0,6)); head.columnconfigure(0,weight=1)
        _label(head,"LIVE LOG",size=15,fg=GREEN,weight="bold",bg=BG).grid(row=0,column=0,sticky="w")
        _button(head,"Save Log",self._save_log_tab,compact=True).grid(row=0,column=1,padx=4)
        _button(head,"Clear Log",self._clear_log_tab,compact=True).grid(row=0,column=2,padx=4)
        card=_panel(parent); card.grid(row=1,column=0,sticky="nsew"); card.columnconfigure(0,weight=1); card.rowconfigure(0,weight=1)
        self.modern_log_text=tk_mod.Text(card,bg="#070a0c",fg="#d6d8da",insertbackground=TEXT,font=("Menlo",10),relief="flat",bd=0,wrap="none",selectbackground=GREEN_SOFT)
        self.modern_log_text.grid(row=0,column=0,sticky="nsew",padx=(8,0),pady=8)
        sb=ttk_mod.Scrollbar(card,orient="vertical",command=self.modern_log_text.yview,style="HV.Vertical.TScrollbar"); sb.grid(row=0,column=1,sticky="ns",pady=8,padx=(0,8)); self.modern_log_text.configure(yscrollcommand=sb.set,state="disabled")

    def _modern_open_limit_calibration(self):
        try:
            if getattr(self,"modern_calibration_overlay",None) is not None and self.modern_calibration_overlay.winfo_exists():
                self.modern_calibration_overlay.lift(); return
        except Exception:
            pass
        try:
            self._begin_limit_calibration()
        except Exception:
            try:self._enter_system_calibration_mode()
            except Exception:pass
        overlay=_panel(self.modern_root)
        overlay.place(relx=0.5,rely=0.52,anchor="center",relwidth=0.46,relheight=0.55)
        overlay.lift(); self.modern_calibration_overlay=overlay; overlay.columnconfigure(0,weight=1); overlay.rowconfigure(3,weight=1)
        head=tk_mod.Frame(overlay,bg=PANEL); head.grid(row=0,column=0,sticky="ew",padx=18,pady=(13,5)); head.columnconfigure(0,weight=1)
        _label(head,"Limit Calibration",size=17,weight="bold").grid(row=0,column=0,sticky="w")
        _button(head,"×",self._modern_cancel_limit_calibration,compact=True,width=2).grid(row=0,column=1,sticky="e")
        steps=tk_mod.Frame(overlay,bg=PANEL); steps.grid(row=1,column=0,sticky="ew",padx=38,pady=(4,6));
        for i in range(4):steps.columnconfigure(i,weight=1)
        self.modern_cal_step_canvases=[]
        for i,name in enumerate(("Set Near","Set Far","Set Ref","Done")):
            c=tk_mod.Canvas(steps,width=90,height=54,bg=PANEL,highlightthickness=0); c.grid(row=0,column=i,sticky="ew"); self.modern_cal_step_canvases.append((c,name))
        _separator(overlay).grid(row=2,column=0,sticky="ew",padx=18,pady=2)
        body=tk_mod.Frame(overlay,bg=PANEL); body.grid(row=3,column=0,sticky="nsew",padx=26,pady=10); body.columnconfigure(0,weight=1); body.columnconfigure(1,weight=1); body.rowconfigure(0,weight=1)
        self.modern_cal_illustration=tk_mod.Canvas(body,bg=PANEL,highlightthickness=0); self.modern_cal_illustration.grid(row=0,column=0,sticky="nsew",padx=(0,15))
        tk_mod.Frame(body,bg=BORDER_SOFT,width=1).grid(row=0,column=1,sticky="nsw")
        text=tk_mod.Frame(body,bg=PANEL); text.grid(row=0,column=1,sticky="nsew",padx=(20,0)); text.columnconfigure(0,weight=1)
        self.modern_cal_title=tk_mod.StringVar(value=""); self.modern_cal_desc=tk_mod.StringVar(value="")
        _label(text,textvariable=self.modern_cal_title,size=16,weight="bold").grid(row=0,column=0,sticky="w",pady=(5,8))
        _label(text,textvariable=self.modern_cal_desc,size=11,fg=TEXT_2,wraplength=330,justify="left").grid(row=1,column=0,sticky="nw")
        info=_panel(text); info.grid(row=2,column=0,sticky="ew",pady=(18,0)); _label(info,"ⓘ   Ensure the skate is stable at the selected position before saving.",size=10,fg=MUTED,wraplength=310,justify="left").pack(fill="x",padx=12,pady=10)
        foot=tk_mod.Frame(overlay,bg=PANEL); foot.grid(row=4,column=0,sticky="ew",padx=18,pady=(2,16)); foot.columnconfigure(1,weight=1)
        _button(foot,"Cancel",self._modern_cancel_limit_calibration,width=10).grid(row=0,column=0,sticky="w")
        self.modern_cal_back=_button(foot,"Back",self._modern_limit_cal_back,width=10); self.modern_cal_back.grid(row=0,column=2,sticky="e",padx=(0,10))
        self.modern_cal_next_var=tk_mod.StringVar(value="Save Near & Continue")
        self.modern_cal_next=_button(foot,var=self.modern_cal_next_var,command=self._modern_limit_cal_next,width=18); self.modern_cal_next.grid(row=0,column=3,sticky="e")
        self.modern_cal_step=0; self._modern_render_limit_cal_step()

    def _modern_render_limit_cal_step(self):
        step=int(getattr(self,"modern_cal_step",0)); names=["Set Near","Set Far","Set Ref","Done"]
        for i,(c,name) in enumerate(self.modern_cal_step_canvases):
            c.delete("all"); w=max(80,c.winfo_width()); active=i<=step; col=GREEN if i==step else TEXT_2
            if i<3: c.create_line(w/2,15,w,15,fill=GREEN if i<step else BORDER,width=1)
            c.create_oval(w/2-12,3,w/2+12,27,fill=GREEN if i==step else PANEL,outline=GREEN if active else BORDER,width=1)
            c.create_text(w/2,15,text=str(i+1),fill=BG if i==step else TEXT_2,font=_font(10,"bold"))
            c.create_text(w/2,42,text=name,fill=TEXT_2,font=_font(9))
        titles=["Set Near Limit","Set Far Limit","Set Reference Point","Calibration Complete"]
        descs=[
            "Move the skate to the near limit position, then press Save Near & Continue.",
            "Move the skate to the far limit position, then press Save Far & Continue.",
            "Move the skate to the known reference position, then press Save Ref & Continue.",
            "Near Limit, Far Limit and Reference Point have been saved."
        ]
        self.modern_cal_title.set(titles[step]); self.modern_cal_desc.set(descs[step])
        self.modern_cal_back.configure(state="normal" if step>0 and step<3 else "disabled")
        labels=["Save Near & Continue","Save Far & Continue","Save Ref & Continue","Done"]
        self.modern_cal_next_var.set(labels[step])
        c=self.modern_cal_illustration; c.delete("all"); w=max(200,c.winfo_width()); h=max(140,c.winfo_height());
        if step==3:
            c.create_text(w/2,h/2,text="✓",fill=GREEN,font=_font(60,"bold")); c.create_text(w/2,h/2+52,text="DONE",fill=TEXT_2,font=_font(12,"bold")); return
        _tower(c,48,h/2-35,0.9); _camera_icon(c,w-55,h/2+15); c.create_text(48,h/2+45,text="NEAR\nLIMIT" if step==0 else "FAR\nLIMIT" if step==1 else "REF",fill=TEXT_2,font=_font(10,"bold"),justify="center")
        c.create_text(w-55,h/2+47,text="SKATE",fill=TEXT_2,font=_font(10,"bold")); c.create_line(78,h/2, w-86,h/2,fill=GREEN,dash=(5,4),arrow="last")

    def _modern_limit_cal_next(self):
        step=int(getattr(self,"modern_cal_step",0))
        if step>=3:
            self._modern_finish_limit_calibration(); return
        try:
            lp=[self.state.near_limit,self.state.far_limit,self.state.ref_point][step]
            pos=getattr(self.state,"pos_m",None)
            if pos is None: pos=(self.state.near_limit.position_m or 0.0)+self.state.total_length_m/2
            self._set_system_calibration_point(lp,step,pos)
            self._update_limits_ui(); self._sync_limits_to_winch(); self._save_config()
            if step==2:
                try:self._exit_not_calibrated_mode()
                except Exception:pass
            self.modern_cal_step=step+1; self._modern_render_limit_cal_step(); self._modern_redraw_all()
        except Exception as exc:
            messagebox.showerror("Limit Calibration",str(exc))

    def _modern_limit_cal_back(self):
        if getattr(self,"modern_cal_step",0)>0:
            self.modern_cal_step-=1; self._modern_render_limit_cal_step()

    def _modern_finish_limit_calibration(self):
        try:self._exit_system_calibration_mode()
        except Exception:pass
        try:self.modern_calibration_overlay.destroy()
        except Exception:pass
        self.modern_calibration_overlay=None; self._modern_redraw_all()

    def _modern_cancel_limit_calibration(self):
        try:self._cancel_active_calibration_restore_config()
        except Exception:
            try:self._exit_system_calibration_mode()
            except Exception:pass
        try:self.modern_calibration_overlay.destroy()
        except Exception:pass
        self.modern_calibration_overlay=None; self._modern_redraw_all()

    def _modern_refresh_preset_buttons(self):
        try:
            now=time.time(); active=getattr(self,"_preset_confirm",None)
            if isinstance(active,dict) and now>float(active.get("until",0) or 0): self._preset_confirm=None; active=None
            for i in range(10):
                sv = self.modern_preset_save_vars[i] if i < len(getattr(self,"modern_preset_save_vars",[])) else None
                rv = self.modern_preset_recall_vars[i] if i < len(getattr(self,"modern_preset_recall_vars",[])) else None
                if sv is not None: sv.set(str(active.get("label")) if isinstance(active,dict) and active.get("idx")==i and active.get("kind")=="set" else "Save")
                if rv is not None: rv.set(str(active.get("label")) if isinstance(active,dict) and active.get("idx")==i and active.get("kind")=="goto" else "Recall")
                if i < len(getattr(self,"modern_preset_eye_buttons",[])) and self.modern_preset_eye_buttons[i] is not None:
                    vis=bool(self.preset_visible[i]) if i<len(self.preset_visible) else False
                    self.modern_preset_eye_buttons[i].configure(text="◉" if vis else "◎",fg=GREEN if vis else TEXT)
        except Exception:
            pass

    def _modern_refresh_limit_buttons(self):
        try:
            now=time.time(); active=getattr(self,"_limit_confirm",None)
            if isinstance(active,dict) and now>float(active.get("until",0) or 0): self._limit_confirm=None; active=None
            defaults={"set":"Save","goto":"Recall","slip":"Slip"}
            for (key,kind),var in getattr(self,"modern_limit_button_vars",{}).items():
                txt=defaults.get(kind,kind.title())
                if isinstance(active,dict) and active.get("key")==key and active.get("kind")==kind: txt=str(active.get("label","Confirm?"))
                var.set(txt)
        except Exception:pass

    def _refresh_preset_confirm_buttons_modern(self):
        legacy_preset_refresh(self)
        try:self._modern_refresh_preset_buttons()
        except Exception:pass

    def _refresh_limit_confirm_buttons_modern(self):
        legacy_limit_refresh(self)
        try:self._modern_refresh_limit_buttons()
        except Exception:pass

    def _modern_redraw_all(self):
        try:
            if hasattr(self,"modern_run_top_canvas"):_draw_run_diagram(self,self.modern_run_top_canvas,False)
            if hasattr(self,"modern_run_side_canvas"):_draw_run_diagram(self,self.modern_run_side_canvas,True)
            if hasattr(self,"modern_freed_top_canvas"):_draw_freed_geometry(self,self.modern_freed_top_canvas,False)
            if hasattr(self,"modern_freed_side_canvas"):_draw_freed_geometry(self,self.modern_freed_side_canvas,True)
        except Exception:pass

    def _modern_refresh(self):
        try:
            # time / uptime
            self.modern_time_var.set(time.strftime("%Y-%m-%d  %H:%M:%S"))
            up=max(0,int(time.time()-getattr(self,"modern_start_time",time.time()))); hh=up//3600; mm=(up%3600)//60; ss=up%60
            self.modern_uptime_var.set(f"{hh:02d}:{mm:02d}:{ss:02d}")
            cs=G["get_controller_status"]()
            ctrl_connected=bool(cs.get("connected",False)); ctrl_ip=str(cs.get("expected_ip") or getattr(self,"controller_ip_ref","172.20.1.101") or "172.20.1.101")
            self.modern_ctrl_sub.set(f"{'Connected' if ctrl_connected else 'Disconnected'}   {ctrl_ip}"); _dot(self.modern_ctrl_dot,GREEN if ctrl_connected else RED)
            w_connected=bool(getattr(getattr(self,"arduino_status",None),"connected",False)); wip=str(getattr(self,"winch_host","172.20.1.102")); self.modern_w1p_sub.set(f"{'Connected' if w_connected else 'Disconnected'}   {wip}"); _dot(self.modern_w1p_dot,GREEN if w_connected else RED)
            in_fps=_safe_float(getattr(self,"freed_in_fps",0.0)); f_active=bool(getattr(self,"freed_input_enabled",False)) and bool(self._freed_input_recent())
            self.modern_freed_sub.set(f"{'Active' if f_active else 'Inactive'}   {in_fps:.3f} fps"); _dot(self.modern_freed_dot,GREEN if f_active else (AMBER if getattr(self,"freed_input_enabled",False) else RED))
            # system banner from backend safety summary
            try:
                red,red_text,_=self._safety_status_summary()
            except Exception:red,red_text=False,""
            if red:
                text=red_text.upper(); bg="#351516"; border="#7d2b2e"; fg="#ff6262"
            elif bool(getattr(self,"battery_change_mode",False)):
                text="BATTERY CHANGE"; bg="#332910"; border="#7e6625"; fg="#f1bd47"
            elif bool(getattr(self,"system_calibration_mode",False)) or bool(getattr(self,"winch_calibration_mode",False)):
                text="CALIBRATION"; bg="#332910"; border="#7e6625"; fg="#f1bd47"
            elif bool(getattr(self,"not_calibrated_mode",False)):
                text="UN-CALIBRATED"; bg="#332910"; border="#7e6625"; fg="#f1bd47"
            else:
                text="SYSTEM READY"; bg="#102b18"; border="#2d6c36"; fg=GREEN
            self.modern_banner.configure(bg=bg,highlightbackground=border)
            for child in self.modern_banner.winfo_children():
                try: child.configure(bg=bg,fg=fg)
                except Exception:pass
            self.modern_banner_text.set(text)
            # run values
            mode_idx=int(getattr(self,"active_drive_mode",0) or 0); mode_name=str(self.drive_modes[mode_idx].get("name",f"Mode {mode_idx+1}")) if mode_idx<len(self.drive_modes) else f"Mode {mode_idx+1}"
            self.modern_drive_mode_var.set(mode_name); self.modern_accel_var.set(self._display_accel_type()); self.modern_batt_var.set("On" if getattr(self,"battery_change_mode",False) else "Off")
            sp=_safe_float(getattr(self,"display_speed_mps",getattr(self,"current_speed_mps",0.0))); mx=_safe_float(getattr(self,"max_speed_mps",0.0)); self.modern_speed_mps.set(f"{sp:.1f}"); self.modern_speed_kmh.set(f"{sp*3.6:.1f}"); self.modern_max_mps.set(f"{mx:.1f}"); self.modern_max_kmh.set(f"{mx*3.6:.1f}")
            pos=_safe_float(self._current_position_relative_m()); span=max(0.0,_safe_float(getattr(self.state,"total_length_m",0.0))); self.modern_pos_var.set(f"{pos:.2f}"); self.modern_to_near.set(f"{max(0,pos):.2f} m"); self.modern_to_far.set(f"{max(0,span-pos):.2f} m")
            # sync preset visible values unless field has focus
            for i in range(10):
                if i<len(getattr(self,"modern_preset_name_vars",[])) and self.modern_preset_name_vars[i] is not None:
                    try:
                        focus=self.root.focus_get(); active_var=str(focus.cget("textvariable")) if focus is not None and focus.winfo_class()=="Entry" else ""
                    except Exception: active_var=""
                    if str(self.modern_preset_name_vars[i])!=active_var:
                        name=self.preset_names[i] if i<len(self.preset_names) else f"P{i+1}"; self.modern_preset_name_vars[i].set(name)
                    if str(self.modern_preset_dist_vars[i])!=active_var:
                        p=self.preset_positions[i] if i<len(self.preset_positions) else None; self.modern_preset_dist_vars[i].set("" if p is None else f"{float(p):.2f}")
            self._modern_refresh_preset_buttons(); self._modern_refresh_limit_buttons(); self._modern_refresh_system_controls(); self._modern_refresh_freed_toggle_buttons()
            self.modern_freed_input_rate.set(f"{in_fps:.3f} fps"); self.modern_freed_input_status.set("Locked" if f_active else ("Waiting" if getattr(self,"freed_input_enabled",False) else "Off"))
            out_fps=_safe_float(getattr(self,"freed_out_fps",0.0)); out_on=bool(getattr(self,"freed_output_enabled",False)); self.modern_freed_output_rate.set(f"{out_fps:.3f} fps"); self.modern_freed_output_status.set("Streaming" if out_on else "Stopped")
            zoom=self._current_lens_value("zoom"); focusv=self._current_lens_value("focus"); zn=self._lens_norm_for_display("zoom",zoom)*100; fn=self._lens_norm_for_display("focus",focusv)*100; self.modern_zoom_live.set(f"{zoom:.0f} ({zn:.3f}%)"); self.modern_focus_live.set(f"{focusv:.0f} ({fn:.3f}%)")
            # mirror hidden log without stealing APP_LOG_QUEUE
            if hasattr(self,"log_text") and hasattr(self,"modern_log_text"):
                try:
                    text=self.log_text.get("1.0","end-1c"); current=self.modern_log_text.get("1.0","end-1c")
                    if text!=current:
                        self.modern_log_text.configure(state="normal"); self.modern_log_text.delete("1.0","end"); self.modern_log_text.insert("1.0",text); self.modern_log_text.see("end"); self.modern_log_text.configure(state="disabled")
                except Exception:pass
            # redraw live diagrams at modest cadence
            if int(time.time()*5)%2==0:self._modern_redraw_all()
        except Exception:
            pass
        try:self.root.after(200,self._modern_refresh)
        except Exception:pass

    def _modern_build_layout(self):
        self.modern_start_time=time.time()
        _config_style(self)
        outer=self.main_frame
        outer.configure(bg=BG)
        # Build the entire previous UI off-screen. This retains all proven backend
        # variables, callbacks, network state and config behavior without exposing
        # the legacy visuals.
        compat=tk_mod.Frame(outer,bg=BG,width=1,height=1)
        self._legacy_ui_host=compat
        self.main_frame=compat
        legacy_build_layout(self)
        self.main_frame=outer
        # Keep unmanaged: no pack/grid/place = no visible legacy UI.
        for child in outer.winfo_children():
            if child is not compat:
                try:child.destroy()
                except Exception:pass
        # Reset outer geometry.
        for i in range(8):
            try:outer.rowconfigure(i,weight=0,minsize=0)
            except Exception:pass
        outer.columnconfigure(0,weight=1)
        outer.rowconfigure(3,weight=1)
        self.modern_root=tk_mod.Frame(outer,bg=BG)
        self.modern_root.grid(row=0,column=0,rowspan=6,sticky="nsew")
        self.modern_root.columnconfigure(0,weight=1); self.modern_root.rowconfigure(3,weight=1)
        _build_header(self,self.modern_root); _build_banner(self,self.modern_root); _build_nav(self,self.modern_root)
        pages_host=tk_mod.Frame(self.modern_root,bg=BG)
        pages_host.grid(row=3,column=0,sticky="nsew",padx=14); pages_host.columnconfigure(0,weight=1); pages_host.rowconfigure(0,weight=1); pages_host.grid_propagate(False)
        self.modern_pages={}
        for name in ("Run","Setup","Free-D","Log"):
            f=tk_mod.Frame(pages_host,bg=BG); f.grid(row=0,column=0,sticky="nsew"); self.modern_pages[name]=f
        _build_run_page(self,self.modern_pages["Run"]); _build_setup_page(self,self.modern_pages["Setup"]); _build_freed_page(self,self.modern_pages["Free-D"]); _build_log_page(self,self.modern_pages["Log"])
        _build_footer(self,self.modern_root)
        self.modern_page="Run"; _show_page(self,"Run")
        try:
            self.root.configure(bg=BG)
            self.root.minsize(1280,760)
            sw=max(1280,int(self.root.winfo_screenwidth()))
            sh=max(760,int(self.root.winfo_screenheight()))
            self.root.geometry(f"{sw}x{sh}+0+0")
        except Exception:
            pass
        self.root.after(100,self._modern_refresh)

    def _to_config_dict_modern(self):
        cfg = legacy_to_config(self)
        try:
            fd = cfg.setdefault("free_d", {})
            def _deg(v, default):
                try: return float(str(v).replace("°", "").strip())
                except Exception: return float(default)
            fd["lens_wide_fov_deg"] = _deg(getattr(self,"modern_saved_wide_fov",getattr(self,"modern_wide_fov",None).get() if hasattr(self,"modern_wide_fov") else 82.0),82.0)
            fd["lens_tele_fov_deg"] = _deg(getattr(self,"modern_saved_tele_fov",getattr(self,"modern_tele_fov",None).get() if hasattr(self,"modern_tele_fov") else 4.85),4.85)
            fd["weight_unit"] = str(getattr(self,"modern_weight_unit",None).get() if hasattr(self,"modern_weight_unit") else getattr(self,"modern_saved_weight_unit","kg"))
            fd["cable_weight_unit"] = str(getattr(self,"modern_cable_unit",None).get() if hasattr(self,"modern_cable_unit") else getattr(self,"modern_saved_cable_unit","kg/100m"))
            fd["tension_unit"] = str(getattr(self,"modern_tension_unit",None).get() if hasattr(self,"modern_tension_unit") else getattr(self,"modern_saved_tension_unit","kg"))
        except Exception:
            pass
        return cfg

    def _apply_freed_config_modern(self, freed_cfg):
        legacy_apply_freed_config(self, freed_cfg)
        try:
            fd = freed_cfg if isinstance(freed_cfg, dict) else {}
            self.modern_saved_wide_fov = f"{float(fd.get('lens_wide_fov_deg',82.0)):g}°"
            self.modern_saved_tele_fov = f"{float(fd.get('lens_tele_fov_deg',4.85)):g}°"
            self.modern_saved_weight_unit = str(fd.get("weight_unit","kg"))
            self.modern_saved_cable_unit = str(fd.get("cable_weight_unit","kg/100m"))
            self.modern_saved_tension_unit = str(fd.get("tension_unit","kg"))
        except Exception:
            pass

    # install methods
    AppClass._to_config_dict = _to_config_dict_modern
    AppClass._apply_freed_config = _apply_freed_config_modern
    AppClass._build_layout = _modern_build_layout
    AppClass._modern_show_shortcut_tab = _modern_show_shortcut_tab
    AppClass._modern_build_preset_tab = _modern_build_preset_tab
    AppClass._modern_build_limits_tab = _modern_build_limits_tab
    AppClass._modern_build_system_tab = _modern_build_system_tab
    AppClass._modern_commit_preset_name = _modern_commit_preset_name
    AppClass._modern_commit_preset_distance = _modern_commit_preset_distance
    AppClass._modern_sync_ramp_vars = _modern_sync_ramp_vars
    AppClass._modern_commit_ramp = _modern_commit_ramp
    AppClass._modern_set_accel = _modern_set_accel
    AppClass._modern_set_batt = _modern_set_batt
    AppClass._modern_select_drive_mode = _modern_select_drive_mode
    AppClass._modern_commit_mode_name = _modern_commit_mode_name
    AppClass._modern_refresh_system_controls = _modern_refresh_system_controls
    AppClass._modern_start_winch_calibration = _modern_start_winch_calibration
    AppClass._modern_toggle_freed_input = _modern_toggle_freed_input
    AppClass._modern_toggle_freed_output = _modern_toggle_freed_output
    AppClass._modern_refresh_freed_toggle_buttons = _modern_refresh_freed_toggle_buttons
    AppClass._modern_weight_unit_changed = _modern_weight_unit_changed
    AppClass._modern_commit_weight_units = _modern_commit_weight_units
    AppClass._modern_commit_lens_scale = _modern_commit_lens_scale
    AppClass._modern_freed_apply = _modern_freed_apply
    AppClass._modern_freed_reset = _modern_freed_reset
    AppClass._modern_open_limit_calibration = _modern_open_limit_calibration
    AppClass._modern_render_limit_cal_step = _modern_render_limit_cal_step
    AppClass._modern_limit_cal_next = _modern_limit_cal_next
    AppClass._modern_limit_cal_back = _modern_limit_cal_back
    AppClass._modern_finish_limit_calibration = _modern_finish_limit_calibration
    AppClass._modern_cancel_limit_calibration = _modern_cancel_limit_calibration
    AppClass._modern_refresh_preset_buttons = _modern_refresh_preset_buttons
    AppClass._modern_refresh_limit_buttons = _modern_refresh_limit_buttons
    AppClass._modern_redraw_all = _modern_redraw_all
    AppClass._modern_refresh = _modern_refresh
    AppClass._refresh_preset_confirm_buttons = _refresh_preset_confirm_buttons_modern
    AppClass._refresh_limit_confirm_buttons = _refresh_limit_confirm_buttons_modern
