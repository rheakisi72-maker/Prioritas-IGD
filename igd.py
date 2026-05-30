import sqlite3

def inisialisasi_database():
    conn = sqlite3.connect("igd_hospital.db")
    cursor = conn.cursor()
    
    # Tabel Utama
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pasien_igd (
            id_pasien INTEGER PRIMARY KEY AUTOINCREMENT, 
            nama TEXT NOT NULL,                         
            keluhan TEXT,
            tensi_sistolik INTEGER,
            nadi INTEGER,
            suhu REAL,
            kategori_triase INTEGER NOT NULL,            
            status TEXT DEFAULT 'Menunggu',
            nama_perawat TEXT,                  
            nama_dokter TEXT DEFAULT 'Belum Ada' 
        )
    """)
    
    # TABEL ARSIP BARU (Ditambahkan tanpa mengubah tabel utama)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS riwayat_pasien_igd (
            id_arsip INTEGER PRIMARY KEY AUTOINCREMENT,
            id_pasien_asli INTEGER, 
            nama TEXT,                         
            keluhan TEXT,
            tensi_sistolik INTEGER,
            nadi INTEGER,
            suhu REAL,
            kategori_triase INTEGER,            
            status TEXT,
            nama_perawat TEXT,                  
            nama_dokter TEXT
        )
    """)
    conn.commit()
    conn.close()
    print("Database dan Tabel sukses diinisialisasi!")

class NodePasien:
    def __init__(self, id_pasien, nama, keluhan, kategori_triase, nama_perawat):
        self.id_pasien = id_pasien       
        self.nama = nama                 
        self.keluhan = keluhan           
        self.kategori_triase = kategori_triase 
        self.nama_perawat = nama_perawat 
        self.waktu_tunggu = 0            
        self.next = None                 

class SistemAntreanIGD:
    def __init__(self):
        self.head = None 

    def tambah_ke_antrean(self, id_pasien, nama, keluhan, kategori_triase, nama_perawat, is_override=False):
        new_node = NodePasien(id_pasien, nama, keluhan, kategori_triase, nama_perawat)

        if is_override:
            new_node.kategori_triase = 1 
            new_node.next = self.head
            self.head = new_node
            print(f"\n⚡ [OVERRIDE] {nama} KONDISI KRITIS! Dicatat oleh: Perawat {nama_perawat} -> Urutan TERDEPAN!")
            return

        if self.head is None or kategori_triase < self.head.kategori_triase:
            new_node.next = self.head
            self.head = new_node
            print(f"[Linked List] {nama} (Level {kategori_triase}) masuk di urutan terdepan.")
            return

        current = self.head
        while current.next is not None and current.next.kategori_triase <= kategori_triase:
            current = current.next
        
        new_node.next = current.next
        current.next = new_node
        print(f"[Linked List] {nama} (Level {kategori_triase}) diletakkan sesuai prioritas.")

    def hitung_estimasi_tunggu(self, target_id):
        current = self.head
        total_waktu = 0
        durasi_per_level = {1: 0, 2: 15, 3: 30, 4: 45, 5: 60}
        while current is not None:
            if current.id_pasien == target_id:
                return total_waktu
            total_waktu += durasi_per_level.get(current.kategori_triase, 30)
            current = current.next
        return 0

    def tampilkan_antrean(self):
        if self.head is None:
            print("\n--- Antrean IGD Saat Ini Kosong ---")
            return []

        hasil = []
        current = self.head
        nomor = 1
        while current is not None:
            estimasi = self.hitung_estimasi_tunggu(current.id_pasien)
            hasil.append({
                "nomor": nomor,
                "id": current.id_pasien,
                "nama": current.nama,
                "keluhan": current.keluhan,
                "level": current.kategori_triase,
                "estimasi": estimasi,
                "perawat": current.nama_perawat
            })
            current = current.next
            nomor += 1
        return hasil

    def panggil_pasien_next(self, nama_dokter):
        if self.head is None:
            return None, "Tidak ada pasien dalam antrean."

        pasien_terpanggil = self.head
        info = {
            "id": pasien_terpanggil.id_pasien,
            "nama": pasien_terpanggil.nama,
            "level": pasien_terpanggil.kategori_triase,
            "perawat": pasien_terpanggil.nama_perawat
        }

        conn = sqlite3.connect("igd_hospital.db")
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE pasien_igd 
            SET status = 'Diperiksa', nama_dokter = ? 
            WHERE id_pasien = ?
        """, (nama_dokter, pasien_terpanggil.id_pasien))
        conn.commit()
        conn.close()

        self.head = self.head.next

        # FITUR AGING
        current = self.head
        while current is not None:
            current.waktu_tunggu += 1 
            if current.waktu_tunggu >= 2 and current.kategori_triase > 1:
                prioritas_lama = current.kategori_triase
                current.kategori_triase -= 1 
                current.waktu_tunggu = 0     
                print(f"--- [AGING] Pasien {current.nama} kelamaan mengantre! Naik ke Level {current.kategori_triase} ---")
                
                conn = sqlite3.connect("igd_hospital.db")
                cursor = conn.cursor()
                cursor.execute("UPDATE pasien_igd SET kategori_triase = ? WHERE id_pasien = ?", (current.kategori_triase, current.id_pasien))
                conn.commit()
                conn.close()
                
            current = current.next

        self._restruktur_antrean()
        return info, f"Berhasil memanggil {info['nama']} (Level {info['level']})"

    def _restruktur_antrean(self):
        if self.head is None or self.head.next is None:
            return
        nodes = []
        current = self.head
        while current is not None:
            nodes.append(current)
            current = current.next
        self.head = None
        for node in nodes:
            node.next = None
            if self.head is None or node.kategori_triase < self.head.kategori_triase:
                node.next = self.head
                self.head = node
            else:
                curr = self.head
                while curr.next is not None and curr.next.kategori_triase <= node.kategori_triase:
                    curr = curr.next
                node.next = curr.next
                curr.next = node

    def rebuild_from_db(self):
        """Membangun ulang linked list dari database (untuk sinkronisasi)"""
        conn = sqlite3.connect("igd_hospital.db")
        cursor = conn.cursor()
        cursor.execute("SELECT id_pasien, nama, keluhan, kategori_triase, nama_perawat FROM pasien_igd WHERE status='Menunggu' ORDER BY kategori_triase ASC, id_pasien ASC")
        rows = cursor.fetchall()
        conn.close()

        self.head = None
        for row in reversed(rows):
            id_pasien, nama, keluhan, triase, perawat = row
            new_node = NodePasien(id_pasien, nama, keluhan, triase, perawat)
            new_node.next = self.head
            self.head = new_node
        self._restruktur_antrean()

# ========== FUNGSI TAMBAHAN UNTUK GUI ==========
def tentukan_triase_dari_vital(tensi_sistolik, nadi, suhu, kesadaran):
    """Mengembalikan (kategori, deskripsi) berdasarkan tanda vital"""
    if kesadaran == "1" or tensi_sistolik < 70 or nadi <= 40 or nadi >= 140:
        return 1, "Resusitasi (Skala Merah)"
    elif tensi_sistolik >= 180 or nadi >= 120 or suhu >= 40.0:
        return 2, "Emergensi (Skala Oranye)"
    elif (140 <= tensi_sistolik <= 179) or (101 <= nadi <= 119) or (39.0 <= suhu <= 39.9):
        return 3, "Urgen (Skala Kuning)"
    elif (121 <= tensi_sistolik <= 139) or (37.5 <= suhu <= 38.9):
        return 4, "Kurang Urgen (Skala Hijau)"
    else:
        return 5, "Tidak Urgen (Skala Biru)"

def tambah_pasien_gui(nama, keluhan, tensi_sistolik, nadi, suhu, kesadaran, nama_perawat, override=False):
    """
    Menambahkan pasien ke database dan antrean linked list.
    Mengembalikan (id_pasien, kategori, estimasi)
    """
    if override:
        kategori = 1
        deskripsi = "Resusitasi (OVERRIDE)"
        tensi_sistolik = nadi = suhu = 0
    else:
        kategori, deskripsi = tentukan_triase_dari_vital(tensi_sistolik, nadi, suhu, kesadaran)

    conn = sqlite3.connect("igd_hospital.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO pasien_igd (nama, keluhan, tensi_sistolik, nadi, suhu, kategori_triase, status, nama_perawat)
        VALUES (?, ?, ?, ?, ?, ?, 'Menunggu', ?)
    """, (nama, keluhan, tensi_sistolik, nadi, suhu, kategori, nama_perawat))
    conn.commit()
    id_terakhir = cursor.lastrowid
    conn.close()
    return id_terakhir, kategori, deskripsi

def get_all_pasien_records():
    """Mengambil semua rekam medis untuk log"""
    conn = sqlite3.connect("igd_hospital.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id_pasien, nama, keluhan, tensi_sistolik, nadi, suhu, kategori_triase, status, nama_perawat, nama_dokter FROM pasien_igd ORDER BY id_pasien DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_chart_data():
    """Mengembalikan data statistik untuk chart dan dashboard"""
    conn = sqlite3.connect("igd_hospital.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM pasien_igd")
    total_pasien = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM pasien_igd WHERE status = 'Menunggu'")
    menunggu = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM pasien_igd WHERE status = 'Diperiksa'")
    diperiksa = cursor.fetchone()[0]
    
    # Level kritis (1-2)
    cursor.execute("SELECT COUNT(*) FROM pasien_igd WHERE kategori_triase IN (1,2)")
    level_kritis = cursor.fetchone()[0]
    
    # Distribusi per level
    distribusi = {}
    for i in range(1, 6):
        cursor.execute("SELECT COUNT(*) FROM pasien_igd WHERE kategori_triase = ?", (i,))
        distribusi[i] = cursor.fetchone()[0]
    conn.close()
    
    return {
        "total": total_pasien,
        "menunggu": menunggu,
        "diperiksa": diperiksa,
        "level_kritis": level_kritis,
        "distribusi": distribusi
    }

# FUNGSI YANG DIUBAH UNTUK PROSES ARSIP & RESET SEQUENCE
def reset_seluruh_database(sistem_antrean):
    conn = sqlite3.connect("igd_hospital.db")
    cursor = conn.cursor()
    
    # 1. Salin data dari tabel utama ke tabel arsip riwayat_pasien_igd sebelum dihapus
    cursor.execute("""
        INSERT INTO riwayat_pasien_igd (id_pasien_asli, nama, keluhan, tensi_sistolik, nadi, suhu, kategori_triase, status, nama_perawat, nama_dokter)
        SELECT id_pasien, nama, keluhan, tensi_sistolik, nadi, suhu, kategori_triase, status, nama_perawat, nama_dokter 
        FROM pasien_igd
    """)
    
    # 2. Hapus semua data di tabel utama
    cursor.execute("DELETE FROM pasien_igd")
    
    # 3. Hapus baris sequence agar AUTOINCREMENT kembali dari awal (1)
    cursor.execute("DELETE FROM sqlite_sequence WHERE name='pasien_igd'")
    
    conn.commit()
    conn.close()
    if sistem_antrean:
        sistem_antrean.head = None
    print("\n♻️ [Sistem] Sukses! Seluruh rekam medis telah diarsipkan, tabel utama dikosongkan dan hitungan ID direset kembali ke 1!")

# Inisialisasi database saat modul diimport
inisialisasi_database()