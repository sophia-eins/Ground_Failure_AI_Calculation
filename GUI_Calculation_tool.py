
"""
GUI for calculating bearing capacity failure (Tkinter)
- Executes the existing notebook UNCHANGED
- Replaces terminal inputs with GUI
- Shows print outputs and plots in the GUI

Prerequisites:
  - Python 3.x
  - matplotlib
  - (optional) nbformat not necessary; we read JSON directly

Start:
  python grundbruch_gui.py
"""

import json
import io, os, sys, traceback, contextlib, logging
import traceback
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import tkinter.font as tkfont

# Matplotlib: Embed figures in Tk
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import datetime

# ReportLab for PDF export (optional)

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from PIL import Image as PILImage 
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
except ImportError:
    print("PDF export not available. Please install 'reportlab' and 'Pillow': pip install reportlab Pillow")
    # You could skip the PDF button creation if the import fails


# ------------------------------------------------------------
# Notebook loader (reads code cells unchanged)
# ------------------------------------------------------------
def load_notebook_code_cells(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            nb = json.load(f)
        code_cells = [c for c in nb.get("cells", []) if c.get("cell_type") == "code"]
        sources = ["".join(c.get("source", [])) for c in code_cells]
        return sources
    except Exception as e:
        # Fallback: If a JSON decode error occurs (for example with a .py file), 
        # the entire content is returned as a single code block.
        with open(path, "r", encoding="utf-8") as f:
            source = f.read().strip()
        if source:
            return [source]
        else:
            raise Exception("File empty or invalid: " + str(e))

# ------------------------------------------------------------
# Execution of the notebook cells with patched input() and plt.show()
# ------------------------------------------------------------
# --- at the beginning of the file with the other imports ---

def run_python_file_with_inputs(path, answers):
    """
    Executes a .py file like `python file.py`:
    - __name__ = "__main__" (Main block is executed)
    - input() is served from `answers` (GUI values)
    - print(), stderr, logging are intercepted
    - plt.show() is intercepted (figures collected)
    - sys.exit() is intercepted (GUI stays alive)
    - Working directory = script directory
    """
    path = os.fspath(path)
    ans_iter = iter(list(map(str, answers)))

    stdout_buf, stderr_buf, log_buf = io.StringIO(), io.StringIO(), io.StringIO()
    captured_figs = []

    import builtins as _builtins

    orig_input = _builtins.input
    orig_show  = plt.show
    orig_exit  = sys.exit
    orig_cwd   = os.getcwd()
    orig_argv  = sys.argv[:]

    def fake_input(prompt=""):
        try:
            return next(ans_iter)
        except StopIteration:
            raise RuntimeError(f"Not enough GUI inputs for input(); last prompt: {prompt!r}")

    def fake_show(*args, **kwargs):
        fig = plt.gcf()
        if not getattr(fig, "_gui_internal", False):
            captured_figs.append(fig)

    def fake_exit(code=0):
        raise SystemExit(code)

    # Logging -> Buffer
    handler = logging.StreamHandler(log_buf)
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    try:
        _builtins.input = fake_input
        plt.show = fake_show
        sys.exit = fake_exit

        # like `python path.py`
        os.chdir(os.path.dirname(path) or ".")
        sys.argv = [path]
        globs = {"__name__": "__main__", "__file__": path}

        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            with open(path, "r", encoding="utf-8") as f:
                code = compile(f.read(), path, "exec")
            exec(code, globs, globs)

        # if script leaves figures open without calling show(): collect them
        try:
            from matplotlib._pylab_helpers import Gcf
            for m in Gcf.get_all_fig_managers():
                fig = m.canvas.figure
                if not getattr(fig, "_gui_internal", False) and fig not in captured_figs:
                    captured_figs.append(fig)
        except Exception:
            pass

        out = stdout_buf.getvalue()
        err = stderr_buf.getvalue()
        logs = log_buf.getvalue()
        text = "\n".join(s for s in [out, err, logs] if s).strip()
        return text, captured_figs, None, globs

    except SystemExit as e:
        out = stdout_buf.getvalue()
        err = stderr_buf.getvalue()
        logs = log_buf.getvalue()
        text = "\n".join(s for s in [out, err, logs, f"[SystemExit: {e.code}]"] if s).strip()
        return text, captured_figs, None, globs

    except Exception:
        tb = traceback.format_exc()
        out = stdout_buf.getvalue()
        err = stderr_buf.getvalue()
        logs = log_buf.getvalue()
        text = "\n".join(s for s in [out, err, logs] if s).strip()
        return text, captured_figs, tb, globs

    finally:
        # Restore
        _builtins.input = orig_input
        plt.show = orig_show
        sys.exit = orig_exit
        os.chdir(orig_cwd)
        sys.argv = orig_argv
        try:
            root.removeHandler(handler)
        except Exception:
            pass
        root.setLevel(old_level)

# ------------------------------------------------------------
# GUI
# ------------------------------------------------------------
class GrundbruchGUI(tk.Tk):
    # --- Colors / hatching for the 2D soil sketch ---
    SOIL1_COLOR = "#FFD54F"   # yellow
    SOIL2_COLOR = "#81C784"   # green
    GW_COLOR    = "#1565C0"   # blue
    FOUND_FACE  = "#BDBDBD"   # gray (foundation)
    FOUND_HATCH = "///"       # foundation hatching
    HK_COLOR = "#2E7D32"   # green for horizontal load
    VK_COLOR = "#C62828"   # red for vertical load

    def __init__(self):
        super().__init__()
        self.title("Calculation of bearing capacity failure of a shallow foundation according to EC7")
        self.geometry("1920x1080")

        self.nb_path = tk.StringVar(value=str(Path.cwd() / "src"))
        self.code_cells = None

        self.last_run_data = None  # Placeholder for results

        self._build_ui()

    # Mapping design situation -> Identifier
    DS_NAME_BY_VALUE = {"1": "BS-P", "2": "BS-T", "3": "BS-A/BS-E"}

    # Partial safety factors according to the notebook (adopted unchanged)
    GAMMAS_BY_DS = {
        "BS-P":     {"γ_G": 1.35, "γ_Q": 1.50, "γ_M": 1.00, "γ_φ": 1.00, "γ_c": 1.00, "γ_R": 1.40},
        "BS-T":     {"γ_G": 1.20, "γ_Q": 1.30, "γ_M": 1.00, "γ_φ": 1.00, "γ_c": 1.00, "γ_R": 1.30},
        "BS-A/BS-E":{"γ_G": 1.10, "γ_Q": 1.10, "γ_M": 1.00, "γ_φ": 1.00, "γ_c": 1.00, "γ_R": 1.20},
    }

    def _build_gamma_table(self, parent):
        frame = ttk.LabelFrame(parent, text="Partial safety factors (γ)")
        frame.pack(fill="x", padx=10, pady=12)

        # Fonts for highlighting
        self._font_norm = tkfont.nametofont("TkDefaultFont")
        self._font_bold = self._font_norm.copy()
        self._font_bold.configure(weight="bold")

        cols = ["BS-P", "BS-T", "BS-A/BS-E"]
        rows = ["γ_G", "γ_Q", "γ_M", "γ_φ", "γ_c", "γ_R"]

        # Header
        ttk.Label(frame, text="").grid(row=0, column=0, padx=8, pady=6, sticky="w")
        for j, col in enumerate(cols, start=1):
            ttk.Label(frame, text=col).grid(row=0, column=j, padx=8, pady=6, sticky="w")

        # Create + reference cells
        self.gamma_cells = {}  # (row_key, col_key) -> Label
        for i, rk in enumerate(rows, start=1):
            ttk.Label(frame, text=rk).grid(row=i, column=0, padx=8, pady=4, sticky="w")
            for j, ck in enumerate(cols, start=1):
                val = self.GAMMAS_BY_DS[ck][rk]
                lbl = ttk.Label(frame, text=f"{val:.2f}")
                lbl.grid(row=i, column=j, padx=8, pady=4, sticky="w")
                self.gamma_cells[(rk, ck)] = lbl

    def _update_gamma_table(self, *_):
        """Highlights the currently selected design situation in bold."""
        ds_val = self.ds_var.get()
        ds_name = self.DS_NAME_BY_VALUE.get(ds_val, "BS-P")
        cols = ["BS-P", "BS-T", "BS-A/BS-E"]
        rows = ["γ_G", "γ_Q", "γ_M", "γ_φ", "γ_c", "γ_R"]

        for ck in cols:
            for rk in rows:
                lbl = self.gamma_cells[(rk, ck)]
                lbl.configure(font=self._font_bold if ck == ds_name else self._font_norm)

    # ---------- UI Structure ----------
    def _build_ui(self):
        # Notebook file selection
        file_frame = ttk.Frame(self)
        file_frame.pack(fill="x", padx=10, pady=8)

        ttk.Label(file_frame, text="Notebook file:").pack(side="left")
        ttk.Entry(file_frame, textvariable=self.nb_path, width=80).pack(side="left", padx=6)
        ttk.Button(file_frame, text="Browse…", command=self._browse_nb).pack(side="left")
        ttk.Button(file_frame, text="Load notebook", command=self._load_nb).pack(side="left", padx=6)

        # Paned Window: left inputs, right output
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=8)

        # Left: inputs
        self.left = ttk.Frame(paned)
        paned.add(self.left, weight=1)

        # Right: output
        self.right = ttk.Frame(paned)
        paned.add(self.right, weight=2)

        self._build_inputs(self.left)
        self._build_output(self.right)

    def _browse_nb(self):
        p = filedialog.askopenfilename(
            title="Select file",
            filetypes=[("Python file", "*.py"), ("All files", "*.*")],
        )
        if p:
            self.nb_path.set(p)

    def _load_nb(self):
        path = Path(self.nb_path.get())
        if not path.exists():
            messagebox.showerror("Error", f"File not found:\n{path}")
            return
        try:
            self.code_cells = load_notebook_code_cells(path)
            messagebox.showinfo("OK", f"Notebook loaded: {path.name}\nCode cells: {len(self.code_cells)}")
        except Exception as e:
            messagebox.showerror("Error", f"Notebook could not be read:\n{e}")

    # ---------- Input Panel ----------
    def _build_inputs(self, parent):
        # Tabs for overview
        nb = ttk.Notebook(parent)
        nb.pack(fill="both", expand=True)

        self.tab_ds = ttk.Frame(nb)
        self.tab_fund = ttk.Frame(nb)
        self.tab_soil = ttk.Frame(nb)
        self.tab_loads = ttk.Frame(nb)

        nb.add(self.tab_ds, text="Design Situation")
        nb.add(self.tab_fund, text="Foundation Dimensions")
        nb.add(self.tab_soil, text="Soil Layers")
        nb.add(self.tab_loads, text="Loads")

        # --- DS ---
        self.ds_var = tk.StringVar(value="1")
        ttk.Label(self.tab_ds, text="EC7 Design Situation").pack(anchor="w", padx=10, pady=10)
        rb1 = ttk.Radiobutton(self.tab_ds, text="1) BS-P (persistent)",
                              variable=self.ds_var, value="1", command=self._update_gamma_table)
        rb2 = ttk.Radiobutton(self.tab_ds, text="2) BS-T (temporary)",
                              variable=self.ds_var, value="2", command=self._update_gamma_table)
        rb3 = ttk.Radiobutton(self.tab_ds, text="3) BS-A/BS-E (accidental/earthquake)",
                              variable=self.ds_var, value="3", command=self._update_gamma_table)
        rb1.pack(anchor="w", padx=20)
        rb2.pack(anchor="w", padx=20)
        rb3.pack(anchor="w", padx=20)

        # Table of partial safety factors (γ)
        self._build_gamma_table(self.tab_ds)
        self._update_gamma_table()  # initial highlight


        # --- Foundation ---
        self.ft_var = tk.StringVar(value="1")  # 1 Rectangle, 2 Strip
        box = ttk.LabelFrame(self.tab_fund, text="Foundation type")
        box.pack(fill="x", padx=10, pady=10)
        ttk.Radiobutton(box, text="1) Rectangle (pad foundation)", variable=self.ft_var, value="1", command=self._update_fund_fields).pack(anchor="w", padx=10, pady=4)
        ttk.Radiobutton(box, text="2) Strip foundation (per linear meter, a = 1.0 m)", variable=self.ft_var, value="2", command=self._update_fund_fields).pack(anchor="w", padx=10, pady=4)

        dims = ttk.LabelFrame(self.tab_fund, text="Dimensions (m)")
        dims.pack(fill="x", padx=10, pady=10)

        self.a_var = tk.StringVar(value="2.0")
        self.b_var = tk.StringVar(value="1.5")
        self.h_var = tk.StringVar(value="1.0")
        self.d_var = tk.StringVar(value="0.8")

        self.row_a = self._labeled_entry(dims, "Length a", self.a_var)
        self.row_b = self._labeled_entry(dims, "Width b", self.b_var)
        self.row_h = self._labeled_entry(dims, "Height h", self.h_var)
        self.row_d = self._labeled_entry(dims, "Embedment depth d", self.d_var)

        # --- Sketch (3D wireframe model) ---
        self.sketch_frame = ttk.LabelFrame(self.tab_fund, text="Sketch (3D wireframe model)")
        self.sketch_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.sketch_fig = plt.figure(figsize=(5.8, 4.2), dpi=100)
        self.sketch_ax = self.sketch_fig.add_subplot(111, projection='3d')

        # Set flag: "GUI-internal - do not collect"
        self.sketch_fig._gui_internal = True

        # Interaction off (no rotation/zooming)
        try:
            self.sketch_ax.mouse_init(rotate_btn=0, zoom_btn=0)
        except Exception:
            pass

        # absolutely "blank" axis
        self.sketch_ax.grid(False)
        self.sketch_ax.set_axis_off()
        self.sketch_fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

        self.sketch_canvas = FigureCanvasTkAgg(self.sketch_fig, master=self.sketch_frame)
        self.sketch_canvas.get_tk_widget().pack(fill="both", expand=True)

        # Redraw on changes
        def _trigger_redraw(*_):
            self._draw_fundament_sketch()

        for v in (self.a_var, self.b_var, self.h_var, self.d_var):
            v.trace_add("write", _trigger_redraw)
        self.ft_var.trace_add("write", _trigger_redraw)

        # draw initially
        self._draw_fundament_sketch()


        self._update_fund_fields()

        # Update sketch, but only if canvas exists
        if hasattr(self, "sketch_ax"):
            self._draw_fundament_sketch()

        # --- Soil profile ---
        soil_top = ttk.Frame(self.tab_soil)
        soil_top.pack(fill="x", padx=10, pady=10)

        ttk.Label(soil_top, text="Number of soil layers").pack(side="left")
        self.n_layers_var = tk.IntVar(value=1)
        spin = ttk.Spinbox(soil_top, from_=1, to=2, width=5, textvariable=self.n_layers_var, command=self._update_layers)
        spin.pack(side="left", padx=6)

        # Layer Frames
        self.layer_frames = []
        self.layer_name = [tk.StringVar(value="Sand"), tk.StringVar(value="Sand, denser")]
        self.layer_phi  = [tk.StringVar(value="30"), tk.StringVar(value="35")]
        self.layer_gam  = [tk.StringVar(value="20"), tk.StringVar(value="20")]
        self.layer_c    = [tk.StringVar(value="0"),  tk.StringVar(value="0")]

        for i in range(2):
            lf = ttk.LabelFrame(self.tab_soil, text=f"Layer {i+1}")
            lf.pack(fill="x", padx=10, pady=6)
            self._labeled_entry(lf, "Designation", self.layer_name[i])
            self._labeled_entry(lf, "φ (degrees)",  self.layer_phi[i])
            self._labeled_entry(lf, "γ (kN/m³)", self.layer_gam[i])
            self._labeled_entry(lf, "c (kN/m²)", self.layer_c[i])
            self.layer_frames.append(lf)

        # Depth bottom of layer 1
        self.z_sw_var = tk.StringVar(value="1.5")
        self.row_zsw = self._labeled_entry(self.tab_soil, "Depth bottom of layer 1 below ground level (m) [only for 2 layers]", self.z_sw_var)

        # Groundwater
        gw_frame = ttk.LabelFrame(self.tab_soil, text="Groundwater")
        gw_frame.pack(fill="x", padx=10, pady=10)
        self.gw_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(gw_frame, text="Groundwater present", variable=self.gw_var, command=self._update_gw).pack(anchor="w", padx=10, pady=4)
        self.z_gw_var = tk.StringVar(value="2.0")
        self.row_zgw = self._labeled_entry(gw_frame, "Depth of GW level below ground level (m)", self.z_gw_var)

        self._update_layers()
        self._update_gw()

        # --- Loads ---
        loads = ttk.LabelFrame(self.tab_loads, text="Characteristic loads")
        loads.pack(fill="x", padx=10, pady=10)
        self.Vgk_var = tk.StringVar(value="1000")
        self._labeled_entry(loads, "Vg,k", self.Vgk_var)

        self.has_Q_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(loads, text="Vertical variable load present (Qk)", variable=self.has_Q_var, command=self._update_loads).pack(anchor="w", padx=10, pady=4)
        self.Qk_var = tk.StringVar(value="0")
        self.row_Qk = self._labeled_entry(loads, "Qk", self.Qk_var)

        self.has_H_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(loads, text="Horizontal load present (Hk)", variable=self.has_H_var, command=self._update_loads).pack(anchor="w", padx=10, pady=4)
        self.Hk_var = tk.StringVar(value="0")
        self.row_Hk = self._labeled_entry(loads, "Hk", self.Hk_var)

        self._update_loads()

        # --- Loads sketch (2D) ---
        self._build_loads_sketch(self.tab_loads)

        # --- 2D sketch soil profile ---
        self._build_soil_sketch(self.tab_soil)

        # Actions
        btns = ttk.Frame(parent)
        btns.pack(fill="x", padx=10, pady=10)
        ttk.Button(btns, text="Calculate", command=self.on_run).pack(side="left")
        ttk.Button(btns, text="Reset", command=self.on_reset).pack(side="left", padx=6)
        
        # Export button
        self.export_button = ttk.Button(btns, text="Export PDF", command=self.on_export_pdf)
        self.export_button.pack(side="left", padx=6)
        self.export_button.configure(state="disabled") # Start disabled

    def _labeled_entry(self, parent, label, var):
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=10, pady=4)
        ttk.Label(row, text=label, width=38).pack(side="left")
        e = ttk.Entry(row, textvariable=var, width=18)
        e.pack(side="left")
        return row

    def _update_fund_fields(self):
        is_streifen = (self.ft_var.get() == "2")
        self.row_a.pack_forget() if is_streifen else self.row_a.pack(fill="x", padx=10, pady=4)
        # Update sketch
        try:
            self._draw_fundament_sketch()
        except Exception:
            pass
    def _parse_float(self, s, default):
        try:
            return float((s or "").strip().replace(",", "."))
        except Exception:
            return default

    def _dims_for_sketch(self):
        # Parse values robustly; for strip foundation a=1.0 is used for the sketch
        is_streifen = (self.ft_var.get() == "2")
        a_in = self._parse_float(self.a_var.get(), 1.0)
        a_render = 1.0 if is_streifen else max(a_in, 0.0)
        b = max(self._parse_float(self.b_var.get(), 1.0), 0.0)
        h = max(self._parse_float(self.h_var.get(), 1.0), 0.0)
        d_raw = max(self._parse_float(self.d_var.get(), 0.5), 0.0)
        # IMPORTANT: For the SKETCH ensure that d <= h (visualization only!)
        d = min(d_raw, h)
        return a_render, b, h, d, is_streifen

    def _draw_fundament_sketch(self):
        """
        Minimalistic 3D sketch (black/white), without axes/grid/interaction.
        d starts at the bottom edge (U-height) and runs upwards to ground level (z=0).
        For the SKETCH d <= h is forced (calculation code remains untouched).
        """
        if not hasattr(self, "sketch_ax"):
            return

        a0, b0, h0, d0, is_streifen = self._dims_for_sketch()

        # Visual scaling so that the foundation appears larger
        SCALE_BODY = 1.35
        a = max(a0 * SCALE_BODY, 1e-6)
        b = max(b0 * SCALE_BODY, 1e-6)
        h = max(h0 * SCALE_BODY, 1e-6)
        d = max(d0 * SCALE_BODY, 1e-6)

        ax = self.sketch_ax
        ax.cla()

        # Turn off all visual axis elements
        ax.grid(False); ax.set_axis_off()
        ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])
        ax.set_xlabel(''); ax.set_ylabel(''); ax.set_zlabel('')
        for axis in (ax.xaxis, ax.yaxis, ax.zaxis):
            try:
                axis.pane.set_visible(False)
                axis.line.set_visible(False)
            except Exception:
                pass
        try:
            ax.mouse_init(rotate_btn=0, zoom_btn=0)  # no rotation
        except Exception:
            pass

        # --- new z definitions (d <= h for sketch already forced in _dims_for_sketch) ---
        z_bot = -d                 # Bottom edge (U-height)
        z_top = z_bot + h          # Top edge

        # Corners of the body
        top = [(0,0,z_top),(a,0,z_top),(a,b,z_top),(0,b,z_top)]
        bot = [(0,0,z_bot),(a,0,z_bot),(a,b,z_bot),(0,b,z_bot)]

        L = max(a, b, h, d, 1.0)
        GAP_MAIN = 0.55 * L   # Distance of dimension line to body
        GAP_TEXT = 0.26 * L   # Distance of label to dimension line
        TXT_ZOFF = 0.06 * L   # small z-offset for text

        line_k  = dict(color="k", linewidth=1.0)
        text_k  = dict(color="k")
        arrow_k = dict(color="k", normalize=True, linewidth=0.9)

        # --- Body edges (black) ---
        edges = [
            (top[0], top[1]), (top[1], top[2]), (top[2], top[3]), (top[3], top[0]),
            (bot[0], bot[1]), (bot[1], bot[2]), (bot[2], bot[3]), (bot[3], bot[0]),
            (top[0], bot[0]), (top[1], bot[1]), (top[2], bot[2]), (top[3], bot[3]),
        ]
        for (x1,y1,z1),(x2,y2,z2) in edges:
            ax.plot([x1,x2],[y1,y2],[z1,z2], **line_k)

        # --- Origin: Point at corner + leader + label outside ---
        ax.scatter([0],[0],[z_bot], s=22, c="k")
        x_u_lbl = -GAP_MAIN * 0.85
        y_u_lbl = -GAP_MAIN * 0.85
        z_u_lbl = z_bot - 0.12 * L
        #ax.plot([x_u_lbl, 0], [y_u_lbl, 0], [z_u_lbl, z_bot], **line_k)  # Leader
        ax.text(x_u_lbl, y_u_lbl, z_u_lbl, " U (0;0)", zdir=None, **text_k)

        # --- Dimension line a (bottom, in front of the body) ---
        y_a = -GAP_MAIN * 1.05
        ax.plot([0,0],[0,y_a],[z_bot,z_bot], **line_k)
        ax.plot([a,a],[0,y_a],[z_bot,z_bot], **line_k)
        ax.quiver(0, y_a, z_bot,  1, 0, 0, length=a, **arrow_k)
        ax.quiver(a, y_a, z_bot, -1, 0, 0, length=a, **arrow_k)
        label_a = "a = 1 m" if is_streifen else "a"
        ax.text(a/2, y_a - GAP_TEXT, z_bot - TXT_ZOFF, f" {label_a}", zdir=None, **text_k)

        # --- Dimension line b (left outside, top) ---
        x_b = -GAP_MAIN * 1.15
        ax.plot([0,x_b],[0,0],[z_top,z_top], **line_k)
        ax.plot([0,x_b],[b,b],[z_top,z_top], **line_k)
        ax.quiver(x_b, 0, z_top, 0, 1, 0, length=b, **arrow_k)
        ax.quiver(x_b, b, z_top, 0,-1, 0, length=b, **arrow_k)
        ax.text(x_b - GAP_TEXT, b/2, z_top + TXT_ZOFF, " b", zdir=None, **text_k)

        # --- Dimension line h (left outside, vertical) ---
        x_h, y_h = -GAP_MAIN * 1.35, 0
        ax.plot([0,x_h],[0,y_h],[z_bot,z_bot], **line_k)
        ax.plot([0,x_h],[0,y_h],[z_top,z_top], **line_k)
        ax.quiver(x_h, y_h, z_bot, 0, 0, 1, length=h, **arrow_k)
        ax.quiver(x_h, y_h, z_top, 0, 0,-1, length=h, **arrow_k)
        ax.text(x_h - GAP_TEXT, y_h, (z_top+z_bot)/2, " h", zdir=None, **text_k)

        # --- Dimension line d (right outside, vertical - start at U-height, up to ground level) ---
        x_d, y_d = a + GAP_MAIN * 1.20, 0
        # Auxiliary lines from bottom edge (U-height) and ground level to dimension line
        ax.plot([a, x_d], [0, y_d], [z_bot, z_bot], **line_k)   # from U-height (bottom edge)
        ax.plot([a, x_d], [0, y_d], [0.0,   0.0  ], **line_k)   # from ground level
        # Arrow upwards: length = d (embedment depth of the bottom edge)
        ax.quiver(x_d, y_d, z_bot, 0, 0, 1, length=d, **arrow_k)
        # Baseline at the lower end (at z_bot)
        base_len = 0.33 * L
        ax.plot([x_d, x_d + base_len], [y_d, y_d], [z_bot, z_bot], **line_k)
        ax.text(x_d + GAP_TEXT, y_d, z_bot + d/2 - TXT_ZOFF, " d", zdir=None, **text_k)

        # fixed view & tight crop (fills canvas)
        ax.view_init(elev=20, azim=-55)
        ax.set_box_aspect((max(a,1e-6), max(b,1e-6), max(h,1e-6)))
        margin = 0.18 * L
        x_min = min(0, x_b, x_h, x_u_lbl) - margin
        x_max = max(a, x_d + base_len) + margin
        y_min = min(0, y_a, y_u_lbl) - margin
        y_max = max(b, y_d) + margin
        z_min = min(z_bot, z_u_lbl) - margin
        z_max = max(0.0, z_top) + 0.10 * L
        ax.set_xlim(x_min, x_max)
        ax.set_ylim(y_min, y_max)
        ax.set_zlim(z_min, z_max)

        if hasattr(self, "sketch_canvas"):
            self.sketch_canvas.draw()


    def _update_layers(self):
        n = self.n_layers_var.get()
        # show/hide layer 2
        if n == 1:
            self.layer_frames[1].pack_forget()
            self.row_zsw.pack_forget()
        else:
            self.layer_frames[1].pack(fill="x", padx=10, pady=6)
            self.row_zsw.pack(fill="x", padx=10, pady=6)

        # redraw sketch
        try:
            self._draw_soil_sketch()
        except Exception:
            pass

    def _update_gw(self):
        if self.gw_var.get():
            self.row_zgw.pack(fill="x", padx=10, pady=4)
        else:
            self.row_zgw.pack_forget()

    def _update_loads(self):
        if self.has_Q_var.get():
            self.row_Qk.pack(fill="x", padx=10, pady=4)
        else:
            self.row_Qk.pack_forget()
        if self.has_H_var.get():
            self.row_Hk.pack(fill="x", padx=10, pady=4)
        else:
            self.row_Hk.pack_forget()

    def _build_soil_sketch(self, parent):
        frame = ttk.LabelFrame(parent, text="Soil profile - sketch (2D)")
        frame.pack(fill="x", padx=10, pady=8)  # only fill horizontally, do not expand
        self.soil_sketch_frame = frame

        # smaller figure
        self.soil_fig = plt.Figure(figsize=(4.8, 2.2), dpi=110)
        self.soil_ax = self.soil_fig.add_subplot(111)
        self.soil_ax.set_axis_off()
        self.soil_fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

        self.soil_canvas = FigureCanvasTkAgg(self.soil_fig, master=frame)
        w = self.soil_canvas.get_tk_widget()
        # fixed, small height (so that inputs do not "disappear")
        w.configure(width=520, height=220)
        w.pack(fill="x", expand=False, padx=4, pady=4)

        self._setup_soil_traces()
        self._draw_soil_sketch()

        # IMPORTANT: after creating the sketch, ensure that
        # for 2 layers the bottom edge field is displayed
        self._update_layers()

        self.soil_fig._gui_internal = True
        
    def _setup_soil_traces(self):
        def _redraw(*_):
            try:
                self._draw_soil_sketch()
            except Exception:
                pass

        # Geometry/Layers/GW
        self.n_layers_var.trace_add("write", _redraw)
        self.z_sw_var.trace_add("write", _redraw)
        self.gw_var.trace_add("write", _redraw)
        self.z_gw_var.trace_add("write", _redraw)

        # Foundation (depth d / height h / width dimension for small sketch)
        self.d_var.trace_add("write", _redraw)
        self.h_var.trace_add("write", _redraw)
        self.b_var.trace_add("write", _redraw)
        self.ft_var.trace_add("write", _redraw)

        # (Layer names are used as labels)
        self.layer_name[0].trace_add("write", _redraw)
        self.layer_name[1].trace_add("write", _redraw)


    def _draw_soil_sketch(self):
        """
        2D cross-section (schematic, without axes/grid):
        - Ground level (black) y=0, interrupted at foundation
        - 1/2 soil layers (yellow/green)
        - GW (blue) optional, interrupted at foundation
        - Foundation: width=b, height=h, bottom edge at depth d (gray + hatched)
          Top edge at y = d - h (negative => protrudes above ground level)
        - automatic scaling so everything fits in the picture
        """
        import matplotlib.patches as mpatches

        ax = self.soil_ax
        ax.cla()
        ax.set_axis_off()

        # ---- Read inputs robustly ----
        try:
            n_layers = max(1, min(2, int(self.n_layers_var.get())))
        except Exception:
            n_layers = 1

        z_sw = None
        if n_layers == 2:
            try: z_sw = float(str(self.z_sw_var.get()).replace(",", "."))
            except Exception: z_sw = 1.5

        has_gw = bool(self.gw_var.get())
        z_gw = None
        if has_gw:
            try: z_gw = float(str(self.z_gw_var.get()).replace(",", "."))
            except Exception: z_gw = 2.0

        def _pf(s, default):
            try: return float(str(s).replace(",", "."))
            except Exception: return default

        b = max(_pf(self.b_var.get(), 1.0), 0.0)
        h = max(_pf(self.h_var.get(), 1.0), 0.0)
        d = max(_pf(self.d_var.get(), 0.5), 0.0)

        # Foundation geometry (y downwards positive)
        y_bot = d                 # Bottom edge
        y_top = d - h             # Top edge (negative => protrudes above ground level)
        f_height = h
        f_width  = b

        # ---- Determine scene size ----
        bottom_candidates = [y_bot, 1.0]
        if n_layers == 2 and z_sw is not None: bottom_candidates.append(z_sw)
        if has_gw and z_gw is not None:       bottom_candidates.append(z_gw)
        scene_bottom = max(bottom_candidates)
        scene_top = min(0.0, y_top)

        pad_top = 0.15 * max(h, 1.0) + 0.05 * scene_bottom
        pad_bot = 0.18 * max(h, 1.0) + 0.08 * scene_bottom
        y_min = scene_top - pad_top
        y_max = scene_bottom + pad_bot

        pad_x = 0.40 * max(b, 1.0) + 0.6
        W = max(b + 2 * pad_x, 4.0)

        # ---- Helper function: horizontal line with gap over the foundation ----
        def draw_hline_with_gap(y, color, lw, label_text=None, label_color=None):
            """draws y-constant; if it intersects the foundation, left & right as segments."""
            f_left = (W - f_width) / 2.0
            f_right = f_left + f_width
            intersects = (min(y_top, y_bot) <= y <= max(y_top, y_bot))
            # left
            if not intersects or f_left > 0:
                x1, x2 = 0.0, (f_left if intersects else W)
                if x2 > x1:
                    ax.plot([x1, x2], [y, y], color=color, linewidth=lw)
            # right
            if intersects and f_right < W:
                ax.plot([f_right, W], [y, y], color=color, linewidth=lw)

            if label_text:
                # Label as far left as possible; if left is too short, right of the foundation
                label_x = 0.02 * W
                min_legible = 0.08 * W
                if intersects and (f_left - label_x) < min_legible:
                    label_x = min(W - 0.1 * W, f_right + 0.03 * W)
                # slightly above the line (negative offset due to inverted y-axis)
                y_off = -(0.03 * (y_max - y_min))
                ax.text(label_x, y + y_off, label_text,
                        fontsize=10, color=(label_color or color))

        # ---- Draw soil layers ----
        soil1_to = z_sw if (n_layers == 2 and z_sw is not None) else y_max
        soil1_rect = mpatches.Rectangle((0, 0), W, max(0.0, soil1_to),
                                        facecolor=self.SOIL1_COLOR, edgecolor="k", linewidth=1.0)
        ax.add_patch(soil1_rect)

        if n_layers == 2 and z_sw is not None:
            soil2_rect = mpatches.Rectangle((0, z_sw), W, max(0.0, y_max - z_sw),
                                            facecolor=self.SOIL2_COLOR, edgecolor="k", linewidth=1.0)
            ax.add_patch(soil2_rect)

        # Layer labels
        ax.text(W * 0.02, (0 + soil1_to) * 0.5, "Soil 1", fontsize=10)
        if n_layers == 2 and z_sw is not None:
            ax.text(W * 0.02, z_sw + (y_max - z_sw) * 0.5, "Soil 2", fontsize=10)

        # ---- Foundation (gray + hatched, centered) ----
        f_left = (W - f_width) / 2.0
        found_rect = mpatches.Rectangle((f_left, y_top), f_width, f_height,
                                        facecolor=self.FOUND_FACE, edgecolor="k",
                                        linewidth=1.6, hatch=self.FOUND_HATCH)
        ax.add_patch(found_rect)
        ax.add_patch(mpatches.Rectangle((f_left, y_top), f_width, f_height,
                                        facecolor="none", edgecolor="k", linewidth=2.0))

        # ---- Ground level & GW with gap over the foundation ----
        draw_hline_with_gap(y=0.0, color="k", lw=2.0, label_text="GL")
        if has_gw and z_gw is not None:
            draw_hline_with_gap(y=z_gw, color=self.GW_COLOR, lw=2.0,
                                label_text="GW", label_color=self.GW_COLOR)

        # ---- Viewport / Layout ----
        ax.set_xlim(0, W)
        ax.set_ylim(y_max, y_min)  # inverted: 0 top
        ax.set_aspect("auto", adjustable="box")

        self.soil_canvas.draw()

    def _build_loads_sketch(self, parent):
        frame = ttk.LabelFrame(parent, text="Loads - sketch (2D)")
        frame.pack(fill="x", padx=10, pady=10)

        # compact, fixed size
        self.loads_fig = Figure(figsize=(4.8, 2.4), dpi=110)
        self.loads_ax = self.loads_fig.add_subplot(111)
        self.loads_ax.set_axis_off()
        self.loads_fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

        self.loads_canvas = FigureCanvasTkAgg(self.loads_fig, master=frame)
        w = self.loads_canvas.get_tk_widget()
        w.configure(width=520, height=240)
        w.pack(fill="x", expand=False, padx=4, pady=4)

        self._setup_loads_traces()
        self._draw_loads_sketch()

        self.loads_fig._gui_internal = True
    def _setup_loads_traces(self):
        def _redraw(*_):
            try:
              self._draw_loads_sketch()
            except Exception:
                # do not swallow anything here - when in doubt, better draw visibly
                pass

        # Foundation dimensions
        for v in (self.b_var, self.h_var):
            v.trace_add("write", _redraw)

        # Loads (and switches)
        self.Vgk_var.trace_add("write", _redraw)
        self.has_Q_var.trace_add("write", _redraw)
        self.Qk_var.trace_add("write", _redraw)
        self.has_H_var.trace_add("write", _redraw)
        self.Hk_var.trace_add("write", _redraw)

    def _draw_loads_sketch(self):
        """
        2D sketch of the loads:
        - Ground level (black) at y=0
        - Foundation (width b, height h) gray + hatched, top edge at y=0
        - Vg,k (always) & Qk (optional) coaxial over foundation center, directed downwards
         - Hk (optional) as horizontal arrow on left foundation side
        """
        import matplotlib.patches as mpatches

        ax = getattr(self, "loads_ax", None)
        cvs = getattr(self, "loads_canvas", None)
        if ax is None or cvs is None:
            return

        ax.cla()
        ax.set_axis_off()

        # --- robust parsers ---
        def pf(s, default):
            try:
                return float(str(s).replace(",", "."))
            except Exception:
                return default

        b = max(pf(self.b_var.get(), 1.0), 1e-3)
        h = max(pf(self.h_var.get(), 1.0), 1e-3)

        has_Q = bool(self.has_Q_var.get())
        has_H = bool(self.has_H_var.get())

        # --- Scene / Scaling ---
        pad_x = 0.45 * max(b, 1.0) + 0.6
        W = max(b + 2 * pad_x, 4.0)

        arrow_up = max(0.9 * h, 1.0)   # Space above
        below    = max(0.3 * h, 0.6)   # Space below

        # --- Ground level ---
        #ax.plot([0, W], [0, 0], color="k", linewidth=2.0)
        #ax.text(W * 0.02, -0.12 * arrow_up, "GL", fontsize=9)

        # --- Foundation (centered, top edge at y=0) ---
        f_left = (W - b) / 2.0
        found_rect = mpatches.Rectangle(
            (f_left, -h), b, h,
            facecolor=self.FOUND_FACE, edgecolor="k", linewidth=1.6, hatch=self.FOUND_HATCH
        )
        ax.add_patch(found_rect)
        ax.add_patch(mpatches.Rectangle((f_left, -h), b, h, facecolor="none", edgecolor="k", linewidth=2.0))

        # --- vertical load arrows on ONE fall line (foundation center) ---
        xc = f_left + 0.5 * b

        def fmt(name, var):
            try:
                val = pf(var.get(), None)
                return f"{name} = {val:.2f} kN/m" if val is not None else name
            except Exception:
                return name

        # Arrow drawer (top -> y=0), text to the right
        def v_arrow(y_start, label):
            ax.annotate("", xy=(xc, 0), xytext=(xc, y_start),
                        arrowprops=dict(arrowstyle="-|>", lw=2.0, color="k"))
            ax.text(xc + 0.02 * W, y_start * 0.96, label, ha="left", va="bottom", fontsize=10)

        # Vg,k (always), Qk (optional) slightly offset in height
        v_arrow(arrow_up, fmt("Vg,k", self.Vgk_var))
        if has_Q:
            v_arrow(arrow_up * 0.62, fmt("Qk", self.Qk_var))

        # --- horizontal load Hk (optional) - according to sketch ---
        if has_H:
            # Arrow just below ground level, so there is no overlap with the ground level line
            yh = -h
            # from left to the left foundation side; arrowhead at left edge (top left)
            x_end   = f_left
            x_start = f_left - (0.55 * max(b, 1.0))  # sufficient distance on the left

            ax.annotate(
                "", xy=(x_end, yh), xytext=(x_start, yh),
                arrowprops=dict(arrowstyle="-|>", lw=2.2, color=self.HK_COLOR)
            )

            # Label above the arrow, left-aligned - no overlapping
            ax.text(
                x_start-0.2, yh + 0.12 * max(h, 1.0),
                fmt("Hk", self.Hk_var),
                ha="left", va="bottom", fontsize=10, color=self.HK_COLOR
            )

        # --- Viewport (so that something is always visible) ---
        ax.set_xlim(0, W)
        ax.set_ylim(-h - below, arrow_up * 1.15)
        ax.set_aspect("auto", adjustable="box")

        cvs.draw()

    # ---------- Output Panel ----------
    def _build_output(self, parent):
        text_frame = ttk.LabelFrame(parent, text="Output")
        text_frame.pack(fill="both", expand=True, padx=8, pady=8)

        # Text Widget Setup
        self.text = tk.Text(text_frame, wrap="word", height=11)
        yscroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=yscroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        # --- Plot area with grid layout for X and Y scrollbars ---
        fig_frame = ttk.LabelFrame(parent, text="Plot representations")
        fig_frame.pack(fill="both", expand=True, padx=12, pady=12)

        # Important: Grid configuration so the canvas fills the space
        fig_frame.columnconfigure(0, weight=1)
        fig_frame.rowconfigure(0, weight=1)

        # The canvas itself
        self.fig_canvas_outer = tk.Canvas(fig_frame, bg="#f0f0f0") 
        
        # Create scrollbars
        self.fig_scroll_y = ttk.Scrollbar(fig_frame, orient="vertical", command=self.fig_canvas_outer.yview)
        self.fig_scroll_x = ttk.Scrollbar(fig_frame, orient="horizontal", command=self.fig_canvas_outer.xview)
        
        # Link canvas with scrollbars (HERE WAS THE ERROR: fig_scroll -> fig_scroll_y)
        self.fig_canvas_outer.configure(yscrollcommand=self.fig_scroll_y.set, xscrollcommand=self.fig_scroll_x.set)

        # Pack everything into the grid
        self.fig_canvas_outer.grid(row=0, column=0, sticky="nsew")
        self.fig_scroll_y.grid(row=0, column=1, sticky="ns")   # Right, full height
        self.fig_scroll_x.grid(row=1, column=0, sticky="ew")   # Bottom, full width

        # The inner frame holding the plots
        self.fig_inner = ttk.Frame(self.fig_canvas_outer)
        
        # Create window in canvas (anchor="nw" = top left)
        self.fig_canvas_window = self.fig_canvas_outer.create_window((0,0), window=self.fig_inner, anchor="nw")

        # Event: If the size of the inner frame changes, adjust scroll region
        def _on_inner_frame_configure(event):
            self.fig_canvas_outer.configure(scrollregion=self.fig_canvas_outer.bbox("all"))
        
        self.fig_inner.bind("<Configure>", _on_inner_frame_configure)

        self.figure_canvases = []  # List for stored FigureCanvasTkAgg

    def clear_output(self):
        self.text.delete("1.0", "end")
        # destroy existing FigureCanvasTkAgg
        for c in self.figure_canvases:
            try:
                c.get_tk_widget().destroy()
            except Exception:
                pass
        self.figure_canvases.clear()

    # ---------- Actions ----------
    def on_reset(self):
        self.clear_output()

    def on_run(self):
        from pathlib import Path
        path = Path(self.nb_path.get()).expanduser()

        if not path.exists():
            messagebox.showerror("Error", f"File not found:\n{path}")
            return

        # Build answers from GUI
        try:
            answers = self._build_answer_sequence()
            # Collect input also as dictionary for PDF
            inputs_for_pdf = self._collect_inputs_dict()
        except Exception as e:
            messagebox.showerror("Input error", str(e))
            return

        # Clear output & start info
        self.clear_output()
        self.text.insert("end", f"Start calculation ({path.name})...\n\n")
        self.update_idletasks()

        # Reset storage and disable button
        self.last_run_data = None
        self.export_button.configure(state="disabled")

        # Execute the file with the answers
        suffix = path.suffix.lower()
        script_globals = {} # Placeholder
        if suffix == ".py":
            output_text, figs, tb, script_globals= run_python_file_with_inputs(path, answers)
            #output_text, figs, tb = run_notebook_with_inputs(self.code_cells, answers)
        else:
            messagebox.showerror("Error", f"Unsupported file type: {suffix}\nAllowed: .py or .ipynb")
            return
        
        # --- SAVE DATA FOR PDF EXPORT ---
        self.last_run_data = {}
        self.last_run_data['inputs'] = inputs_for_pdf
        self.last_run_data['output_text'] = output_text
        self.last_run_data['plot_fig'] = figs[0] if figs else None
        
        # Get data from script context (variables from functions_new.py)
        self.last_run_data['itres'] = script_globals.get('itres') # Gets the 'itres' variable
        self.last_run_data['det'] = script_globals.get('det')     # Gets 'det'
        self.last_run_data['R_n_k'] = script_globals.get('R_n_k')
        self.last_run_data['R_n_d'] = script_globals.get('R_n_d')
        self.last_run_data['V_ed'] = script_globals.get('V_ed')
        self.last_run_data['ok'] = script_globals.get('ok')
        
        # Utilization factor 'mu' (if available, otherwise calculate)
        mu = script_globals.get('mu')
        if mu is None and self.last_run_data.get('R_n_d') and self.last_run_data.get('V_ed'):
            try:
                # Ensure they are floats
                r_n_d_val = float(self.last_run_data['R_n_d'])
                v_ed_val = float(self.last_run_data['V_ed'])
                if r_n_d_val == 0:
                    mu = float('inf')
                else:
                    mu = v_ed_val / r_n_d_val
            except (ValueError, TypeError, ZeroDivisionError):
                mu = float('inf') # Error during calculation
        self.last_run_data['mu'] = mu

        # Only activate button if core data is present
        if self.last_run_data.get('det') and self.last_run_data.get('R_n_d') is not None:
            self.export_button.configure(state="normal") # Activate button
        else:
            print("WARNING: Core data (det, R_n_d) was not found in the script context.")

        # Text outputs / errors
        if tb:
            self.text.insert("end", "ERROR during execution:\n")
            self.text.insert("end", tb + "\n\n")

        self.text.insert("end", output_text if (output_text and output_text.strip()) else "(No text/log output intercepted)\n")
        self.update_idletasks()

        # Show plots
        if figs:
            for fig in figs:
                try:
                    fig.subplots_adjust(left=0.001, right=0.99, top=0.95, bottom=0.15)
                except Exception:
                    pass
                canvas = FigureCanvasTkAgg(fig, master=self.fig_inner)
                canvas.get_tk_widget().pack(fill="both", expand=True, padx=5, pady=5)
                canvas.draw()
                self.figure_canvases.append(canvas)
        else:
            ttk.Label(self.fig_inner, text="No diagrams intercepted.").pack(fill="x", padx=10, pady=10)

    def _build_answer_sequence(self):
        """
        Build the answers exactly in the order of the input() prompts in the notebook:
        1) get_design_situation -> Selection [1/2/3]
        2) get_foundation_type -> Selection [1/2]
        3) get_foundation_dimensions -> depending on type
        4) get_soil_profile -> Number of layers; per layer: Name, φ, γ, c; optionally Depth UK1; GW (y/n), optionally Depth
        5) get_loads -> Vgk; Q? + optionally Qk; H? + optionally Hk
        """
        answers = []

        # 1) Design situation
        answers.append(self.ds_var.get())  # "1"/"2"/"3"

        # 2) Foundation type
        answers.append("1" if self.ft_var.get() == "1" else "2")  # "1" rectangle, "2" strip

        # 3) Dimensions
        if self.ft_var.get() == "2":  # Strip
            answers.append(self._num(self.b_var.get()))
            answers.append(self._num(self.h_var.get()))
            # The prompt contains (<= h ...); note the order (h was before)
            answers.append(self._num(self.d_var.get()))
        else:  # Rectangle
            answers.append(self._num(self.a_var.get()))
            answers.append(self._num(self.b_var.get()))
            answers.append(self._num(self.h_var.get()))
            answers.append(self._num(self.d_var.get()))

        # 4) Soil profile
        n = int(self.n_layers_var.get())
        answers.append(str(n))  # Quantity 1/2
        # Layers
        for i in range(n):
            answers.append(self.layer_name[i].get())                  # Designation (STRING!)
            answers.append(self._num(self.layer_phi[i].get()))
            answers.append(self._num(self.layer_gam[i].get()))
            answers.append(self._num(self.layer_c[i].get()))

            if n == 2 and i == 0:
                # Depth bottom layer 1
                answers.append(self._num(self.z_sw_var.get()))

        # GW
        answers.append('j' if self.gw_var.get() else 'n')
        if self.gw_var.get():
            answers.append(self._num(self.z_gw_var.get()))

        # 5) Loads
        answers.append(self._num(self.Vgk_var.get()))
        answers.append('j' if self.has_Q_var.get() else 'n')
        if self.has_Q_var.get():
            answers.append(self._num(self.Qk_var.get()))
        answers.append('j' if self.has_H_var.get() else 'n')
        if self.has_H_var.get():
            answers.append(self._num(self.Hk_var.get()))

        return answers

    @staticmethod
    def _num(s: str) -> str:
        s = (s or "").strip().replace(",", ".")
        # simple validation
        float(s)  # throws on error -> Exception
        return s

    def _collect_inputs_dict(self):
        """Collects all GUI inputs in a structured dictionary for the PDF export."""
        inputs = {}
        try:
            # 1. Design situation
            ds_val = self.ds_var.get()
            inputs['ds_val'] = ds_val
            inputs['ds_name'] = self.DS_NAME_BY_VALUE.get(ds_val, "BS-P")
            
            # 2. Foundation
            ft_val = self.ft_var.get()
            inputs['ft_name'] = "Rectangle" if ft_val == "1" else "Strip foundation"
            inputs['b'] = self._num(self.b_var.get())
            inputs['h'] = self._num(self.h_var.get())
            inputs['d'] = self._num(self.d_var.get())
            if ft_val == "1": # Rectangle
                inputs['a'] = self._num(self.a_var.get())
            else:
                inputs['a'] = "1.0 (Strip)"

            # 3. Soil profile
            n = int(self.n_layers_var.get())
            inputs['n_layers'] = n
            inputs['layers'] = []
            for i in range(n):
                layer_data = {
                    'name': self.layer_name[i].get(),
                    'phi': self._num(self.layer_phi[i].get()),
                    'gam': self._num(self.layer_gam[i].get()),
                    'c': self._num(self.layer_c[i].get())
                }
                inputs['layers'].append(layer_data)
            
            if n == 2:
                inputs['z_sw'] = self._num(self.z_sw_var.get())
            
            inputs['has_gw'] = self.gw_var.get()
            if inputs['has_gw']:
                inputs['z_gw'] = self._num(self.z_gw_var.get())

            # 4. Loads (adjust unit if necessary)
            unit = "kN/m" if inputs['ft_name'] == "Strip foundation" else "kN"
            inputs['unit'] = unit
            inputs['Vgk'] = self._num(self.Vgk_var.get())
            inputs['has_Q'] = self.has_Q_var.get()
            inputs['Qk'] = self._num(self.Qk_var.get()) if inputs['has_Q'] else "0"
            inputs['has_H'] = self.has_H_var.get()
            inputs['Hk'] = self._num(self.Hk_var.get()) if inputs['has_H'] else "0"
            
            return inputs
        except Exception as e:
            messagebox.showerror("Input error (for PDF)", f"Could not collect inputs: {e}")
            return None

    def on_export_pdf(self):
        """Called by the 'Export PDF' button."""
        if not self.last_run_data:
            messagebox.showerror("Error", "There are no valid calculation results for the export. Please execute 'Calculate' first.")
            return
            
        # Check if the important data is there
        if 'det' not in self.last_run_data or self.last_run_data.get('R_n_d') is None:
            messagebox.showerror("Error", "The calculation results (det, R_n_d) could not be found in the script. Export not possible.\n(Ensure that run_python_file_with_inputs returns 'globs'.)")
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Documents", "*.pdf"), ("All files", "*.*")],
            title="Save calculation results as..."
        )
        if not filepath:
            return # User pressed cancel

        try:
            self._generate_pdf_report(filepath, self.last_run_data)
            messagebox.showinfo("Export successful", f"PDF report was saved:\n{filepath}")
        except Exception as e:
            messagebox.showerror("PDF export error", f"An error occurred while creating the PDF:\n{e}\n\nTraceback:\n{traceback.format_exc()}")

    def _generate_pdf_report(self, filepath, data):
        """Creates the PDF document with reportlab."""
        
        # Try to register a font that supports umlauts
        font_name = "Arial"
        font_name_bold = "Arial-Bold"
        
        try:
            # Search for common fonts on various systems
            font_paths = [
                'C:/Windows/Fonts/Arial.ttf', # Windows
                '/Library/Fonts/Arial.ttf', # macOS (Standard path)
                '/System/Library/Fonts/Helvetica.ttc', # macOS (Alternative)
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf' # Linux (DejaVu)
            ]
            font_name = "Arial" # Desired name
            found_font = False
            for path in font_paths:
                if Path(path).exists():
                    pdfmetrics.registerFont(TTFont(font_name, path))
                    found_font = True
                    break
            if not found_font:
                font_name = "Arial" # Standard fallback
            
            # --- Register bold font ---
            font_paths_bold = [
                'C:/Windows/Fonts/Arialbd.ttf', # Windows Arial Bold
                '/Library/Fonts/Arial Bold.ttf', # macOS Arial Bold
                '/System/Library/Fonts/HelveticaBold.ttc', # macOS Helvetica Bold
                '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' # Linux DejaVu Bold
            ]
            font_name_bold = "Arial-Bold"
            found_font_bold = False
            for path in font_paths_bold:
                if Path(path).exists():
                    pdfmetrics.registerFont(TTFont(font_name_bold, path))
                    found_font_bold = True
                    break
            if not found_font_bold:
                font_name_bold = "Helvetica-Bold"
                
        except Exception as e:
            print(f"Font warning: {e}. Fallback to Helvetica.")
            font_name = "Helvetica"
            font_name_bold = "Helvetica-Bold"
            
        doc = SimpleDocTemplate(filepath, pagesize=A4,
                                rightMargin=2*cm, leftMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)
        Story = []
        
        # Styles
        styles = getSampleStyleSheet()
        styleH1 = ParagraphStyle('h1', parent=styles['h1'], fontName=font_name, fontSize=16, spaceAfter=14)
        styleH2 = ParagraphStyle('h2', parent=styles['h2'], fontName=font_name, fontSize=12, spaceAfter=10, keepWithNext=1)
        styleN = ParagraphStyle('normal', parent=styles['Normal'], fontName=font_name, fontSize=10, spaceAfter=6, leading=14)
        
        # Styles for results
        styleB = ParagraphStyle('bold', parent=styleN, fontName=font_name_bold, spaceAfter=2)
        styleResultOK = ParagraphStyle('res_ok', parent=styleN, fontName=font_name_bold, fontSize=11, spaceAfter=8, textColor=colors.darkgreen)
        styleResultFail = ParagraphStyle('res_fail', parent=styleN, fontName=font_name_bold, fontSize=11, spaceAfter=8, textColor=colors.red)


        # ----------------- TITLE -----------------
        Story.append(Paragraph("Calculation of Bearing Capacity Failure", styleH1))
        Story.append(Paragraph(f"Report from {datetime.date.today().strftime('%d.%m.%Y')}", styleN))
        Story.append(Spacer(1, 1*cm))

        # ----------------- 1. INPUT PARAMETERS -----------------
        # (Remains as table - clear for inputs)
        Story.append(Paragraph("Input parameters", styleH2))
        inputs = data.get('inputs', {})
        unit = inputs.get('unit', 'kN')
        
        input_data = [
            ["Parameter", "Value", "Unit"],
            ["Design situation", inputs.get('ds_name', 'N/A'), "-"],
            ["Foundation type", inputs.get('ft_name', 'N/A'), ""],
            ["Length a'", inputs.get('a', 'N/A'), "m"],
            ["Width b'", inputs.get('b', 'N/A'), "m"],
            ["Height h", inputs.get('h', 'N/A'), "m"],
            ["Embedment depth d", inputs.get('d', 'N/A'), "m"],
            ["Number of soil layers", inputs.get('n_layers', 'N/A'), ""],
        ]
        
        layers = inputs.get('layers', [])
        for i, layer in enumerate(layers):
            input_data.append([f"Layer {i+1} Name", layer.get('name', 'N/A'), ""])
            input_data.append([f"Layer {i+1} φ", layer.get('phi', 'N/A'), "°"])
            input_data.append([f"Layer {i+1} γ", layer.get('gam', 'N/A'), "kN/m³"])
            input_data.append([f"Layer {i+1} c", layer.get('c', 'N/A'), "kN/m²"])
        
        if 'z_sw' in inputs:
            input_data.append(["Depth bottom layer 1", inputs.get('z_sw', 'N/A'), "m"])
            
        gw_status = "Yes" if inputs.get('has_gw', False) else "No"
        input_data.append(["Groundwater present", gw_status, ""])
        if inputs.get('has_gw', False):
            input_data.append(["GW level z_gw", inputs.get('z_gw', 'N/A'), "m"])
            
        input_data.append(["Load Vg,k", inputs.get('Vgk', 'N/A'), unit]),
        input_data.append(["Load Qk", inputs.get('Qk', 'N/A'), unit]),
        input_data.append(["Load Hk", inputs.get('Hk', 'N/A'), unit]),

        t_inputs = Table(input_data, colWidths=[6*cm, 5*cm, 4*cm])
        t_inputs.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('GRID', (0,0), (-1,-1), 0.5, colors.black),
            ('BOX', (0,0), (-1,-1), 1, colors.black),
            ('FONTNAME', (0,0), (-1,-1), font_name),
            ('FONTSIZE', (0,0), (-1,-1), 9),
            ('ALIGN', (1,1), (-1,-1), 'RIGHT'),
        ]))
        Story.append(t_inputs)
        Story.append(Spacer(1, 1*cm))

        # ----------------- 2. ITERATION (if available) -----------------
        # (Remains as table - iterations make sense in tabular form)
        itres = data.get('itres')
        if itres and 'rows' in itres:
            Story.append(Paragraph("Iteration table (2-layer case)", styleH2))
            
            rows = itres['rows']
            iter_data = [["It.", "φ_geom", "φ_avg", "γ_avg", "c_avg", "A_tot", "A_top", "Δφ_rel"]]
            for r in rows:
                iter_data.append([
                    r['it'],
                    f"{r['phi_geom']:.3f}°",
                    f"{r['phi_avg']:.3f}°",
                    f"{r['gamma_avg']:.2f}",
                    f"{r['c_avg']:.2f}",
                    f"{r['A_tot']:.2f}",
                    f"{r['A_top']:.2f}",
                    f"{100*r['rel']:.2f}%"
                ])
                
            t_iter = Table(iter_data, colWidths=[1.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm])
            t_iter.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                ('BOX', (0,0), (-1,-1), 1, colors.black),
                ('FONTNAME', (0,0), (-1,-1), font_name),
                ('FONTSIZE', (0,0), (-1,-1), 8),
                ('ALIGN', (1,1), (-1,-1), 'RIGHT'),
            ]))
            Story.append(t_iter)
            Story.append(Spacer(1, 1*cm))

        # ----------------- 3. CALCULATION PARAMETERS (NEW: As text) -----------------
        Story.append(Paragraph("Calculation parameters (Bearing capacity resistance)", styleH2))
        det = data.get('det')
        if det:
            # Helper function for safely formatting numbers from the 'det' dict
            def f(key, decimals=3):
                try:
                    return f"{float(det.get(key, 0)):.{decimals}f}"
                except (ValueError, TypeError):
                    return str(det.get(key, "N/A"))

            # Use styleB (Bold) for subheadings and • for lists
            Story.append(Paragraph("Calculated values base (characteristic)", styleB))
            Story.append(Paragraph(f"&nbsp;&nbsp;•&nbsp;&nbsp;φ_k = {f('phi_k', 2)}°", styleN))
            Story.append(Paragraph(f"&nbsp;&nbsp;•&nbsp;&nbsp;c_k = {f('c_k', 2)} kN/m²", styleN))
            Story.append(Spacer(1, 0.2*cm))

            Story.append(Paragraph("Bearing capacity factors", styleB))
            Story.append(Paragraph(f"&nbsp;&nbsp;•&nbsp;&nbsp;N_b = {f('Nb0')} | N_d = {f('Nd0')} | N_c = {f('Nc0')}", styleN))
            Story.append(Spacer(1, 0.2*cm))

            Story.append(Paragraph("Shape factors (v)", styleB))
            Story.append(Paragraph(f"&nbsp;&nbsp;•&nbsp;&nbsp;v_b = {f('vb')} | v_d = {f('vd')} | v_c = {f('vc')}", styleN))
            Story.append(Spacer(1, 0.2*cm))

            Story.append(Paragraph(f"Load inclination factors (i) for δ = {f('delta_char_deg', 2)}°", styleB))
            Story.append(Paragraph(f"&nbsp;&nbsp;•&nbsp;&nbsp;i_b = {f('i_b')} | i_d = {f('i_d')} | i_c = {f('i_c')}", styleN))
            Story.append(Spacer(1, 0.2*cm))

            Story.append(Paragraph("Bearing capacity factors ", styleB))
            Story.append(Paragraph(f"&nbsp;&nbsp;•&nbsp;&nbsp;N_b0 = {f('N_b')} | N_d0 = {f('N_d')} | N_c0 = {f('N_c')}", styleN))
            Story.append(Spacer(1, 0.2*cm))

            Story.append(Paragraph("Unit weights and surcharge", styleB))
            Story.append(Paragraph(f"&nbsp;&nbsp;•&nbsp;&nbsp;Unit weight above base (γ1) = {f('gamma1', 2)} kN/m³", styleN))
            Story.append(Paragraph(f"&nbsp;&nbsp;•&nbsp;&nbsp;Unit weight below base (γ2) = {f('gamma2', 2)} kN/m³", styleN))
    
        else:
            Story.append(Paragraph("Details (det) not found.", styleN))
            
        Story.append(Spacer(1, 1*cm))

        # ----------------- 4. RESULTS (As text) -----------------
        Story.append(Paragraph("Results (Verification GEO-2)", styleH2))
        
        try:
            R_n_k = float(data.get('R_n_k', 0))
            R_n_d = float(data.get('R_n_d', 0))
            V_ed = float(data.get('V_ed', 0))
            mu = data.get('mu', float('inf'))
            ok = data.get('ok', False)
            
            status_text = "VERIFIED" if ok else "NOT VERIFIED"
            
            # --- Representation as structured paragraphs ---
            Story.append(Paragraph(f"Char. bearing capacity resistance R_n,k: <b>{R_n_k:.2f} {unit}</b>", styleN))
            Story.append(Paragraph(f"Design value bearing capacity resistance R_n,d: <b>{R_n_d:.2f} {unit}</b>", styleN))
            Story.append(Paragraph(f"Design value of action V_ed: <b>{V_ed:.2f} {unit}</b>", styleN))
            
            Story.append(Spacer(1, 0.5*cm))
            
            # Highlight result
            if ok:
                Story.append(Paragraph(f"Verification V_ed <= R_n,d: {status_text}", styleResultOK))
            else:
                Story.append(Paragraph(f"Verification V_ed <= R_n,d: {status_text}", styleResultFail))
                
            Story.append(Paragraph(f"Utilization factor μ = V_ed / R_n,d: <b>{mu:.3f}</b>", styleN))
            
        except Exception as e:
            Story.append(Paragraph(f"Error formatting the results: {e}", styleN))

        Story.append(Spacer(1, 1*cm))

        # ----------------- 5. PLOT (Without page break) -----------------
        Story.append(Paragraph("Graphical representation", styleH2))
        
        plot_fig = data.get('plot_fig')
        if plot_fig:
            try:
                # Save Matplotlib figure into an in-memory buffer
                img_buffer = io.BytesIO()
                plot_fig.savefig(img_buffer, format='PNG', dpi=300, bbox_inches='tight')
                img_buffer.seek(0)
                
                # Scale image to A4 width
                img = PILImage.open(img_buffer)
                img_width, img_height = img.size
                aspect = img_height / float(img_width)
                
                # Available width in PDF (A4 width - margins)
                available_width = doc.width 
                
                img_rl_width = available_width
                img_rl_height = available_width * aspect
                
                # Check if height exceeds the page
                available_height = doc.height
                if img_rl_height > available_height:
                    img_rl_height = available_height
                    img_rl_width = available_height / aspect

                rl_image = Image(img_buffer, width=img_rl_width, height=img_rl_height)
                Story.append(rl_image)
                # img_buffer.close() # <-- IMPORTANT: Do not close!
            except Exception as e:
                Story.append(Paragraph(f"Error embedding the graphic: {e}", styleN))
        else:
            Story.append(Paragraph("No graphic found.", styleN))

        # ----------------- BUILD PDF -----------------
        doc.build(Story)

def main():
    app = GrundbruchGUI()
    # Try to load notebook directly if present
    default_path = Path(app.nb_path.get())
    if default_path.exists():
        try:
            app.code_cells = load_notebook_code_cells(default_path)
        except Exception:
            pass
    app.mainloop()

if __name__ == "__main__":
    main()
    def _num(s: str) -> str:
        s = (s or "").strip().replace(",", ".")
        # simple validation
        float(s)  # throws on error -> Exception
        return s
