"""
GUI für die Berechnung der Grundbruchsicherheit (Tkinter)
- Führt das vorhandene Notebook UNVERÄNDERT aus
- Ersetzt Terminal-Eingaben durch GUI
- Zeigt print-Ausgaben und Plots in der GUI

Voraussetzungen:
  - Python 3.x
  - matplotlib
  - (optional) nbformat nicht nötig; wir lesen JSON direkt

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

# Matplotlib: Figuren in Tk einbetten
import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

import datetime

# ReportKab für PDF-Export (optional)

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
    print("PDF-Export nicht verfügbar. Bitte 'reportlab' und 'Pillow' installieren: pip install reportlab Pillow")
    # Sie könnten die PDF-Button-Erstellung überspringen, wenn der Import fehlschlägt


# ------------------------------------------------------------
# Notebook-Lader (liest Codezellen unverändert)
# ------------------------------------------------------------
def load_notebook_code_cells(path: Path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            nb = json.load(f)
        code_cells = [c for c in nb.get("cells", []) if c.get("cell_type") == "code"]
        sources = ["".join(c.get("source", [])) for c in code_cells]
        return sources
    except Exception as e:
        # Fallback: Falls JSON-Decode-Fehler auftritt (beispielsweise bei einer .py-Datei), 
        # wird der gesamte Inhalt als ein einzelner Codeblock zurückgegeben.
        with open(path, "r", encoding="utf-8") as f:
            source = f.read().strip()
        if source:
            return [source]
        else:
            raise Exception("Datei leer oder ungültig: " + str(e))

# ------------------------------------------------------------
# Ausführung der Notebook-Zellen mit gepatchtem input() und plt.show()
# ------------------------------------------------------------
# --- am Datei-Anfang bei den anderen Imports ---

def run_python_file_with_inputs(path, answers):
    """
    Führt eine .py-Datei wie `python file.py` aus:
    - __name__ = "__main__" (Main-Block wird ausgeführt)
    - input() wird aus `answers` bedient (GUI-Werte)
    - print(), stderr, logging werden abgefangen
    - plt.show() wird abgefangen (Figuren gesammelt)
    - sys.exit() wird abgefangen (GUI lebt weiter)
    - Arbeitsverzeichnis = Skriptverzeichnis
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
            raise RuntimeError(f"Nicht genügend GUI-Eingaben für input(); letzter Prompt: {prompt!r}")

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

        # wie `python path.py`
        os.chdir(os.path.dirname(path) or ".")
        sys.argv = [path]
        globs = {"__name__": "__main__", "__file__": path}

        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            with open(path, "r", encoding="utf-8") as f:
                code = compile(f.read(), path, "exec")
            exec(code, globs, globs)

        # falls Script Figuren offen lässt, ohne show() zu rufen: einsammeln
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
    # --- Farben / Schraffur für die 2D-Boden-Skizze ---
    SOIL1_COLOR = "#FFD54F"   # gelb
    SOIL2_COLOR = "#81C784"   # grün
    GW_COLOR    = "#1565C0"   # blau
    FOUND_FACE  = "#BDBDBD"   # grau (Fundament)
    FOUND_HATCH = "///"       # Schraffur Fundament
    HK_COLOR = "#2E7D32"   # grün für horizontale Last
    VK_COLOR = "#C62828"   # rot für vertikale Last

    def __init__(self):
        super().__init__()
        self.title("Berechnung der Grundbruchsicherheit einer Flächengründung nach EC7")
        self.geometry("1920x1080")

        self.nb_path = tk.StringVar(value=str(Path.cwd() / "src"))
        self.code_cells = None

        self.last_run_data = None  # Platzhalter für Ergebnisse

        self._build_ui()

    # Mapping Bemessungssituation -> Bezeichner
    DS_NAME_BY_VALUE = {"1": "BS-P", "2": "BS-T", "3": "BS-A/BS-E"}

    # Teilsicherheitsbeiwerte gemäß Notebook (unverändert übernommen)
    GAMMAS_BY_DS = {
        "BS-P":     {"γ_G": 1.35, "γ_Q": 1.50, "γ_M": 1.00, "γ_φ": 1.00, "γ_c": 1.00, "γ_R": 1.40},
        "BS-T":     {"γ_G": 1.20, "γ_Q": 1.30, "γ_M": 1.00, "γ_φ": 1.00, "γ_c": 1.00, "γ_R": 1.30},
        "BS-A/BS-E":{"γ_G": 1.10, "γ_Q": 1.10, "γ_M": 1.00, "γ_φ": 1.00, "γ_c": 1.00, "γ_R": 1.20},
    }

    def _build_gamma_table(self, parent):
        frame = ttk.LabelFrame(parent, text="Teilsicherheitsbeiwerte (γ)")
        frame.pack(fill="x", padx=10, pady=12)

        # Fonts für Hervorhebung
        self._font_norm = tkfont.nametofont("TkDefaultFont")
        self._font_bold = self._font_norm.copy()
        self._font_bold.configure(weight="bold")

        cols = ["BS-P", "BS-T", "BS-A/BS-E"]
        rows = ["γ_G", "γ_Q", "γ_M", "γ_φ", "γ_c", "γ_R"]

        # Header
        ttk.Label(frame, text="").grid(row=0, column=0, padx=8, pady=6, sticky="w")
        for j, col in enumerate(cols, start=1):
            ttk.Label(frame, text=col).grid(row=0, column=j, padx=8, pady=6, sticky="w")

        # Zellen erstellen + referenzieren
        self.gamma_cells = {}  # (row_key, col_key) -> Label
        for i, rk in enumerate(rows, start=1):
            ttk.Label(frame, text=rk).grid(row=i, column=0, padx=8, pady=4, sticky="w")
            for j, ck in enumerate(cols, start=1):
                val = self.GAMMAS_BY_DS[ck][rk]
                lbl = ttk.Label(frame, text=f"{val:.2f}")
                lbl.grid(row=i, column=j, padx=8, pady=4, sticky="w")
                self.gamma_cells[(rk, ck)] = lbl

    def _update_gamma_table(self, *_):
        """Markiert die aktuell gewählte Bemessungssituation fett."""
        ds_val = self.ds_var.get()
        ds_name = self.DS_NAME_BY_VALUE.get(ds_val, "BS-P")
        cols = ["BS-P", "BS-T", "BS-A/BS-E"]
        rows = ["γ_G", "γ_Q", "γ_M", "γ_φ", "γ_c", "γ_R"]

        for ck in cols:
            for rk in rows:
                lbl = self.gamma_cells[(rk, ck)]
                lbl.configure(font=self._font_bold if ck == ds_name else self._font_norm)

    # ---------- UI-Aufbau ----------
    def _build_ui(self):
        # Notebook-Datei Auswahl
        file_frame = ttk.Frame(self)
        file_frame.pack(fill="x", padx=10, pady=8)

        ttk.Label(file_frame, text="Notebook-Datei:").pack(side="left")
        ttk.Entry(file_frame, textvariable=self.nb_path, width=80).pack(side="left", padx=6)
        ttk.Button(file_frame, text="Durchsuchen…", command=self._browse_nb).pack(side="left")
        ttk.Button(file_frame, text="Notebook laden", command=self._load_nb).pack(side="left", padx=6)

        # Paned Window: links Eingaben, rechts Ausgabe
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=8)

        # Links: Eingaben
        self.left = ttk.Frame(paned)
        paned.add(self.left, weight=1)

        # Rechts: Ausgabe
        self.right = ttk.Frame(paned)
        paned.add(self.right, weight=2)

        self._build_inputs(self.left)
        self._build_output(self.right)

    def _browse_nb(self):
        p = filedialog.askopenfilename(
            title="Datei wählen",
            filetypes=[("Python-Datei", "*.py"), ("Alle Dateien", "*.*")],
        )
        if p:
            self.nb_path.set(p)

    def _load_nb(self):
        path = Path(self.nb_path.get())
        if not path.exists():
            messagebox.showerror("Fehler", f"Datei nicht gefunden:\n{path}")
            return
        try:
            self.code_cells = load_notebook_code_cells(path)
            messagebox.showinfo("OK", f"Notebook geladen: {path.name}\nCode-Zellen: {len(self.code_cells)}")
        except Exception as e:
            messagebox.showerror("Fehler", f"Notebook konnte nicht gelesen werden:\n{e}")

    # ---------- Eingabe-Panel ----------
    def _build_inputs(self, parent):
        # Tabs für Übersicht
        nb = ttk.Notebook(parent)
        nb.pack(fill="both", expand=True)

        self.tab_ds = ttk.Frame(nb)
        self.tab_fund = ttk.Frame(nb)
        self.tab_soil = ttk.Frame(nb)
        self.tab_loads = ttk.Frame(nb)

        nb.add(self.tab_ds, text="Bemessungssituation")
        nb.add(self.tab_fund, text="Fundamentabmessungen")
        nb.add(self.tab_soil, text="Bodenschichten")
        nb.add(self.tab_loads, text="Lasten")

        # --- DS ---
        self.ds_var = tk.StringVar(value="1")
        ttk.Label(self.tab_ds, text="EC7-Bemessungssituation").pack(anchor="w", padx=10, pady=10)
        rb1 = ttk.Radiobutton(self.tab_ds, text="1) BS-P (persistent)",
                              variable=self.ds_var, value="1", command=self._update_gamma_table)
        rb2 = ttk.Radiobutton(self.tab_ds, text="2) BS-T (temporary)",
                              variable=self.ds_var, value="2", command=self._update_gamma_table)
        rb3 = ttk.Radiobutton(self.tab_ds, text="3) BS-A/BS-E (accidental/earthquake)",
                              variable=self.ds_var, value="3", command=self._update_gamma_table)
        rb1.pack(anchor="w", padx=20)
        rb2.pack(anchor="w", padx=20)
        rb3.pack(anchor="w", padx=20)

        # Tabelle der Teilsicherheitsbeiwerte (γ)
        self._build_gamma_table(self.tab_ds)
        self._update_gamma_table()  # initial markieren


        # --- Fundament ---
        self.ft_var = tk.StringVar(value="1")  # 1 Rechteck, 2 Streifen
        box = ttk.LabelFrame(self.tab_fund, text="Fundamenttyp")
        box.pack(fill="x", padx=10, pady=10)
        ttk.Radiobutton(box, text="1) Rechteck (Einzelfundament)", variable=self.ft_var, value="1", command=self._update_fund_fields).pack(anchor="w", padx=10, pady=4)
        ttk.Radiobutton(box, text="2) Streifenfundament (je lfm, a = 1,0 m)", variable=self.ft_var, value="2", command=self._update_fund_fields).pack(anchor="w", padx=10, pady=4)

        dims = ttk.LabelFrame(self.tab_fund, text="Abmessungen (m)")
        dims.pack(fill="x", padx=10, pady=10)

        self.a_var = tk.StringVar(value="2.0")
        self.b_var = tk.StringVar(value="1.5")
        self.h_var = tk.StringVar(value="1.0")
        self.d_var = tk.StringVar(value="0.8")

        self.row_a = self._labeled_entry(dims, "Länge a", self.a_var)
        self.row_b = self._labeled_entry(dims, "Breite b", self.b_var)
        self.row_h = self._labeled_entry(dims, "Höhe h", self.h_var)
        self.row_d = self._labeled_entry(dims, "Einbindetiefe d", self.d_var)

        # --- Skizze (3D-Drahtmodell) ---
        self.sketch_frame = ttk.LabelFrame(self.tab_fund, text="Skizze (3D-Drahtmodell)")
        self.sketch_frame.pack(fill="both", expand=True, padx=10, pady=10)

        self.sketch_fig = plt.figure(figsize=(5.8, 4.2), dpi=100)
        self.sketch_ax = self.sketch_fig.add_subplot(111, projection='3d')

        # Flag setzen: "GUI-intern – nicht einsammeln"
        self.sketch_fig._gui_internal = True

        # Interaktion aus (kein Drehen/Zoomen)
        try:
            self.sketch_ax.mouse_init(rotate_btn=0, zoom_btn=0)
        except Exception:
            pass

        # absolut „blanke“ Achse
        self.sketch_ax.grid(False)
        self.sketch_ax.set_axis_off()
        self.sketch_fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

        self.sketch_canvas = FigureCanvasTkAgg(self.sketch_fig, master=self.sketch_frame)
        self.sketch_canvas.get_tk_widget().pack(fill="both", expand=True)

        # Redraw bei Änderungen
        def _trigger_redraw(*_):
            self._draw_fundament_sketch()

        for v in (self.a_var, self.b_var, self.h_var, self.d_var):
            v.trace_add("write", _trigger_redraw)
        self.ft_var.trace_add("write", _trigger_redraw)

        # initial zeichnen
        self._draw_fundament_sketch()


        self._update_fund_fields()

        # Skizze aktualisieren, aber nur wenn Canvas existiert
        if hasattr(self, "sketch_ax"):
            self._draw_fundament_sketch()

        # --- Bodenprofil ---
        soil_top = ttk.Frame(self.tab_soil)
        soil_top.pack(fill="x", padx=10, pady=10)

        ttk.Label(soil_top, text="Anzahl der Bodenschichten").pack(side="left")
        self.n_layers_var = tk.IntVar(value=1)
        spin = ttk.Spinbox(soil_top, from_=1, to=2, width=5, textvariable=self.n_layers_var, command=self._update_layers)
        spin.pack(side="left", padx=6)

        # Layer Frames
        self.layer_frames = []
        self.layer_name = [tk.StringVar(value="Sand"), tk.StringVar(value="Sand, dichter")]
        self.layer_phi  = [tk.StringVar(value="30"), tk.StringVar(value="35")]
        self.layer_gam  = [tk.StringVar(value="20"), tk.StringVar(value="20")]
        self.layer_c    = [tk.StringVar(value="0"),  tk.StringVar(value="0")]

        for i in range(2):
            lf = ttk.LabelFrame(self.tab_soil, text=f"Schicht {i+1}")
            lf.pack(fill="x", padx=10, pady=6)
            self._labeled_entry(lf, "Bezeichnung", self.layer_name[i])
            self._labeled_entry(lf, "φ (Grad)",  self.layer_phi[i])
            self._labeled_entry(lf, "γ (kN/m³)", self.layer_gam[i])
            self._labeled_entry(lf, "c (kN/m²)", self.layer_c[i])
            self.layer_frames.append(lf)

        # Tiefe UK Schicht 1
        self.z_sw_var = tk.StringVar(value="1.5")
        self.row_zsw = self._labeled_entry(self.tab_soil, "Tiefe UK Schicht 1 unter GOK (m) [nur bei 2 Schichten]", self.z_sw_var)

        # Grundwasser
        gw_frame = ttk.LabelFrame(self.tab_soil, text="Grundwasser")
        gw_frame.pack(fill="x", padx=10, pady=10)
        self.gw_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(gw_frame, text="Grundwasser vorhanden", variable=self.gw_var, command=self._update_gw).pack(anchor="w", padx=10, pady=4)
        self.z_gw_var = tk.StringVar(value="2.0")
        self.row_zgw = self._labeled_entry(gw_frame, "Tiefe GW-Spiegel unter GOK (m)", self.z_gw_var)

        self._update_layers()
        self._update_gw()

        # --- Lasten ---
        loads = ttk.LabelFrame(self.tab_loads, text="Charakteristische Lasten")
        loads.pack(fill="x", padx=10, pady=10)
        self.Vgk_var = tk.StringVar(value="1000")
        self._labeled_entry(loads, "Vg,k", self.Vgk_var)

        self.has_Q_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(loads, text="Vertikale veränderliche Last vorhanden (Qk)", variable=self.has_Q_var, command=self._update_loads).pack(anchor="w", padx=10, pady=4)
        self.Qk_var = tk.StringVar(value="0")
        self.row_Qk = self._labeled_entry(loads, "Qk", self.Qk_var)

        self.has_H_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(loads, text="Horizontale Last vorhanden (Hk)", variable=self.has_H_var, command=self._update_loads).pack(anchor="w", padx=10, pady=4)
        self.Hk_var = tk.StringVar(value="0")
        self.row_Hk = self._labeled_entry(loads, "Hk", self.Hk_var)

        self._update_loads()

        # --- Skizze Lasten (2D) ---
        self._build_loads_sketch(self.tab_loads)

        # --- 2D-Skizze Bodenprofil ---
        self._build_soil_sketch(self.tab_soil)

        # Aktionen
        btns = ttk.Frame(parent)
        btns.pack(fill="x", padx=10, pady=10)
        ttk.Button(btns, text="Berechnen", command=self.on_run).pack(side="left")
        ttk.Button(btns, text="Zurücksetzen", command=self.on_reset).pack(side="left", padx=6)
        
        # Export-Button
        self.export_button = ttk.Button(btns, text="PDF Exportieren", command=self.on_export_pdf)
        self.export_button.pack(side="left", padx=6)
        self.export_button.configure(state="disabled") # Deaktiviert starten

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
        # Skizze aktualisieren
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
        # Werte robust parsen; bei Streifenfundament wird a=1.0 für die Skizze verwendet
        is_streifen = (self.ft_var.get() == "2")
        a_in = self._parse_float(self.a_var.get(), 1.0)
        a_render = 1.0 if is_streifen else max(a_in, 0.0)
        b = max(self._parse_float(self.b_var.get(), 1.0), 0.0)
        h = max(self._parse_float(self.h_var.get(), 1.0), 0.0)
        d_raw = max(self._parse_float(self.d_var.get(), 0.5), 0.0)
        # WICHTIG: Für die SKIZZE sicherstellen, dass d ≤ h (nur Visualisierung!)
        d = min(d_raw, h)
        return a_render, b, h, d, is_streifen

    def _draw_fundament_sketch(self):
        """
        Minimalistische 3D-Skizze (schwarz/weiß), ohne Achsen/Gitter/Interaktion.
        d beginnt an der Unterkante (U-Höhe) und läuft nach oben bis GOK (z=0).
        Für die SKIZZE wird d ≤ h erzwungen (Berechnungscode bleibt unberührt).
        """
        if not hasattr(self, "sketch_ax"):
            return

        a0, b0, h0, d0, is_streifen = self._dims_for_sketch()

        # Visuelle Skalierung, damit das Fundament größer erscheint
        SCALE_BODY = 1.35
        a = max(a0 * SCALE_BODY, 1e-6)
        b = max(b0 * SCALE_BODY, 1e-6)
        h = max(h0 * SCALE_BODY, 1e-6)
        d = max(d0 * SCALE_BODY, 1e-6)

        ax = self.sketch_ax
        ax.cla()

        # Alles visuelle der Achse abschalten
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
            ax.mouse_init(rotate_btn=0, zoom_btn=0)  # keine Drehung
        except Exception:
            pass

        # --- neue z-Definitionen (d ≤ h für Skizze bereits in _dims_for_sketch erzwungen) ---
        z_bot = -d                 # Unterkante (U-Höhe)
        z_top = z_bot + h          # Oberkante

        # Ecken des Körpers
        top = [(0,0,z_top),(a,0,z_top),(a,b,z_top),(0,b,z_top)]
        bot = [(0,0,z_bot),(a,0,z_bot),(a,b,z_bot),(0,b,z_bot)]

        L = max(a, b, h, d, 1.0)
        GAP_MAIN = 0.55 * L   # Abstand Maßkette zum Körper
        GAP_TEXT = 0.26 * L   # Abstand Beschriftung zur Maßlinie
        TXT_ZOFF = 0.06 * L   # kleiner z-Offset für Text

        line_k  = dict(color="k", linewidth=1.0)
        text_k  = dict(color="k")
        arrow_k = dict(color="k", normalize=True, linewidth=0.9)

        # --- Körperkanten (schwarz) ---
        edges = [
            (top[0], top[1]), (top[1], top[2]), (top[2], top[3]), (top[3], top[0]),
            (bot[0], bot[1]), (bot[1], bot[2]), (bot[2], bot[3]), (bot[3], bot[0]),
            (top[0], bot[0]), (top[1], bot[1]), (top[2], bot[2]), (top[3], bot[3]),
        ]
        for (x1,y1,z1),(x2,y2,z2) in edges:
            ax.plot([x1,x2],[y1,y2],[z1,z2], **line_k)

        # --- Ursprung: Punkt an Ecke + Leader + Label außerhalb ---
        ax.scatter([0],[0],[z_bot], s=22, c="k")
        x_u_lbl = -GAP_MAIN * 0.85
        y_u_lbl = -GAP_MAIN * 0.85
        z_u_lbl = z_bot - 0.12 * L
        #ax.plot([x_u_lbl, 0], [y_u_lbl, 0], [z_u_lbl, z_bot], **line_k)  # Leader
        ax.text(x_u_lbl, y_u_lbl, z_u_lbl, " U (0;0)", zdir=None, **text_k)

        # --- Maßkette a (unten, vor dem Körper) ---
        y_a = -GAP_MAIN * 1.05
        ax.plot([0,0],[0,y_a],[z_bot,z_bot], **line_k)
        ax.plot([a,a],[0,y_a],[z_bot,z_bot], **line_k)
        ax.quiver(0, y_a, z_bot,  1, 0, 0, length=a, **arrow_k)
        ax.quiver(a, y_a, z_bot, -1, 0, 0, length=a, **arrow_k)
        label_a = "a = 1 m" if is_streifen else "a"
        ax.text(a/2, y_a - GAP_TEXT, z_bot - TXT_ZOFF, f" {label_a}", zdir=None, **text_k)

        # --- Maßkette b (links außen, oben) ---
        x_b = -GAP_MAIN * 1.15
        ax.plot([0,x_b],[0,0],[z_top,z_top], **line_k)
        ax.plot([0,x_b],[b,b],[z_top,z_top], **line_k)
        ax.quiver(x_b, 0, z_top, 0, 1, 0, length=b, **arrow_k)
        ax.quiver(x_b, b, z_top, 0,-1, 0, length=b, **arrow_k)
        ax.text(x_b - GAP_TEXT, b/2, z_top + TXT_ZOFF, " b", zdir=None, **text_k)

        # --- Maßkette h (links außen, vertikal) ---
        x_h, y_h = -GAP_MAIN * 1.35, 0
        ax.plot([0,x_h],[0,y_h],[z_bot,z_bot], **line_k)
        ax.plot([0,x_h],[0,y_h],[z_top,z_top], **line_k)
        ax.quiver(x_h, y_h, z_bot, 0, 0, 1, length=h, **arrow_k)
        ax.quiver(x_h, y_h, z_top, 0, 0,-1, length=h, **arrow_k)
        ax.text(x_h - GAP_TEXT, y_h, (z_top+z_bot)/2, " h", zdir=None, **text_k)

        # --- Maßkette d (rechts außen, vertikal – Start an U-Höhe, nach oben zu GOK) ---
        x_d, y_d = a + GAP_MAIN * 1.20, 0
        # Hilfslinien von Unterkante (U-Höhe) und GOK zur Maßlinie
        ax.plot([a, x_d], [0, y_d], [z_bot, z_bot], **line_k)   # von U-Höhe (Unterkante)
        ax.plot([a, x_d], [0, y_d], [0.0,   0.0  ], **line_k)   # von GOK
        # Pfeil nach oben: Länge = d (Einbindetiefe der Unterkante)
        ax.quiver(x_d, y_d, z_bot, 0, 0, 1, length=d, **arrow_k)
        # Baseline am unteren Ende (an z_bot)
        base_len = 0.33 * L
        ax.plot([x_d, x_d + base_len], [y_d, y_d], [z_bot, z_bot], **line_k)
        ax.text(x_d + GAP_TEXT, y_d, z_bot + d/2 - TXT_ZOFF, " d", zdir=None, **text_k)

        # feste Ansicht & enger Ausschnitt (füllt Canvas)
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
        # Schicht 2 ein-/ausblenden
        if n == 1:
            self.layer_frames[1].pack_forget()
            self.row_zsw.pack_forget()
        else:
            self.layer_frames[1].pack(fill="x", padx=10, pady=6)
            self.row_zsw.pack(fill="x", padx=10, pady=6)

        # Skizze nachziehen
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
        frame = ttk.LabelFrame(parent, text="Bodenprofil – Skizze (2D)")
        frame.pack(fill="x", padx=10, pady=8)  # nur horizontal füllen, nicht expandieren
        self.soil_sketch_frame = frame

        # kleinere Figur
        self.soil_fig = plt.Figure(figsize=(4.8, 2.2), dpi=110)
        self.soil_ax = self.soil_fig.add_subplot(111)
        self.soil_ax.set_axis_off()
        self.soil_fig.subplots_adjust(left=0, right=1, bottom=0, top=1)

        self.soil_canvas = FigureCanvasTkAgg(self.soil_fig, master=frame)
        w = self.soil_canvas.get_tk_widget()
        # feste, kleine Höhe (damit Eingaben nicht „verschwinden“)
        w.configure(width=520, height=220)
        w.pack(fill="x", expand=False, padx=4, pady=4)

        self._setup_soil_traces()
        self._draw_soil_sketch()

        # WICHTIG: nach dem Anlegen der Skizze sicherstellen, dass
        # bei 2 Schichten das UK-Feld eingeblendet ist
        self._update_layers()

        self.soil_fig._gui_internal = True
        
    def _setup_soil_traces(self):
        def _redraw(*_):
            try:
                self._draw_soil_sketch()
            except Exception:
                pass

        # Geometrie/Schichten/GW
        self.n_layers_var.trace_add("write", _redraw)
        self.z_sw_var.trace_add("write", _redraw)
        self.gw_var.trace_add("write", _redraw)
        self.z_gw_var.trace_add("write", _redraw)

        # Fundament (Tiefe d / Höhe h / Breitenmaß für kleine Skizze)
        self.d_var.trace_add("write", _redraw)
        self.h_var.trace_add("write", _redraw)
        self.b_var.trace_add("write", _redraw)
        self.ft_var.trace_add("write", _redraw)

        # (Schichtnamen werden als Label genutzt)
        self.layer_name[0].trace_add("write", _redraw)
        self.layer_name[1].trace_add("write", _redraw)


    def _draw_soil_sketch(self):
        """
        2D-Querschnitt (schematisch, ohne Achsen/Gitter):
        - GOK (schwarz) y=0, unterbrochen am Fundament
        - 1/2 Bodenschichten (gelb/grün)
        - GW (blau) optional, unterbrochen am Fundament
        - Fundament: Breite=b, Höhe=h, Unterkante in Tiefe d (grau + schraffiert)
          Oberkante bei y = d - h (negativ => ragt über GOK)
        - automatische Skalierung, damit alles ins Bild passt
        """
        import matplotlib.patches as mpatches

        ax = self.soil_ax
        ax.cla()
        ax.set_axis_off()

        # ---- Eingaben robust lesen ----
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

        # Fundament-Geometrie (y nach unten positiv)
        y_bot = d                 # Unterkante
        y_top = d - h             # Oberkante (negativ => ragt über GOK)
        f_height = h
        f_width  = b

        # ---- Szenengröße bestimmen ----
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

        # ---- Hilfsfunktion: horizontale Linie mit Lücke über dem Fundament ----
        def draw_hline_with_gap(y, color, lw, label_text=None, label_color=None):
            """zeichnet y-Konstante; falls sie das Fundament schneidet, links & rechts als Segmente."""
            f_left = (W - f_width) / 2.0
            f_right = f_left + f_width
            intersects = (min(y_top, y_bot) <= y <= max(y_top, y_bot))
            # links
            if not intersects or f_left > 0:
                x1, x2 = 0.0, (f_left if intersects else W)
                if x2 > x1:
                    ax.plot([x1, x2], [y, y], color=color, linewidth=lw)
            # rechts
            if intersects and f_right < W:
                ax.plot([f_right, W], [y, y], color=color, linewidth=lw)

            if label_text:
                # Label möglichst links; wenn links zu kurz, rechts vom Fundament
                label_x = 0.02 * W
                min_legible = 0.08 * W
                if intersects and (f_left - label_x) < min_legible:
                    label_x = min(W - 0.1 * W, f_right + 0.03 * W)
                # leicht über der Linie (negativer Offset wegen invertierter y-Achse)
                y_off = -(0.03 * (y_max - y_min))
                ax.text(label_x, y + y_off, label_text,
                        fontsize=10, color=(label_color or color))

        # ---- Bodenschichten zeichnen ----
        soil1_to = z_sw if (n_layers == 2 and z_sw is not None) else y_max
        soil1_rect = mpatches.Rectangle((0, 0), W, max(0.0, soil1_to),
                                        facecolor=self.SOIL1_COLOR, edgecolor="k", linewidth=1.0)
        ax.add_patch(soil1_rect)

        if n_layers == 2 and z_sw is not None:
            soil2_rect = mpatches.Rectangle((0, z_sw), W, max(0.0, y_max - z_sw),
                                            facecolor=self.SOIL2_COLOR, edgecolor="k", linewidth=1.0)
            ax.add_patch(soil2_rect)

        # Schicht-Labels
        ax.text(W * 0.02, (0 + soil1_to) * 0.5, "Soil 1", fontsize=10)
        if n_layers == 2 and z_sw is not None:
            ax.text(W * 0.02, z_sw + (y_max - z_sw) * 0.5, "Soil 2", fontsize=10)

        # ---- Fundament (grau + schraffiert, mittig) ----
        f_left = (W - f_width) / 2.0
        found_rect = mpatches.Rectangle((f_left, y_top), f_width, f_height,
                                        facecolor=self.FOUND_FACE, edgecolor="k",
                                        linewidth=1.6, hatch=self.FOUND_HATCH)
        ax.add_patch(found_rect)
        ax.add_patch(mpatches.Rectangle((f_left, y_top), f_width, f_height,
                                        facecolor="none", edgecolor="k", linewidth=2.0))

        # ---- GOK & GW mit Lücke über dem Fundament ----
        draw_hline_with_gap(y=0.0, color="k", lw=2.0, label_text="GOK")
        if has_gw and z_gw is not None:
            draw_hline_with_gap(y=z_gw, color=self.GW_COLOR, lw=2.0,
                                label_text="GW", label_color=self.GW_COLOR)

        # ---- Sichtfenster / Layout ----
        ax.set_xlim(0, W)
        ax.set_ylim(y_max, y_min)  # invertiert: 0 oben
        ax.set_aspect("auto", adjustable="box")

        self.soil_canvas.draw()

    def _build_loads_sketch(self, parent):
        frame = ttk.LabelFrame(parent, text="Lasten – Skizze (2D)")
        frame.pack(fill="x", padx=10, pady=10)

        # kompakte, fixe Größe
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
                # hier nichts verschlucken – im Zweifel lieber sichtbar zeichnen
                pass

        # Fundamentabmessungen
        for v in (self.b_var, self.h_var):
            v.trace_add("write", _redraw)

        # Lasten (und Schalter)
        self.Vgk_var.trace_add("write", _redraw)
        self.has_Q_var.trace_add("write", _redraw)
        self.Qk_var.trace_add("write", _redraw)
        self.has_H_var.trace_add("write", _redraw)
        self.Hk_var.trace_add("write", _redraw)

    def _draw_loads_sketch(self):
        """
        2D-Skizze der Lasten:
        - GOK (schwarz) bei y=0
        - Fundament (Breite b, Höhe h) grau + schraffiert, Oberkante bei y=0
        - Vg,k (immer) & Qk (optional) koaxial über Fundamentmitte, nach unten gerichtet
         - Hk (optional) als horizontaler Pfeil auf linke Fundamentseite
        """
        import matplotlib.patches as mpatches

        ax = getattr(self, "loads_ax", None)
        cvs = getattr(self, "loads_canvas", None)
        if ax is None or cvs is None:
            return

        ax.cla()
        ax.set_axis_off()

        # --- robuste Parser ---
        def pf(s, default):
            try:
                return float(str(s).replace(",", "."))
            except Exception:
                return default

        b = max(pf(self.b_var.get(), 1.0), 1e-3)
        h = max(pf(self.h_var.get(), 1.0), 1e-3)

        has_Q = bool(self.has_Q_var.get())
        has_H = bool(self.has_H_var.get())

        # --- Szene / Skalierung ---
        pad_x = 0.45 * max(b, 1.0) + 0.6
        W = max(b + 2 * pad_x, 4.0)

        arrow_up = max(0.9 * h, 1.0)   # Platz oberhalb
        below    = max(0.3 * h, 0.6)   # Platz unterhalb

        # --- GOK ---
        #ax.plot([0, W], [0, 0], color="k", linewidth=2.0)
        #ax.text(W * 0.02, -0.12 * arrow_up, "GOK", fontsize=9)

        # --- Fundament (mittig, Oberkante bei y=0) ---
        f_left = (W - b) / 2.0
        found_rect = mpatches.Rectangle(
            (f_left, -h), b, h,
            facecolor=self.FOUND_FACE, edgecolor="k", linewidth=1.6, hatch=self.FOUND_HATCH
        )
        ax.add_patch(found_rect)
        ax.add_patch(mpatches.Rectangle((f_left, -h), b, h, facecolor="none", edgecolor="k", linewidth=2.0))

        # --- vertikale Lastpfeile auf EINER Falllinie (Fundamentmitte) ---
        xc = f_left + 0.5 * b

        def fmt(name, var):
            try:
                val = pf(var.get(), None)
                return f"{name} = {val:.2f} kN/m" if val is not None else name
            except Exception:
                return name

        # Pfeilzeichner (oben -> y=0), Text rechts daneben
        def v_arrow(y_start, label):
            ax.annotate("", xy=(xc, 0), xytext=(xc, y_start),
                        arrowprops=dict(arrowstyle="-|>", lw=2.0, color="k"))
            ax.text(xc + 0.02 * W, y_start * 0.96, label, ha="left", va="bottom", fontsize=10)

        # Vg,k (immer), Qk (optional) leicht versetzt in der Höhe
        v_arrow(arrow_up, fmt("Vg,k", self.Vgk_var))
        if has_Q:
            v_arrow(arrow_up * 0.62, fmt("Qk", self.Qk_var))

        # --- horizontale Last Hk (optional) – gemäß Skizze ---
        if has_H:
            # Pfeil knapp unter GOK, damit keine Überdeckung der GOK-Linie entsteht
            yh = -h
            # von links auf die linke Fundamentseite; Pfeilkopf am linken Rand (oben links)
            x_end   = f_left
            x_start = f_left - (0.55 * max(b, 1.0))  # ausreichend Abstand links

            ax.annotate(
                "", xy=(x_end, yh), xytext=(x_start, yh),
                arrowprops=dict(arrowstyle="-|>", lw=2.2, color=self.HK_COLOR)
            )

            # Label oberhalb des Pfeils, linksbündig – kein Überlappen
            ax.text(
                x_start-0.2, yh + 0.12 * max(h, 1.0),
                fmt("Hk", self.Hk_var),
                ha="left", va="bottom", fontsize=10, color=self.HK_COLOR
            )

        # --- Sichtfenster (so, dass immer etwas sichtbar ist) ---
        ax.set_xlim(0, W)
        ax.set_ylim(-h - below, arrow_up * 1.15)
        ax.set_aspect("auto", adjustable="box")

        cvs.draw()

    # ---------- Ausgabe-Panel ----------
    def _build_output(self, parent):
        text_frame = ttk.LabelFrame(parent, text="Ausgabe")
        text_frame.pack(fill="both", expand=True, padx=8, pady=8)

        # Text-Widget Setup
        self.text = tk.Text(text_frame, wrap="word", height=11)
        yscroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=yscroll.set)
        self.text.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")

        # --- Plot-Bereich mit Grid-Layout für X- und Y-Scrollbars ---
        fig_frame = ttk.LabelFrame(parent, text="Plot-Darstellungen")
        fig_frame.pack(fill="both", expand=True, padx=12, pady=12)

        # Wichtig: Grid-Konfiguration, damit der Canvas den Platz ausfüllt
        fig_frame.columnconfigure(0, weight=1)
        fig_frame.rowconfigure(0, weight=1)

        # Der Canvas selbst
        self.fig_canvas_outer = tk.Canvas(fig_frame, bg="#f0f0f0") 
        
        # Scrollbars erstellen
        self.fig_scroll_y = ttk.Scrollbar(fig_frame, orient="vertical", command=self.fig_canvas_outer.yview)
        self.fig_scroll_x = ttk.Scrollbar(fig_frame, orient="horizontal", command=self.fig_canvas_outer.xview)
        
        # Canvas mit Scrollbars verknüpfen (HIER WAR DER FEHLER: fig_scroll -> fig_scroll_y)
        self.fig_canvas_outer.configure(yscrollcommand=self.fig_scroll_y.set, xscrollcommand=self.fig_scroll_x.set)

        # Alles ins Grid packen
        self.fig_canvas_outer.grid(row=0, column=0, sticky="nsew")
        self.fig_scroll_y.grid(row=0, column=1, sticky="ns")   # Rechts, volle Höhe
        self.fig_scroll_x.grid(row=1, column=0, sticky="ew")   # Unten, volle Breite

        # Der innere Frame, der die Plots hält
        self.fig_inner = ttk.Frame(self.fig_canvas_outer)
        
        # Fenster im Canvas erstellen (anchor="nw" = oben links)
        self.fig_canvas_window = self.fig_canvas_outer.create_window((0,0), window=self.fig_inner, anchor="nw")

        # Event: Wenn sich die Größe des inneren Frames ändert, Scrollregion anpassen
        def _on_inner_frame_configure(event):
            self.fig_canvas_outer.configure(scrollregion=self.fig_canvas_outer.bbox("all"))
        
        self.fig_inner.bind("<Configure>", _on_inner_frame_configure)

        self.figure_canvases = []  # Liste für gespeicherte FigureCanvasTkAgg

    def clear_output(self):
        self.text.delete("1.0", "end")
        # vorhandene FigureCanvasTkAgg zerstören
        for c in self.figure_canvases:
            try:
                c.get_tk_widget().destroy()
            except Exception:
                pass
        self.figure_canvases.clear()

    # ---------- Aktionen ----------
    def on_reset(self):
        self.clear_output()

    def on_run(self):
        from pathlib import Path
        path = Path(self.nb_path.get()).expanduser()

        if not path.exists():
            messagebox.showerror("Fehler", f"Datei nicht gefunden:\n{path}")
            return

        # Antworten aus GUI bauen
        try:
            answers = self._build_answer_sequence()
            # Eingabe auch als Diktionär für PDF sammeln
            inputs_for_pdf = self._collect_inputs_dict()
        except Exception as e:
            messagebox.showerror("Eingabefehler", str(e))
            return

        # Ausgabe leeren & Startinfo
        self.clear_output()
        self.text.insert("end", f"Starte Berechnung ({path.name})...\n\n")
        self.update_idletasks()

        # Reset storage and disable button
        self.last_run_data = None
        self.export_button.configure(state="disabled")

        # Ausführen der Datei mit den Antworten
        suffix = path.suffix.lower()
        script_globals = {} # Platzhalter
        if suffix == ".py":
            output_text, figs, tb, script_globals= run_python_file_with_inputs(path, answers)
            #output_text, figs, tb = run_notebook_with_inputs(self.code_cells, answers)
        else:
            messagebox.showerror("Fehler", f"Nicht unterstützter Dateityp: {suffix}\nErlaubt: .py oder .ipynb")
            return
        
        # --- DATEN FÜR PDF-EXPORT SPEICHERN ---
        self.last_run_data = {}
        self.last_run_data['inputs'] = inputs_for_pdf
        self.last_run_data['output_text'] = output_text
        self.last_run_data['plot_fig'] = figs[0] if figs else None
        
        # Daten aus dem Skript-Kontext holen (Variablen aus functions_new.py)
        self.last_run_data['itres'] = script_globals.get('itres') # Holt die 'itres'-Variable
        self.last_run_data['det'] = script_globals.get('det')     # Holt 'det'
        self.last_run_data['R_n_k'] = script_globals.get('R_n_k')
        self.last_run_data['R_n_d'] = script_globals.get('R_n_d')
        self.last_run_data['V_ed'] = script_globals.get('V_ed')
        self.last_run_data['ok'] = script_globals.get('ok')
        
        # Ausnutzungsgrad 'mu' (falls vorhanden, sonst berechnen)
        mu = script_globals.get('mu')
        if mu is None and self.last_run_data.get('R_n_d') and self.last_run_data.get('V_ed'):
            try:
                # Sicherstellen, dass es Floats sind
                r_n_d_val = float(self.last_run_data['R_n_d'])
                v_ed_val = float(self.last_run_data['V_ed'])
                if r_n_d_val == 0:
                    mu = float('inf')
                else:
                    mu = v_ed_val / r_n_d_val
            except (ValueError, TypeError, ZeroDivisionError):
                mu = float('inf') # Fehler beim Berechnen
        self.last_run_data['mu'] = mu

        # Button nur aktivieren, wenn Kerndaten vorhanden sind
        if self.last_run_data.get('det') and self.last_run_data.get('R_n_d') is not None:
            self.export_button.configure(state="normal") # Button aktivieren
        else:
            print("WARNUNG: Kerndaten (det, R_n_d) wurden nicht im Skript-Kontext gefunden.")

        # Textausgaben / Fehler
        if tb:
            self.text.insert("end", "FEHLER bei der Ausführung:\n")
            self.text.insert("end", tb + "\n\n")

        self.text.insert("end", output_text if (output_text and output_text.strip()) else "(Keine Text-/Logausgabe abgefangen)\n")
        self.update_idletasks()

        # Plots anzeigen
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
            ttk.Label(self.fig_inner, text="Keine Diagramme abgefangen.").pack(fill="x", padx=10, pady=10)

    def _build_answer_sequence(self):
        """
        Bilde die Antworten exakt in der Reihenfolge der input()-Abfragen im Notebook:
        1) get_design_situation -> Auswahl [1/2/3]
        2) get_foundation_type -> Auswahl [1/2]
        3) get_foundation_dimensions -> je nach Typ
        4) get_soil_profile -> Anzahl Schichten; je Schicht: Name, φ, γ, c; ggf. Tiefe UK1; GW (j/n), ggf. Tiefe
        5) get_loads -> Vgk; Q? + ggf. Qk; H? + ggf. Hk
        """
        answers = []

        # 1) Bemessungssituation
        answers.append(self.ds_var.get())  # "1"/"2"/"3"

        # 2) Fundamenttyp
        answers.append("1" if self.ft_var.get() == "1" else "2")  # "1" Rechteck, "2" Streifen

        # 3) Abmessungen
        if self.ft_var.get() == "2":  # Streifen
            answers.append(self._num(self.b_var.get()))
            answers.append(self._num(self.h_var.get()))
            # Der Prompt enthält (<= h ...); Reihenfolge beachten (h war vorher)
            answers.append(self._num(self.d_var.get()))
        else:  # Rechteck
            answers.append(self._num(self.a_var.get()))
            answers.append(self._num(self.b_var.get()))
            answers.append(self._num(self.h_var.get()))
            answers.append(self._num(self.d_var.get()))

        # 4) Bodenprofil
        n = int(self.n_layers_var.get())
        answers.append(str(n))  # Anzahl 1/2
        # Schichten
        for i in range(n):
            answers.append(self.layer_name[i].get())                  # Bezeichnung (STRING!)
            answers.append(self._num(self.layer_phi[i].get()))
            answers.append(self._num(self.layer_gam[i].get()))
            answers.append(self._num(self.layer_c[i].get()))

            if n == 2 and i == 0:
                # Tiefe UK Schicht 1
                answers.append(self._num(self.z_sw_var.get()))

        # GW
        answers.append('j' if self.gw_var.get() else 'n')
        if self.gw_var.get():
            answers.append(self._num(self.z_gw_var.get()))

        # 5) Lasten
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
        # simple Validierung
        float(s)  # wirft bei Fehler -> Exception
        return s

    def _collect_inputs_dict(self):
        """Sammelt alle GUI-Eingaben in einem strukturierten Diktionär für den PDF-Export."""
        inputs = {}
        try:
            # 1. Bemessungssituation
            ds_val = self.ds_var.get()
            inputs['ds_val'] = ds_val
            inputs['ds_name'] = self.DS_NAME_BY_VALUE.get(ds_val, "BS-P")
            
            # 2. Fundament
            ft_val = self.ft_var.get()
            inputs['ft_name'] = "Rechteck" if ft_val == "1" else "Streifenfundament"
            inputs['b'] = self._num(self.b_var.get())
            inputs['h'] = self._num(self.h_var.get())
            inputs['d'] = self._num(self.d_var.get())
            if ft_val == "1": # Rechteck
                inputs['a'] = self._num(self.a_var.get())
            else:
                inputs['a'] = "1.0 (Streifen)"

            # 3. Bodenprofil
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

            # 4. Lasten (Einheit anpassen, falls nötig)
            unit = "kN/m" if inputs['ft_name'] == "Streifenfundament" else "kN"
            inputs['unit'] = unit
            inputs['Vgk'] = self._num(self.Vgk_var.get())
            inputs['has_Q'] = self.has_Q_var.get()
            inputs['Qk'] = self._num(self.Qk_var.get()) if inputs['has_Q'] else "0"
            inputs['has_H'] = self.has_H_var.get()
            inputs['Hk'] = self._num(self.Hk_var.get()) if inputs['has_H'] else "0"
            
            return inputs
        except Exception as e:
            messagebox.showerror("Eingabefehler (für PDF)", f"Konnte Eingaben nicht sammeln: {e}")
            return None

    def on_export_pdf(self):
        """Wird vom 'PDF Exportieren' Button aufgerufen."""
        if not self.last_run_data:
            messagebox.showerror("Fehler", "Es sind keine gültigen Berechnungsergebnisse für den Export vorhanden. Bitte zuerst 'Berechnen' ausführen.")
            return
            
        # Prüfen, ob die wichtigen Daten da sind
        if 'det' not in self.last_run_data or self.last_run_data.get('R_n_d') is None:
            messagebox.showerror("Fehler", "Die Berechnungsergebnisse (det, R_n_d) konnten nicht im Skript gefunden werden. Export nicht möglich.\n(Stellen Sie sicher, dass run_python_file_with_inputs 'globs' zurückgibt.)")
            return

        filepath = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF-Dokumente", "*.pdf"), ("Alle Dateien", "*.*")],
            title="Berechnungsergebnisse speichern unter..."
        )
        if not filepath:
            return # Benutzer hat Abbrechen gedrückt

        try:
            self._generate_pdf_report(filepath, self.last_run_data)
            messagebox.showinfo("Export erfolgreich", f"PDF-Bericht wurde gespeichert:\n{filepath}")
        except Exception as e:
            messagebox.showerror("PDF-Exportfehler", f"Ein Fehler ist beim Erstellen der PDF aufgetreten:\n{e}\n\nTraceback:\n{traceback.format_exc()}")

    def _generate_pdf_report(self, filepath, data):
        """Erstellt das PDF-Dokument mit reportlab."""
        
        # Versuchen, eine Schriftart zu registrieren, die Umlaute kann
        font_name = "Arial"
        font_name_bold = "Arial-Bold"
        
        try:
            # Suchen nach gängigen Schriftarten auf verschiedenen Systemen
            font_paths = [
                'C:/Windows/Fonts/Arial.ttf', # Windows
                '/Library/Fonts/Arial.ttf', # macOS (Standardpfad)
                '/System/Library/Fonts/Helvetica.ttc', # macOS (Alternative)
                '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf' # Linux (DejaVu)
            ]
            font_name = "Arial" # Wunschname
            found_font = False
            for path in font_paths:
                if Path(path).exists():
                    pdfmetrics.registerFont(TTFont(font_name, path))
                    found_font = True
                    break
            if not found_font:
                font_name = "Arial" # Standard-Fallback
            
            # --- Fette Schriftart registrieren ---
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
            print(f"Schriftart-Warnung: {e}. Fallback auf Helvetica.")
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
        
        # Styles für Ergebnisse
        styleB = ParagraphStyle('bold', parent=styleN, fontName=font_name_bold, spaceAfter=2)
        styleResultOK = ParagraphStyle('res_ok', parent=styleN, fontName=font_name_bold, fontSize=11, spaceAfter=8, textColor=colors.darkgreen)
        styleResultFail = ParagraphStyle('res_fail', parent=styleN, fontName=font_name_bold, fontSize=11, spaceAfter=8, textColor=colors.red)


        # ----------------- TITEL -----------------
        Story.append(Paragraph("Berechnung der Grundbruchsicherheit", styleH1))
        Story.append(Paragraph(f"Bericht vom {datetime.date.today().strftime('%d.%m.%Y')}", styleN))
        Story.append(Spacer(1, 1*cm))

        # ----------------- 1. EINGABEPARAMETER -----------------
        # (Bleibt als Tabelle - übersichtlich für Eingaben)
        Story.append(Paragraph("Eingabeparameter", styleH2))
        inputs = data.get('inputs', {})
        unit = inputs.get('unit', 'kN')
        
        input_data = [
            ["Parameter", "Wert", "Einheit"],
            ["Bemessungssituation", inputs.get('ds_name', 'N/A'), "-"],
            ["Fundamenttyp", inputs.get('ft_name', 'N/A'), ""],
            ["Länge a'", inputs.get('a', 'N/A'), "m"],
            ["Breite b'", inputs.get('b', 'N/A'), "m"],
            ["Höhe h", inputs.get('h', 'N/A'), "m"],
            ["Einbindetiefe d", inputs.get('d', 'N/A'), "m"],
            ["Anzahl Bodenschichten", inputs.get('n_layers', 'N/A'), ""],
        ]
        
        layers = inputs.get('layers', [])
        for i, layer in enumerate(layers):
            input_data.append([f"Schicht {i+1} Name", layer.get('name', 'N/A'), ""])
            input_data.append([f"Schicht {i+1} φ", layer.get('phi', 'N/A'), "°"])
            input_data.append([f"Schicht {i+1} γ", layer.get('gam', 'N/A'), "kN/m³"])
            input_data.append([f"Schicht {i+1} c", layer.get('c', 'N/A'), "kN/m²"])
        
        if 'z_sw' in inputs:
            input_data.append(["Tiefe UK Schicht 1", inputs.get('z_sw', 'N/A'), "m"])
            
        gw_status = "Ja" if inputs.get('has_gw', False) else "Nein"
        input_data.append(["Grundwasser vorhanden", gw_status, ""])
        if inputs.get('has_gw', False):
            input_data.append(["GW-Spiegel z_gw", inputs.get('z_gw', 'N/A'), "m"])
            
        input_data.append(["Last Vg,k", inputs.get('Vgk', 'N/A'), unit]),
        input_data.append(["Last Qk", inputs.get('Qk', 'N/A'), unit]),
        input_data.append(["Last Hk", inputs.get('Hk', 'N/A'), unit]),

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

        # ----------------- 2. ITERATION (falls vorhanden) -----------------
        # (Bleibt als Tabelle - Iterationen sind tabellarisch sinnvoll)
        itres = data.get('itres')
        if itres and 'rows' in itres:
            Story.append(Paragraph("Iterationstabelle (2-Schicht-Fall)", styleH2))
            
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

        # ----------------- 3. BERECHNUNGSPARAMETER (NEU: Als Text) -----------------
        Story.append(Paragraph("Berechnungsparameter (Grundbruchwiderstand)", styleH2))
        det = data.get('det')
        if det:
            # Helferfunktion zum sicheren Formatieren von Zahlen aus dem 'det'-Dict
            def f(key, decimals=3):
                try:
                    return f"{float(det.get(key, 0)):.{decimals}f}"
                except (ValueError, TypeError):
                    return str(det.get(key, "N/A"))

            # Verwende styleB (Bold) für Zwischenüberschriften und • für Aufzählungen
            Story.append(Paragraph("Rechenwerte Sohle (charakteristisch)", styleB))
            Story.append(Paragraph(f"&nbsp;&nbsp;•&nbsp;&nbsp;φ_k = {f('phi_k', 2)}°", styleN))
            Story.append(Paragraph(f"&nbsp;&nbsp;•&nbsp;&nbsp;c_k = {f('c_k', 2)} kN/m²", styleN))
            Story.append(Spacer(1, 0.2*cm))

            Story.append(Paragraph("Tragfähigkeitsbeiwerte", styleB))
            Story.append(Paragraph(f"&nbsp;&nbsp;•&nbsp;&nbsp;N_b = {f('Nb0')} | N_d = {f('Nd0')} | N_c = {f('Nc0')}", styleN))
            Story.append(Spacer(1, 0.2*cm))

            Story.append(Paragraph("Formbeiwerte (v)", styleB))
            Story.append(Paragraph(f"&nbsp;&nbsp;•&nbsp;&nbsp;v_b = {f('vb')} | v_d = {f('vd')} | v_c = {f('vc')}", styleN))
            Story.append(Spacer(1, 0.2*cm))

            Story.append(Paragraph(f"Lastneigungsbeiwerte (i) für δ = {f('delta_char_deg', 2)}°", styleB))
            Story.append(Paragraph(f"&nbsp;&nbsp;•&nbsp;&nbsp;i_b = {f('i_b')} | i_d = {f('i_d')} | i_c = {f('i_c')}", styleN))
            Story.append(Spacer(1, 0.2*cm))

            Story.append(Paragraph("Tragfähigkeitsfaktoren ", styleB))
            Story.append(Paragraph(f"&nbsp;&nbsp;•&nbsp;&nbsp;N_b0 = {f('N_b')} | N_d0 = {f('N_d')} | N_c0 = {f('N_c')}", styleN))
            Story.append(Spacer(1, 0.2*cm))

            Story.append(Paragraph("Wichten und Auflast", styleB))
            Story.append(Paragraph(f"&nbsp;&nbsp;•&nbsp;&nbsp;Wichte über Sohle (γ1) = {f('gamma1', 2)} kN/m³", styleN))
            Story.append(Paragraph(f"&nbsp;&nbsp;•&nbsp;&nbsp;Wichte unter Sohle (γ2) = {f('gamma2', 2)} kN/m³", styleN))
    
        else:
            Story.append(Paragraph("Details (det) nicht gefunden.", styleN))
            
        Story.append(Spacer(1, 1*cm))

        # ----------------- 4. ERGEBNISSE (Als Text) -----------------
        Story.append(Paragraph("Ergebnisse (Nachweis GEO-2)", styleH2))
        
        try:
            R_n_k = float(data.get('R_n_k', 0))
            R_n_d = float(data.get('R_n_d', 0))
            V_ed = float(data.get('V_ed', 0))
            mu = data.get('mu', float('inf'))
            ok = data.get('ok', False)
            
            status_text = "NACHGEWIESEN" if ok else "NICHT NACHGEWIESEN"
            
            # --- Darstellung als strukturierte Paragraphen ---
            Story.append(Paragraph(f"Char. Grundbruchwiderstand R_n,k: <b>{R_n_k:.2f} {unit}</b>", styleN))
            Story.append(Paragraph(f"Bemessungswert Grundbruchwiderstand R_n,d: <b>{R_n_d:.2f} {unit}</b>", styleN))
            Story.append(Paragraph(f"Bemessungswert Einwirkung V_ed: <b>{V_ed:.2f} {unit}</b>", styleN))
            
            Story.append(Spacer(1, 0.5*cm))
            
            # Highlight Ergebnis
            if ok:
                Story.append(Paragraph(f"Nachweis V_ed <= R_n,d: {status_text}", styleResultOK))
            else:
                Story.append(Paragraph(f"Nachweis V_ed <= R_n,d: {status_text}", styleResultFail))
                
            Story.append(Paragraph(f"Ausnutzungsgrad μ = V_ed / R_n,d: <b>{mu:.3f}</b>", styleN))
            
        except Exception as e:
            Story.append(Paragraph(f"Fehler beim Formatieren der Ergebnisse: {e}", styleN))

        Story.append(Spacer(1, 1*cm))

        # ----------------- 5. PLOT (Ohne Seitenumbruch) -----------------
        Story.append(Paragraph("Grafische Darstellung", styleH2))
        
        plot_fig = data.get('plot_fig')
        if plot_fig:
            try:
                # Matplotlib-Figur in einen In-Memory-Buffer speichern
                img_buffer = io.BytesIO()
                plot_fig.savefig(img_buffer, format='PNG', dpi=300, bbox_inches='tight')
                img_buffer.seek(0)
                
                # Bild auf A4-Breite skalieren
                img = PILImage.open(img_buffer)
                img_width, img_height = img.size
                aspect = img_height / float(img_width)
                
                # Verfügbare Breite im PDF (A4-Breite - Ränder)
                available_width = doc.width 
                
                img_rl_width = available_width
                img_rl_height = available_width * aspect
                
                # Prüfen, ob Höhe die Seite sprengt
                available_height = doc.height
                if img_rl_height > available_height:
                    img_rl_height = available_height
                    img_rl_width = available_height / aspect

                rl_image = Image(img_buffer, width=img_rl_width, height=img_rl_height)
                Story.append(rl_image)
                # img_buffer.close() # <-- WICHTIG: Nicht schließen!
            except Exception as e:
                Story.append(Paragraph(f"Fehler beim Einbetten der Grafik: {e}", styleN))
        else:
            Story.append(Paragraph("Keine Grafik gefunden.", styleN))

        # ----------------- PDF BAUEN -----------------
        doc.build(Story)

def main():
    app = GrundbruchGUI()
    # Versuche Notebook direkt zu laden, wenn vorhanden
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
        # simple Validierung
        float(s)  # wirft bei Fehler -> Exception
        return s
