import sqlite3
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager, Screen
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.core.image import Image as CoreImage
from kivy.uix.image import Image as KivyImage
from kivymd.app import MDApp
from kivymd.uix.button import MDRaisedButton, MDFlatButton
from kivymd.uix.datatables import MDDataTable
from kivymd.uix.dialog import MDDialog
from kivymd.uix.menu import MDDropdownMenu
import matplotlib.pyplot as plt
import io
import os
import math
from kivy.uix.widget import Widget
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.popup import Popup
from kivy.graphics import Color, Ellipse, Rectangle

# Import backend
from igd import (
    SistemAntreanIGD, tambah_pasien_gui, get_all_pasien_records,
    get_chart_data, reset_seluruh_database
)

# Helper: Mengubah grafik Matplotlib menjadi Kivy Texture
def fig_to_kivy_texture(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', transparent=True)
    buf.seek(0)
    core_img = CoreImage(io.BytesIO(buf.getvalue()), ext='png')
    return core_img.texture

# ================== SCREEN CLASSES ==================
TRIASE_INFO = {
    1: {"nama": "Level 1 - Resusitasi", "warna": (0.55, 0.0, 0.0, 1),   "desc": "Kondisi mengancam jiwa"},
    2: {"nama": "Level 2 - Emergensi",  "warna": (0.82, 0.41, 0.12, 1), "desc": "Kondisi sangat serius"},
    3: {"nama": "Level 3 - Urgen",      "warna": (1.0,  0.84, 0.0,  1), "desc": "Kondisi perlu segera ditangani"},
    4: {"nama": "Level 4 - Semi-Urgen", "warna": (0.0,  0.50, 0.0,  1), "desc": "Kondisi stabil"},
    5: {"nama": "Level 5 - Non-Urgen",  "warna": (0.27, 0.51, 0.71, 1), "desc": "Kondisi tidak mendesak"},
}


class DonutChartWidget(Widget):
    """
    Satu widget tunggal: gambar semua arc + handle semua klik.
    Tidak ada widget bertumpuk → tidak ada bug koordinat/ordering.
    """

    def __init__(self, distribusi: dict, **kwargs):
        super().__init__(**kwargs)
        self.distribusi = distribusi
        self._slices = []   # [(level, count, start_angle, sweep_angle), ...]
        self._label = None
        self.bind(pos=self._draw, size=self._draw)
        self._build_slices()

    # ── Hitung slice ──────────────────────────────────────────────────
    def _build_slices(self):
        total = sum(self.distribusi.values())
        self._total = total
        self._slices = []
        if total == 0:
            return
        
        GAP = 2.0  # Celah antar slice dalam derajat
        
        current = 0.0
        for level in range(1, 6):
            count = self.distribusi.get(level, 0)
            if count == 0:
                continue
            
            # Hitung sudut slice penuh (termasuk GAP nanti)
            full_sweep = (count / total) * 360.0
            
            # Sudut untuk digambar (dikurangi GAP)
            draw_sweep = full_sweep - GAP
            if draw_sweep < 1.0:
                draw_sweep = 1.0
            
            # Simpan slice dengan sudut gambar
            self._slices.append((level, count, current, draw_sweep))
            
            # Pindahkan ke posisi berikutnya (full_sweep yang digunakan, bukan draw_sweep)
            current += full_sweep

    # ── Gambar semua arc dalam satu canvas ───────────────────────────
    def _draw(self, *args):
        from kivy.graphics import Color, Ellipse, Line
        self.canvas.clear()
        cx = self.x + self.width / 2
        cy = self.y + self.height / 2
        r_out = min(self.width, self.height) * 0.44
        r_in  = r_out * 0.55

        with self.canvas:
            if not self._slices:
                Color(0.85, 0.85, 0.85, 1)
                Ellipse(pos=(cx - r_out, cy - r_out),
                        size=(r_out * 2, r_out * 2))
                Color(0.92, 0.95, 0.98, 1)
                Ellipse(pos=(cx - r_in, cy - r_in),
                        size=(r_in * 2, r_in * 2))
                return

            for level, count, start, sweep in self._slices:
                r, g, b, a = TRIASE_INFO[level]["warna"]
                Color(r, g, b, 1)
                Ellipse(
                    pos=(cx - r_out, cy - r_out),
                    size=(r_out * 2, r_out * 2),
                    angle_start=start,
                    angle_end=start + sweep,
                )

            # Donut hole — 1 kali saja di akhir
            Color(0.92, 0.95, 0.98, 1)
            Ellipse(pos=(cx - r_in, cy - r_in),
                    size=(r_in * 2, r_in * 2))

        # Label total di tengah (gunakan MDLabel sebagai child overlay)
        self._update_label()

    def _update_label(self):
        from kivymd.uix.label import MDLabel
        # Hapus label lama jika ada
        if self._label and self._label in self.children:
            self.remove_widget(self._label)
        if self._total == 0:
            txt = "Tidak ada\ndata"
        else:
            txt = f"[b]{self._total}[/b]\npasien"
        self._label = MDLabel(
            text=txt, markup=True, halign="center",
            theme_text_color="Custom",
            text_color=(0.055, 0.294, 0.494, 1),
            font_style="Caption",
            size_hint=(None, None), size=(self.width * 0.4, self.height * 0.3),
            pos=(self.center_x - self.width * 0.2,
                 self.center_y - self.height * 0.15),
        )
        self.add_widget(self._label)

    # ── Deteksi klik ─────────────────────────────────────────────────
    # ── Deteksi klik (Sudah Diperbaiki) ────────────────────────────────
    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)

        cx = self.x + self.width / 2
        cy = self.y + self.height / 2
        r_out = min(self.width, self.height) * 0.44
        r_in  = r_out * 0.55

        dx = touch.x - cx
        dy = touch.y - cy
        dist = math.sqrt(dx * dx + dy * dy)

        # Harus di dalam ring donut
        if not (r_in <= dist <= r_out):
            return super().on_touch_down(touch)

        # 1. Ambil sudut matematika standar (0 derajat di kanan/jam 3, counter-clockwise)
        raw_angle = math.degrees(math.atan2(dy, dx)) % 360

        # 2. Konversi ke sistem sudut Kivy (0 derajat di atas/jam 12, clockwise)
        #    - Mengubah arah putaran: (360 - raw_angle)
        #    - Menggeser titik nol dari jam 3 ke jam 12: + 90 derajat
        kivy_angle = (360 - raw_angle + 90) % 360

        for level, count, start, sweep in self._slices:
            # Hitung batas akhir sudut slice berdasarkan sistem Kivy
            a_s = start % 360
            a_e = (start + sweep) % 360
            
            if a_s <= a_e:
                hit = a_s <= kivy_angle <= a_e
            else:
                # Menangani kondisi jika slice melewati batas cross-over 360 derajat
                hit = kivy_angle >= a_s or kivy_angle <= a_e
                
            if hit:
                self._show_popup(level, count)
                return True

        return super().on_touch_down(touch)

    def _is_angle_in_slice(self, angle, start, end):
        """
        Memeriksa apakah sudut berada di dalam rentang slice.
        Menangani slice yang melewati batas 360°.
        """
        # Normalisasi semua sudut ke 0-360
        start_norm = start % 360
        end_norm = end % 360
        angle_norm = angle % 360
        
        if start_norm < end_norm:
            # Slice normal (tidak melewati 360°)
            return start_norm <= angle_norm <= end_norm
        else:
            # Slice melewati batas 360° (wrap around)
            return angle_norm >= start_norm or angle_norm <= end_norm

    # ── Popup desain clean ────────────────────────────────────────────
    def _show_popup(self, level: int, count: int):
        from kivy.uix.floatlayout import FloatLayout
        from kivy.uix.popup import Popup
        from kivy.graphics import Color, RoundedRectangle, Ellipse, Rectangle
        from kivymd.uix.label import MDLabel
        from kivymd.uix.button import MDRaisedButton
        from kivy.uix.widget import Widget

        info = TRIASE_INFO[level]
        r, g, b, a = info["warna"]

        root = FloatLayout()

        # Background putih
        def _redraw_bg(w, *args):
            w.canvas.before.clear()
            with w.canvas.before:
                Color(1, 1, 1, 1)
                RoundedRectangle(pos=w.pos, size=w.size, radius=[dp(16)])
        root.bind(pos=_redraw_bg, size=_redraw_bg)

        # Accent bar atas berwarna level
        accent = Widget(size_hint=(1, None), height=dp(7),
                        pos_hint={"x": 0, "top": 1})
        def draw_accent(w, *args):
            w.canvas.clear()
            with w.canvas:
                Color(r, g, b, 1)
                RoundedRectangle(pos=w.pos, size=w.size,
                                 radius=[dp(16), dp(16), 0, 0])
        accent.bind(pos=draw_accent, size=draw_accent)
        root.add_widget(accent)

        # Badge lingkaran nomor level
        bs = dp(62)
        badge = Widget(size_hint=(None, None), size=(bs, bs),
                       pos_hint={"center_x": 0.5, "top": 0.91})
        def draw_badge(w, *args):
            w.canvas.clear()
            with w.canvas:
                Color(r, g, b, 0.18)
                Ellipse(pos=(w.x - dp(4), w.y - dp(4)),
                        size=(w.width + dp(8), w.height + dp(8)))
                Color(r, g, b, 1)
                Ellipse(pos=w.pos, size=w.size)
        badge.bind(pos=draw_badge, size=draw_badge)
        root.add_widget(badge)

        root.add_widget(MDLabel(
            text=f"[b]{level}[/b]", markup=True, halign="center",
            theme_text_color="Custom", text_color=(1, 1, 1, 1),
            font_style="H5",
            pos_hint={"center_x": 0.5, "top": 0.91},
            size_hint=(None, None), size=(bs, bs),
        ))

        # Nama level
        root.add_widget(MDLabel(
            text=f"[b]{info['nama']}[/b]", markup=True, halign="center",
            theme_text_color="Custom", text_color=(r, g, b, 1),
            font_style="H6", pos_hint={"center_x": 0.5, "center_y": 0.56},
        ))

        # Deskripsi
        root.add_widget(MDLabel(
            text=info["desc"], halign="center",
            theme_text_color="Custom", text_color=(0.45, 0.45, 0.45, 1),
            font_style="Body1", pos_hint={"center_x": 0.5, "center_y": 0.43},
        ))

        # Divider
        div = Widget(size_hint=(0.7, None), height=dp(1),
                     pos_hint={"center_x": 0.5, "center_y": 0.33})
        def draw_div(w, *args):
            w.canvas.clear()
            with w.canvas:
                Color(0.88, 0.88, 0.88, 1)
                Rectangle(pos=w.pos, size=w.size)
        div.bind(pos=draw_div, size=draw_div)
        root.add_widget(div)

        # Angka pasien besar
        root.add_widget(MDLabel(
            text=f"[b]{count}[/b]", markup=True, halign="center",
            theme_text_color="Custom", text_color=(r, g, b, 1),
            font_style="H4", pos_hint={"center_x": 0.5, "center_y": 0.26},
        ))

        # Sub-label
        root.add_widget(MDLabel(
            text="pasien terdaftar", halign="center",
            theme_text_color="Custom", text_color=(0.55, 0.55, 0.55, 1),
            font_style="Caption", pos_hint={"center_x": 0.5, "center_y": 0.16},
        ))

        # Tombol tutup
        btn = MDRaisedButton(
            text="Tutup", md_bg_color=(r, g, b, 1), text_color=(1, 1, 1, 1),
            pos_hint={"center_x": 0.5, "y": 0.04},
            size_hint=(0.55, None), height=dp(42), elevation=2,
        )
        root.add_widget(btn)

        popup = Popup(
            title="", title_size=0, title_color=(1, 1, 1, 0),
            content=root, size_hint=(0.40, 0.52),
            background="", background_color=(0, 0, 0, 0),
            separator_height=0, overlay_color=(0, 0, 0, 0.45),
        )
        btn.bind(on_release=popup.dismiss)
        popup.open()

    def update_data(self, distribusi: dict):
        self.distribusi = distribusi
        self._build_slices()
        self._draw()

class RootScreenManager(ScreenManager):
    pass

class SplashScreen(Screen):
    # Dihapus fitur pindah otomatis, sekarang hanya mengandalkan tombol START
    def go_to_login(self):
        self.manager.current = 'login'

class LoginScreen(Screen):
    def login(self):
        perawat = self.ids.perawat.text.strip()
        dokter = self.ids.dokter.text.strip()
        
        if not perawat or not dokter:
            MDDialog(title="Peringatan", text="Isi Nama Perawat dan Dokter terlebih dahulu!").open()
            return
        
        # Simpan sesi pengguna
        app = MDApp.get_running_app()
        app.perawat = perawat
        app.dokter = dokter
        app.sistem_antrean = SistemAntreanIGD()
        app.sistem_antrean.rebuild_from_db()
        
        # Pindah ke kerangka aplikasi utama
        self.manager.current = 'main_app'
        
        # Tunda sedikit untuk memperbarui teks di sidebar
        Clock.schedule_once(lambda dt: self._update_sidebar(perawat, dokter), 0.2)

    def _update_sidebar(self, perawat, dokter):
        main_screen = self.manager.get_screen('main_app')
        if 'sidebar_perawat' in main_screen.ids:
            main_screen.ids.sidebar_perawat.text = f"Perawat: {perawat}"
            main_screen.ids.sidebar_dokter.text = f"Dokter: {dokter}"

class MainAppScreen(Screen):
    def nav_to(self, screen_name):
        # Berpindah layar di dalam area konten utama (kanan)
        self.ids.content_sm.current = screen_name

    def reset_database(self):
        def do_reset(dialog):
            app = MDApp.get_running_app()
            reset_seluruh_database(app.sistem_antrean)
            app.sistem_antrean.head = None
            dialog.dismiss()
            
            # Refresh layar yang sedang terbuka agar langsung kosong
            current_screen = self.ids.content_sm.current_screen
            if hasattr(current_screen, 'on_enter'):
                current_screen.on_enter()
                
        dialog = MDDialog(title="Konfirmasi Berbahaya", text="Hapus seluruh data rekam medis dan antrean pasien?", buttons=[
            MDFlatButton(text="Batal", on_release=lambda x: dialog.dismiss()),
            MDRaisedButton(text="Hapus Semua", md_bg_color=(1,0,0,1), on_release=lambda x: do_reset(dialog))
        ])
        dialog.open()

class DashboardScreen(Screen):
    def on_enter(self):
        # Saat layar dibuka, perbarui semua data
        Clock.schedule_once(self._refresh_data, 0.1)

    def _refresh_data(self, dt):
        if 'total_label' in self.ids:
            self.update_stats()
            self.update_charts()
            self.update_queue_list()

    def update_stats(self):
        data = get_chart_data()
        self.ids.total_label.text = str(data['total'])
        self.ids.menunggu_label.text = str(data['menunggu'])
        self.ids.diperiksa_label.text = str(data['diperiksa'])
        self.ids.kritis_label.text = str(data['level_kritis'])

    def update_charts(self):
        data = get_chart_data()
        
        # Donut Chart INTERAKTIF
        box_donut = self.ids.donut_chart_box
        box_donut.clear_widgets()
        box_donut.add_widget(DonutChartWidget(distribusi=data['distribusi']))

        # Bar Chart
        box_bar = self.ids.bar_chart_box
        box_bar.clear_widgets()
        fig2, ax2 = plt.subplots(figsize=(4, 3))
        status_labels = ['Menunggu', 'Diperiksa']
        status_counts = [data['menunggu'], data['diperiksa']]
        ax2.bar(status_labels, status_counts, color=['#8b0000', '#0E4B7E'], width=0.5)
        box_bar.add_widget(KivyImage(texture=fig_to_kivy_texture(fig2), size_hint=(1, 1)))
        plt.close(fig2)

    def update_queue_list(self):
        app = MDApp.get_running_app()
        if app.sistem_antrean is None:
            return 
            
        container = self.ids.queue_list_container
        container.clear_widgets()
        antrean = app.sistem_antrean.tampilkan_antrean()
        
        if not antrean:
            from kivymd.uix.label import MDLabel
            lbl_kosong = MDLabel(
                text="Antrean kosong", 
                halign="center", 
                size_hint_y=None,
                height="100dp",
                theme_text_color="Secondary",
                font_style="Body1"
            )
            container.add_widget(lbl_kosong)
        else:
            from kivymd.uix.list import OneLineListItem
            for p in antrean:
                item = OneLineListItem(text=f"{p['nomor']}. {p['nama']} | Keluhan: {p['keluhan']} | Lvl {p['level']}")
                container.add_widget(item)

class DaftarPasienScreen(Screen):
    def on_enter(self):
        Clock.schedule_once(self._init_ui, 0.1)
        
    def _init_ui(self, dt):
        if 'dropdown_kesadaran' in self.ids and not hasattr(self, 'menu'):
            menu_items = [
                {"viewclass": "OneLineListItem", "text": "Sadar Penuh", "on_release": lambda x="Sadar Penuh": self.set_kesadaran(x)},
                {"viewclass": "OneLineListItem", "text": "Tidak Sadar/Pingsan", "on_release": lambda x="Tidak Sadar/Pingsan": self.set_kesadaran(x)}
            ]
            self.menu = MDDropdownMenu(
                caller=self.ids.dropdown_kesadaran,
                items=menu_items,
                position="bottom",
                width_mult=4,
            )

    def set_kesadaran(self, text_item):
        self.ids.dropdown_kesadaran.text = text_item
        self.menu.dismiss()

    def daftar(self):
        nama = self.ids.nama.text.strip()
        keluhan = self.ids.keluhan.text.strip()
        
        if not nama or not keluhan:
            MDDialog(title="Gagal", text="Pastikan Nama dan Keluhan sudah diisi!").open()
            return
            
        try:
            tensi = int(self.ids.tensi.text) if self.ids.tensi.text else 120
            nadi = int(self.ids.nadi.text) if self.ids.nadi.text else 80
            suhu = float(self.ids.suhu.text) if self.ids.suhu.text else 36.5
        except:
            MDDialog(title="Input Tidak Valid", text="Tensi, Nadi, dan Suhu harus berupa angka!").open()
            return
            
        # Perbaikan Bug Kritis: "Tidak Sadar" = 1
        kesadaran = "1" if self.ids.dropdown_kesadaran.text == "Tidak Sadar/Pingsan" else "2"
        
        app = MDApp.get_running_app()
        
        # Tambah ke Backend
        id_pasien, kategori, deskripsi = tambah_pasien_gui(nama, keluhan, tensi, nadi, suhu, kesadaran, app.perawat, override=False)
        app.sistem_antrean.tambah_ke_antrean(id_pasien, nama, keluhan, kategori, app.perawat, is_override=False)
        estimasi = app.sistem_antrean.hitung_estimasi_tunggu(id_pasien)
        
        # Fungsi aksi ketika tombol OK di-klik
        def tutup_dan_pindah(inst):
            dialog_sukses.dismiss() # Tutup dialog
            
            # Reset Form
            self.ids.nama.text = ""
            self.ids.keluhan.text = ""
            self.ids.tensi.text = ""
            self.ids.nadi.text = ""
            self.ids.suhu.text = ""
            
            # Otomatis pindah ke halaman Dashboard
            self.manager.current = 'dashboard'

        # Tampilkan Notifikasi Sukses (tertahan sampai diklik OK)
        dialog_sukses = MDDialog(
            title="Sukses", 
            text=f"Pasien berhasil terdaftar!\n\nNama: {nama}\nKategori: {deskripsi} (Level {kategori})\nEstimasi Antrean: {estimasi} menit",
            buttons=[
                MDFlatButton(
                    text="OK",
                    theme_text_color="Custom",
                    text_color=(0.18, 0.43, 0.68, 1), # Warna biru aksen
                    on_release=tutup_dan_pindah
                )
            ]
        )
        dialog_sukses.open()

class EmergencyScreen(Screen):
    def override(self):
        nama = self.ids.nama.text.strip()
        kondisi = self.ids.kondisi.text.strip()
        if not nama or not kondisi:
            MDDialog(title="Error", text="Isi nama dan kondisi gawat!").open()
            return
            
        app = MDApp.get_running_app()
        id_pasien, _, _ = tambah_pasien_gui(nama, kondisi, 0, 0, 0.0, "2", app.perawat, override=True)
        app.sistem_antrean.tambah_ke_antrean(id_pasien, nama, kondisi, 1, app.perawat, is_override=True)
        
        MDDialog(title="EMERGENCY", text="Pasien Kritis Berhasil Ditambahkan ke Urutan Terdepan!").open()
        
        self.ids.nama.text = ""
        self.ids.kondisi.text = ""
        
        # Otomatis pindah ke halaman Dashboard
        self.manager.current = 'dashboard'

class MonitorScreen(Screen):
    data_table = None

    def on_enter(self):
        # Saat layar dibuka, langsung tarik data antrean
        Clock.schedule_once(self._init_ui, 0.1)

    def _init_ui(self, dt):
        app = MDApp.get_running_app()
        if app.sistem_antrean is None:
            return

        if not self.data_table and 'table_container' in self.ids:
            self.data_table = MDDataTable(
                size_hint=(1, 1),
                use_pagination=True,
                column_data=[
                    ("No", dp(20)),
                    ("Nama Pasien", dp(40)),
                    ("Keluhan", dp(60)),
                    ("Estimasi", dp(30)),
                    ("Status/Perawat", dp(40))
                ],
                row_data=[]
            )
            self.ids.table_container.add_widget(self.data_table)
        self.refresh()

    def refresh(self):
        app = MDApp.get_running_app()
        if app.sistem_antrean is None:
            return
            
        antrean = app.sistem_antrean.tampilkan_antrean()
        row_data = [(p['nomor'], p['nama'], p['keluhan'], f"{p['estimasi']} mnt", f"Lvl {p['level']} | {p['perawat']}") for p in antrean]
        if self.data_table:
            self.data_table.row_data = row_data

class PanggilScreen(Screen):
    def on_enter(self):
        # Saat layar dibuka, cari pasien di urutan teratas
        Clock.schedule_once(self._init_ui, 0.1)
        
    def _init_ui(self, dt):
        if 'next_patient' in self.ids:
            self.update_next()

    def update_next(self):
        app = MDApp.get_running_app()
        if app.sistem_antrean is None:
            return
            
        antrean = app.sistem_antrean.tampilkan_antrean()
        if antrean:
            p = antrean[0]
            self.ids.next_patient.text = p['nama']
            self.ids.next_level.text = f"Level {p['level']}"
            self.ids.next_keluhan.text = f"Keluhan: {p['keluhan']}"
            self.ids.next_perawat.text = f"Perawat: {p['perawat']}"
            self.ids.panggil_info.text = "Siap dipanggil"
            self.ids.panggil_box.md_bg_color = (1, 1, 1, 1) # Reset background
        else:
            self.ids.next_patient.text = "-"
            self.ids.next_level.text = "-"
            self.ids.next_keluhan.text = ""
            self.ids.next_perawat.text = ""
            self.ids.panggil_info.text = "Antrean kosong"

    def panggil(self):
        app = MDApp.get_running_app()
        hasil, pesan = app.sistem_antrean.panggil_pasien_next(app.dokter)
        
        if hasil:
            self.ids.panggil_info.text = f"Memanggil: {hasil['nama']} (Level {hasil['level']})\nSilakan ke ruang periksa Dokter {app.dokter}."
            self.ids.panggil_box.md_bg_color = (0.8, 1, 0.8, 1) # Berubah hijau
        else:
            MDDialog(title="Info", text=pesan).open()
            
        self.update_next()

class RekamMedisScreen(Screen):
    data_table = None

    def on_enter(self):
        # Saat layar dibuka, tarik seluruh data rekam medis
        Clock.schedule_once(self._init_ui, 0.1)

    def _init_ui(self, dt):
        if not self.data_table and 'table_container' in self.ids:
            self.data_table = MDDataTable(
                size_hint=(1, 1),
                use_pagination=True,
                column_data=[
                    ("ID", dp(10)),
                    ("Nama Pasien", dp(30)),
                    ("Keluhan", dp(35)),
                    ("Triase", dp(15)),
                    ("Nadi", dp(15)),
                    ("Tensi", dp(15)),
                    ("Status", dp(20)),
                    ("Perawat", dp(25)), # Tambahan kolom Perawat
                    ("Dokter", dp(25))   # Tambahan kolom Dokter
                ],
                row_data=[]
            )
            self.ids.table_container.add_widget(self.data_table)
        self.refresh()

    def refresh(self, status_filter=None):
        records = get_all_pasien_records()
        if status_filter:
            records = [r for r in records if r[7] == status_filter]
            
        # r[8] adalah nama_perawat, r[9] adalah nama_dokter dari igd.py
        row_data = [(r[0], r[1], r[2], f"Lvl {r[6]}", r[4], r[3], r[7], r[8], r[9]) for r in records]
        if self.data_table:
            self.data_table.row_data = row_data

class GrafikScreen(Screen):
    def on_enter(self):
        # Saat layar dibuka, perbarui grafik
        Clock.schedule_once(self._init_ui, 0.1)

    def _init_ui(self, dt):
        if 'total_label' in self.ids:
            self.update_charts()

    def update_charts(self):
        data = get_chart_data()
        self.ids.total_label.text = str(data['total'])
        self.ids.menunggu_label.text = str(data['menunggu'])
        self.ids.diperiksa_label.text = str(data['diperiksa'])
        self.ids.kritis_label.text = str(data['level_kritis'])

        # Donut Chart
        box_donut = self.ids.donut_chart_box
        box_donut.clear_widgets()
        box_donut.add_widget(DonutChartWidget(distribusi=data['distribusi']))
        
        # Bar Chart 
        box_bar = self.ids.bar_chart_box
        box_bar.clear_widgets()
        fig2, ax2 = plt.subplots(figsize=(4, 3))
        status_labels = ['Menunggu', 'Diperiksa']
        status_counts = [data['menunggu'], data['diperiksa']]
        ax2.bar(status_labels, status_counts, color=['#8b0000', '#0E4B7E'])
        box_bar.add_widget(KivyImage(texture=fig_to_kivy_texture(fig2)))
        plt.close(fig2)


# ================== KV STRING (TIDAK ADA DESAIN YANG DIRUBAH) ==================
KV = '''
#:kivy 2.0
#:import dp kivy.metrics.dp
#:import os os

# COLOR PALETTE VARIABLES
#:set COLOR_BG [0.92, 0.95, 0.98, 1] 
#:set COLOR_SIDEBAR [0.055, 0.294, 0.494, 1]
#:set COLOR_SIDEBAR_HEADER [0.659, 0.125, 0.145, 1]
#:set COLOR_ACCENT_BLUE [0.18, 0.43, 0.68, 1]
#:set COLOR_ACCENT_RED [0.55, 0.0, 0.0, 1]
#:set COLOR_WHITE [1, 1, 1, 1]

<SidebarButton@MDFlatButton>:
    size_hint_x: 1
    halign: "left"
    theme_text_color: "Custom"
    text_color: COLOR_WHITE
    font_style: "Button"
    padding: dp(15)

RootScreenManager:
    id: root_sm
    SplashScreen:
    LoginScreen:
    MainAppScreen:

<SplashScreen>:
    name: 'splash'
    FloatLayout:
        FitImage:
            source: 'bg.jpg' if os.path.exists('bg.jpg') else ''
        MDBoxLayout:
            orientation: 'vertical'
            pos_hint: {'center_x': 0.5, 'center_y': 0.55} # Diubah jadi 0.55 agar seluruh blok agak naik sedikit
            size_hint: 0.8, None
            height: self.minimum_height # Memaksa kotak memeluk elemen di dalamnya
            spacing: dp(10) # Jarak antara judul dan deskripsi
            
            MDLabel:
                text: "SISTEM MANAJEMEN ANTREAN IGD"
                halign: 'center'
                font_style: 'H4'
                theme_text_color: 'Custom'
                text_color: COLOR_WHITE
                bold: True
                adaptive_height: True # Mencegah judul makan tempat terlalu banyak
                
            MDLabel:
                text: "Sistem ini dirancang untuk membantu tenaga medis IGD dalam mengelola antrean pasien secara terstruktur dan berprioritas. Setiap pasien ditempatkan dalam antrean berdasarkan tingkat kegawatan yang dinilai otomatis dari tanda vital."
                halign: 'center'
                theme_text_color: 'Custom'
                text_color: COLOR_WHITE
                adaptive_height: True # Mencegah teks makan tempat terlalu banyak
            
            # Spacer (ruang kosong penengah antara teks dan tombol)
            Widget:
                size_hint_y: None
                height: dp(30)
                
            MDRoundFlatButton:
                text: "START"
                pos_hint: {'center_x': 0.5}
                text_color: COLOR_SIDEBAR
                md_bg_color: COLOR_WHITE
                font_style: "H6"
                on_release: root.go_to_login()

<LoginScreen>:
    name: 'login'
    FloatLayout:
        FitImage:
            source: 'bg.jpg' if os.path.exists('bg.jpg') else ''
        MDCard:
            orientation: 'vertical'
            padding: dp(30)
            spacing: dp(20)
            size_hint: 0.6, 0.6
            pos_hint: {'center_x': 0.5, 'center_y': 0.5}
            md_bg_color: 0.9, 0.9, 0.9, 0.85
            radius: [20]
            MDLabel:
                text: "Set Identitas Shift"
                halign: 'center'
                font_style: 'H5'
                bold: True
                theme_text_color: "Custom"
                text_color: COLOR_SIDEBAR
            MDLabel:
                text: "Masukkan Identitas Petugas Jaga untuk Sesi Ini"
                halign: 'center'

            MDTextField:
                id: perawat
                hint_text: "Nama Perawat Bertugas"
                mode: "fill"
                fill_color_normal: COLOR_WHITE
                radius: [15]
                icon_left: "account"        # Mendorong teks ke kanan + ikon profil
                active_line: False          # Menghilangkan garis bawah
            MDTextField:
                id: dokter
                hint_text: "Nama Dokter Utama"
                mode: "fill"
                fill_color_normal: COLOR_WHITE
                radius: [15]
                icon_left: "stethoscope"    # Mendorong teks ke kanan + ikon dokter
                active_line: False          # Menghilangkan garis bawah
            MDRoundFlatButton:
                text: "LOGIN"
                pos_hint: {'center_x': 0.5}
                text_color: COLOR_SIDEBAR
                md_bg_color: COLOR_WHITE
                font_style: "H6"
                on_release: root.login()

<MainAppScreen>:
    name: 'main_app'
    MDBoxLayout:
        orientation: 'horizontal'
        
        # ---------------- SIDEBAR ----------------
        MDBoxLayout:
            orientation: 'vertical'
            size_hint_x: 0.25
            md_bg_color: COLOR_SIDEBAR
            
            MDBoxLayout:
                size_hint_y: None
                height: dp(80)
                md_bg_color: COLOR_SIDEBAR_HEADER
                padding: dp(15)
                MDLabel:
                    text: "Emergency System\\nManajemen antrian IGD"
                    theme_text_color: "Custom"
                    text_color: COLOR_WHITE
                    bold: True
                    
            MDBoxLayout:
                size_hint_y: None
                height: dp(80)
                padding: dp(10)
                MDCard:
                    md_bg_color: COLOR_ACCENT_BLUE
                    orientation: 'vertical'
                    padding: dp(5)
                    MDLabel:
                        text: "Shift Aktif"
                        theme_text_color: "Custom"
                        text_color: COLOR_WHITE
                        font_style: "Caption"
                    MDLabel:
                        id: sidebar_perawat
                        text: "Perawat: -"
                        theme_text_color: "Custom"
                        text_color: COLOR_WHITE
                        font_style: "Caption"
                    MDLabel:
                        id: sidebar_dokter
                        text: "Dokter: -"
                        theme_text_color: "Custom"
                        text_color: COLOR_WHITE
                        font_style: "Caption"
                        
            ScrollView:
                MDBoxLayout:
                    orientation: 'vertical'
                    size_hint_y: None
                    height: self.minimum_height
                    spacing: dp(5)
                    padding: dp(10)
                    SidebarButton:
                        text: "  Dashboard"
                        icon: "view-dashboard"
                        on_release: root.nav_to('dashboard')
                    SidebarButton:
                        text: "  Daftar Pasien Baru"
                        on_release: root.nav_to('daftar_pasien')
                    SidebarButton:
                        text: "  Emergency Override"
                        on_release: root.nav_to('emergency')
                    Widget:
                        size_hint_y: None
                        height: dp(2)
                        canvas:
                            Color:
                                rgba: 1,1,1,0.2
                            Rectangle:
                                pos: self.pos
                                size: self.size
                    SidebarButton:
                        text: "  Monitor Antrean"
                        on_release: root.nav_to('monitor')
                    SidebarButton:
                        text: "  Panggil Pasien"
                        on_release: root.nav_to('panggil')
                    Widget:
                        size_hint_y: None
                        height: dp(2)
                        canvas:
                            Color:
                                rgba: 1,1,1,0.2
                            Rectangle:
                                pos: self.pos
                                size: self.size
                    SidebarButton:
                        text: "  Rekam Medis Log"
                        on_release: root.nav_to('rekam_medis')
                    SidebarButton:
                        text: "  Grafik Analitik"
                        on_release: root.nav_to('grafik')
                    
            MDBoxLayout:
                size_hint_y: None
                height: dp(60)
                padding: dp(10)
                SidebarButton:
                    text: "  Reset Database"
                    text_color: 1, 0.3, 0.3, 1
                    on_release: root.reset_database()
                    
        # ---------------- MAIN CONTENT AREA ----------------
        MDBoxLayout:
            orientation: 'vertical'
            size_hint_x: 0.75
            md_bg_color: COLOR_BG
            
            ScreenManager:
                id: content_sm
                DashboardScreen:
                DaftarPasienScreen:
                EmergencyScreen:
                MonitorScreen:
                PanggilScreen:
                RekamMedisScreen:
                GrafikScreen:

<DashboardScreen>:
    name: 'dashboard'
    MDBoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(20)
        MDLabel:
            text: "Dashboard IGD"
            font_style: "H4"
            bold: True
            theme_text_color: "Custom"
            text_color: COLOR_SIDEBAR
            size_hint_y: None
            height: dp(40)
            
        MDBoxLayout:
            size_hint_y: None
            height: dp(100)
            spacing: dp(20)
            MDCard:
                padding: dp(15)
                orientation: 'vertical'
                elevation: 1
                MDLabel:
                    text: "TOTAL PASIEN"
                    font_style: "Caption"
                MDLabel:
                    id: total_label
                    text: "0"
                    font_style: "H4"
                    theme_text_color: "Error"
            MDCard:
                padding: dp(15)
                orientation: 'vertical'
                elevation: 1
                MDLabel:
                    text: "MENUNGGU"
                    font_style: "Caption"
                MDLabel:
                    id: menunggu_label
                    text: "0"
                    font_style: "H4"
                    theme_text_color: "Custom"
                    text_color: 0.8, 0.4, 0, 1
            MDCard:
                padding: dp(15)
                orientation: 'vertical'
                elevation: 1
                MDLabel:
                    text: "DIPERIKSA"
                    font_style: "Caption"
                MDLabel:
                    id: diperiksa_label
                    text: "0"
                    font_style: "H4"
                    theme_text_color: "Custom"
                    text_color: 0, 0.6, 0, 1
            MDCard:
                padding: dp(15)
                orientation: 'vertical'
                elevation: 1
                MDLabel:
                    text: "LEVEL KRITIS (1-2)"
                    font_style: "Caption"
                MDLabel:
                    id: kritis_label
                    text: "0"
                    font_style: "H4"
            
        MDBoxLayout:
            spacing: dp(20)
            size_hint_y: 0.4
            MDCard:
                orientation: 'vertical'
                padding: dp(10)
                elevation : 1
                MDLabel:
                    text: "Distribusi Triase"
                    bold: True
                    size_hint_y: 0.2
                BoxLayout:
                    id: donut_chart_box
                    size_hint_y: 0.8
            MDCard:
                orientation: 'vertical'
                padding: dp(10)
                elevation: 1
                MDLabel:
                    text: "Status Pasien"
                    bold: True
                    size_hint_y: 0.2
                BoxLayout:
                    id: bar_chart_box
                    size_hint_y: 0.8
                    
        MDCard:
            orientation: 'vertical'
            size_hint_y: 0.4
            md_bg_color: COLOR_ACCENT_BLUE
            padding: dp(10)
            elevation: 1
            MDBoxLayout:
                size_hint_y: None
                height: dp(40)
                MDLabel:
                    text: "Antrean Aktif IGD"
                    theme_text_color: "Custom"
                    text_color: COLOR_WHITE
                    bold: True
                MDRaisedButton:
                    text: "Refresh"
                    md_bg_color: COLOR_SIDEBAR
                    on_release: root.update_queue_list()
            MDCard:
                md_bg_color: COLOR_WHITE
                padding: dp(10)
                elevation: 1
                ScrollView:
                    MDBoxLayout:
                        id: queue_list_container
                        orientation: 'vertical'
                        size_hint_y: None
                        height: self.minimum_height

<DaftarPasienScreen>:
    name: 'daftar_pasien'
    MDBoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(10)
        MDLabel:
            text: "Daftar Pasien Baru"
            font_style: "H4"
            bold: True
            theme_text_color: "Custom"
            text_color: COLOR_SIDEBAR
            size_hint_y: None
            height: dp(40)
            
        MDCard:
            orientation: 'vertical'
            padding: dp(20)
            spacing: dp(15)
            elevation: 1
            MDBoxLayout:
                size_hint_y: None
                height: dp(50)
                md_bg_color: COLOR_ACCENT_BLUE
                padding: dp(10)
                MDLabel:
                    text: "Pendaftaran Pasien Regular"
                    theme_text_color: "Custom"
                    text_color: COLOR_WHITE
                    bold: True
                    
            MDBoxLayout:
                spacing: dp(20)
                size_hint_y: None
                height: dp(60)
                MDTextField:
                    id: nama
                    hint_text: "NAMA PASIEN"
                    mode: "rectangle"
                MDTextField:
                    id: keluhan
                    hint_text: "KELUHAN UTAMA"
                    mode: "rectangle"
                    
            MDCard:
                orientation: 'vertical'
                md_bg_color: 0.36, 0.54, 0.73, 1
                padding: dp(40)
                spacing: dp(20)
                MDLabel:
                    text: "Pemeriksaan Tanda Vital"
                    theme_text_color: "Custom"
                    text_color: COLOR_WHITE
                    bold: True
                    size_hint_y: None
                    height: dp(40)
                MDBoxLayout:
                    spacing: dp(20)
                    size_hint_y: None
                    height: dp(35)
                    MDTextField:
                        id: tensi
                        hint_text: "Tensi (mmHg)"
                        mode: "fill"
                        radius:[15]
                        fill_color_normal: COLOR_WHITE
                    MDTextField:
                        id: nadi
                        hint_text: "Nadi (BPM)"
                        mode: "fill"
                        radius:[15] 
                        fill_color_normal: COLOR_WHITE
                    MDTextField:
                        id: suhu
                        hint_text: "Suhu Tubuh ( C )"
                        mode: "fill"
                        radius:[15]
                        fill_color_normal: COLOR_WHITE
                MDLabel:
                    text: "STATUS KESADARAN"
                    theme_text_color: "Custom"
                    text_color: COLOR_WHITE
                    size_hint_y: None
                    height: dp(20)
                MDBoxLayout:
                    size_hint_y: None
                    height: dp(50)
                    MDCard:
                        md_bg_color: COLOR_WHITE
                        padding: dp(5)
                        MDFlatButton:
                            id: dropdown_kesadaran
                            text: "Sadar Penuh"
                            size_hint_x: 1
                            on_release: root.menu.open()
                            
            MDBoxLayout:
                size_hint_y: None
                height: dp(50)
                Widget:
                MDRaisedButton:
                    text: "Daftarkan Pasien"
                    md_bg_color: COLOR_WHITE
                    text_color: 0,0,0,1
                    line_color: 0,0,0,1
                    on_release: root.daftar()
                Widget:

<EmergencyScreen>:
    name: 'emergency'
    MDBoxLayout:
        orientation: 'vertical'
        padding: dp(17)
        spacing: dp(17)
        MDLabel:
            text: "Emergency Override"
            font_style: "H4"
            bold: True
            theme_text_color: "Custom"
            text_color: COLOR_SIDEBAR
            size_hint_y: None
            height: dp(40)
            
        MDCard:
            size_hint_y: None
            height: dp(100)
            md_bg_color: 0.95, 0.85, 0.85, 1
            line_color: COLOR_ACCENT_RED
            padding: dp(15)
            elevation: 1
            MDLabel:
                text: "Emergency Override - Pasien Kritis\\nPasien akan langsung ditempatkan di urutan TERDEPAN antrean dengan Level Triase 1 (Resusitasi)"
                theme_text_color: "Error"
                bold: True
                
        MDCard:
            orientation: 'vertical'
            padding: dp(35)
            spacing: dp(35)
            elevation: 1
            MDBoxLayout:
                size_hint_y: None
                height: dp(60)
                md_bg_color: COLOR_ACCENT_RED
                padding: dp(20)
                MDLabel:
                    text: "EMERGENCY OVERRIDE FORM"
                    theme_text_color: "Custom"
                    text_color: COLOR_WHITE
                    bold: True
            MDBoxLayout:
                spacing: dp(20)
                size_hint_y: None
                height: dp(60)
                MDTextField:
                    id: nama
                    hint_text: "NAMA PASIEN KRITIS"
                    mode: "rectangle"
                MDTextField:
                    id: kondisi
                    hint_text: "KONDISI GAWAT"
                    mode: "rectangle"
            MDRaisedButton:
                text: "AKTIFKAN EMERGENCY OVERRIDE"
                md_bg_color: 0, 0, 0, 1
                size_hint_x: 1
                on_release: root.override()
            
            MDCard:
                id: status_box
                size_hint_y: None
                height: dp(60)
                md_bg_color: COLOR_WHITE 
                padding: dp(10)
                MDLabel:
                    id: status_override
                    text: ""
                    halign: "center"
                    theme_text_color: "Error"
                    bold: True

<MonitorScreen>:
    name: 'monitor'
    MDBoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(20)
        MDLabel:
            text: "Monitor Antrean"
            font_style: "H4"
            bold: True
            theme_text_color: "Custom"
            text_color: COLOR_SIDEBAR
            size_hint_y: None
            height: dp(40)
            
        MDCard:
            orientation: 'vertical'
            MDBoxLayout:
                size_hint_y: None
                height: dp(60)
                md_bg_color: COLOR_ACCENT_BLUE
                padding: dp(15)
                MDLabel:
                    text: "Antrean Aktif IGD"
                    theme_text_color: "Custom"
                    text_color: COLOR_WHITE
                    bold: True
                MDRaisedButton:
                    text: "Refresh"
                    md_bg_color: COLOR_SIDEBAR
                    on_release: root.refresh()
            AnchorLayout:
                id: table_container
                padding: dp(10)

<PanggilScreen>:
    name: 'panggil'
    MDBoxLayout:
        orientation: 'vertical'
        padding: dp(30)               # Dikurangi dari dp(60) agar tidak terlalu sempit ke dalam
        spacing: dp(25)
        
        MDLabel:
            text: "Panggil Pasien"
            font_style: "H4"
            bold: True
            theme_text_color: "Custom"
            text_color: COLOR_SIDEBAR
            size_hint_y: None
            height: dp(40)
            
        MDCard:
            orientation: 'vertical'
            padding: dp(25)
            spacing: dp(20)
            size_hint_x: 0.95         # Menyesuaikan lebar card agar sama dengan Daftar Pasien
            
            # --- MODIFIKASI DISINI ---
            size_hint_y: None         # Mematikan ukuran otomatis vertikal
            height: self.minimum_height # Tinggi kartu otomatis pas dengan total tinggi widget di dalamnya
            
            pos_hint: {"center_x": 0.5, "top": 1} # Ditambahkan "top": 1 agar kartu merapat ke atas screen
            elevation: 1             # Memberikan sedikit shadow tipis yang elegan
            radius: [12, 12, 12, 12]  # Membuat sudut melengkung estetik

            # --- Header Bar ---
            MDBoxLayout:
                size_hint_y: None
                height: dp(50)
                md_bg_color: COLOR_ACCENT_BLUE
                padding: [dp(20), 0, 0, 0]
                radius: [8, 8, 8, 8]
                MDLabel:
                    text: "Panggil Pasien"
                    theme_text_color: "Custom"
                    text_color: COLOR_WHITE
                    bold: True
                    font_style: "Subtitle1"

            MDLabel:
                text: "PASIEN BERIKUTNYA"
                size_hint_y: None
                height: dp(20)
                bold: True
                font_style: "Caption"
                theme_text_color: "Secondary"

            # --- Informasi Pasien Berikutnya ---
            MDCard:
                size_hint_y: None
                height: dp(100)       # Dinaikkan ke 100dp agar text tidak menumpuk/terpotong
                md_bg_color: 0.9, 0.95, 1, 1 
                padding: dp(15)
                radius: [8, 8, 8, 8]
                elevation: 0
                
                MDBoxLayout:
                    orientation: 'vertical'
                    spacing: dp(8)
                    
                    # Baris Atas: Nama & Level
                    MDBoxLayout:
                        orientation: 'horizontal'
                        MDLabel:
                            id: next_patient
                            text: "-"
                            bold: True
                            font_style: "Body1"
                        MDLabel:
                            id: next_level
                            text: "-"
                            halign: "right"
                            bold: True
                            theme_text_color: "Secondary"

                    # Baris Bawah: Keluhan & Perawat
                    MDBoxLayout:
                        orientation: 'horizontal'
                        MDLabel:
                            id: next_keluhan
                            text: "Keluhan: -"
                            theme_text_color: "Secondary"
                            font_style: "Body2"
                        MDLabel:
                            id: next_perawat
                            text: "Perawat: -"
                            halign: "right"
                            theme_text_color: "Secondary"
                            font_style: "Body2"

            # --- Tombol Panggil ---
            MDRaisedButton:
                text: "Panggil Pasien Sekarang"
                md_bg_color: 0.05, 0.1, 0.2, 1   # Mengubah hitam pekat menjadi Navy gelap elegan
                size_hint_x: 1
                size_hint_y: None      # Ditambahkan agar tinggi tombol konsisten
                height: dp(48)
                font_style: "Button"
                on_release: root.panggil()
                
            # --- Box Informasi Panggilan ---
            MDCard:
                id: panggil_box
                size_hint_y: None
                height: dp(60)
                md_bg_color: COLOR_WHITE 
                padding: dp(15)
                line_color: 0, 0.6, 0, 0.4
                line_width: dp(1)
                radius: [8, 8, 8, 8]
                elevation: 0
                
                MDLabel:
                    id: panggil_info
                    text: "Antrean kosong"     # Default teks saat kosong
                    theme_text_color: "Custom"
                    text_color: 0, 0.5, 0, 1
                    bold: True
                    halign: "center"          # Membuat teks "Antrean kosong" berada tepat di tengah
                    valign: "center"  

        # --- Widget Spacer (Opsional) ---
        MDWidget:
            # Widget kosong ini akan menyerap sisa space di paling bawah layar
            # sehingga MDCard utama Anda tetap rapi di atas dan tidak melar.
            size_hint_y: 1
<RekamMedisScreen>:
    name: 'rekam_medis'
    MDBoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(20)
        MDLabel:
            text: "Rekam Medis Log"
            font_style: "H4"
            bold: True
            theme_text_color: "Custom"
            text_color: COLOR_SIDEBAR
            size_hint_y: None
            height: dp(40)
            
        MDCard:
            orientation: 'vertical'
            MDBoxLayout:
                size_hint_y: None
                height: dp(60)
                md_bg_color: COLOR_ACCENT_BLUE
                padding: dp(15)
                MDLabel:
                    text: "Rekam Medis & Log Akuntabilitas"
                    theme_text_color: "Custom"
                    text_color: COLOR_WHITE
                    bold: True
                MDRaisedButton:
                    text: "Refresh"
                    md_bg_color: COLOR_SIDEBAR
                    on_release: root.refresh()
            MDBoxLayout:
                size_hint_y: None
                height: dp(50)
                padding: dp(10)
                spacing: dp(10)
                MDRoundFlatButton:
                    text: "Semua"
                    on_release: root.refresh()
                MDRoundFlatButton:
                    text: "Menunggu"
                    on_release: root.refresh("Menunggu")
                MDRoundFlatButton:
                    text: "Diperiksa"
                    on_release: root.refresh("Diperiksa")
            AnchorLayout:
                id: table_container
                padding: dp(10)

<GrafikScreen>:
    name: 'grafik'
    MDBoxLayout:
        orientation: 'vertical'
        padding: dp(20)
        spacing: dp(20)
        MDLabel:
            text: "Grafik Analitik"
            font_style: "H4"
            bold: True
            theme_text_color: "Custom"
            text_color: COLOR_SIDEBAR
            size_hint_y: None
            height: dp(40)
            
        MDBoxLayout:
            size_hint_y: None
            height: dp(100)
            spacing: dp(20)
            MDCard:
                padding: dp(15)
                orientation: 'vertical'
                elevation: 1
                MDLabel:
                    text: "TOTAL PASIEN"
                    font_style: "Caption"
                MDLabel:
                    id: total_label
                    text: "0"
                    font_style: "H4"
                    theme_text_color: "Error"
            MDCard:
                padding: dp(15)
                orientation: 'vertical'
                elevation: 1
                MDLabel:
                    text: "MENUNGGU"
                    font_style: "Caption"
                MDLabel:
                    id: menunggu_label
                    text: "0"
                    font_style: "H4"
                    theme_text_color: "Custom"
                    text_color: 0.8, 0.4, 0, 1
            MDCard:
                padding: dp(15)
                orientation: 'vertical'
                elevation: 1
                MDLabel:
                    text: "DIPERIKSA"
                    font_style: "Caption"
                MDLabel:
                    id: diperiksa_label
                    text: "0"
                    font_style: "H4"
                    theme_text_color: "Custom"
                    text_color: 0, 0.6, 0, 1
            MDCard:
                padding: dp(15)
                orientation: 'vertical'
                elevation: 1
                MDLabel:
                    text: "LEVEL KRITIS (1-2)"
                    font_style: "Caption"
                MDLabel:
                    id: kritis_label
                    text: "0"
                    font_style: "H4"
                    
        MDBoxLayout:
            spacing: dp(20)
            MDCard:
                orientation: 'vertical'
                padding: dp(10)
                elevation: 1
                MDLabel:
                    text: "Distribusi Triase"
                    bold: True
                    size_hint_y: 0.1
                BoxLayout:
                    id: donut_chart_box
                    size_hint_y: 0.9
            MDCard:
                orientation: 'vertical'
                padding: dp(10)
                elevation: 1
                MDLabel:
                    text: "Status Pasien"
                    bold: True
                    size_hint_y: 0.1
                BoxLayout:
                    id: bar_chart_box
                    size_hint_y: 0.9
'''

# ================== APP ==================
class IGDApp(MDApp):
    perawat = ""
    dokter = ""
    sistem_antrean = None

    def build(self):
        self.title = "Sistem Manajemen Antrean IGD"
        self.theme_cls.primary_palette = "Blue"
        self.theme_cls.theme_style = "Light" 
        return Builder.load_string(KV)

if __name__ == '__main__':
    IGDApp().run()