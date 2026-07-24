"""
EXAM ANALYTICS STUDIO - CLEAN VERSION WITHOUT WORD EDITOR
Run with: streamlit run test.py
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
import os
import re
from datetime import datetime, timedelta
from io import BytesIO
import zipfile
import tempfile
import shutil
from pathlib import Path
from PIL import Image
import base64
import warnings
warnings.filterwarnings('ignore')

# For PDF generation
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch, cm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# For Barcode
try:
    import barcode
    from barcode.writer import ImageWriter
    BARCODE_AVAILABLE = True
except ImportError:
    BARCODE_AVAILABLE = False

# ============================================
# CONFIGURATION
# ============================================

st.set_page_config(
    page_title="Exam Analytics Studio Pro",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

CATEGORY_COLORS = {
    'UR': '#1f77b4',
    'OBC': '#ff7f0e',
    'SC': '#2ca02c',
    'ST': '#d62728',
    'EWS': '#9467bd'
}

SHIFT_LABELS = {1: 'Shift I', 2: 'Shift II', 3: 'Shift III'}

# ============================================
# HELPER FUNCTIONS
# ============================================

def safe_get_value(dict_obj, key, default='N/A'):
    if dict_obj is None:
        return default
    value = dict_obj.get(key, default)
    if value is None or pd.isna(value):
        return default
    if isinstance(value, str) and value.strip() == '':
        return default
    return value

def safe_get_int(dict_obj, key, default=0):
    if dict_obj is None:
        return default
    value = dict_obj.get(key, default)
    if value is None or pd.isna(value):
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def format_date_safe(value):
    if value is None or pd.isna(value):
        return 'N/A'
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.strftime('%d-%b-%Y')
    return str(value)

def generate_barcode(roll_number):
    if not BARCODE_AVAILABLE:
        return None
    try:
        code128 = barcode.get_barcode_class('code128')
        barcode_buffer = BytesIO()
        barcode_obj = code128(str(roll_number), writer=ImageWriter())
        barcode_obj.write(barcode_buffer, {
            'write_text': True,
            'text_distance': 2,
            'font_size': 8,
            'module_width': 0.2,
            'module_height': 8,
            'quiet_zone': 4
        })
        barcode_buffer.seek(0)
        return barcode_buffer
    except Exception as e:
        return None

# ============================================
# COLUMN MAPPING
# ============================================

class ColumnMapper:
    COLUMN_PATTERNS = {
        'reg_number': ['reg_number', 'registration_number', 'registration_no', 'reg_no', 'registration', 'reg', 'application_number', 'application_no', 'app_no', 'regno', 'regno_', 'reg_num'],
        'roll_number': ['roll_number', 'roll_no', 'roll', 'rollnumber', 'rollno'],
        'name': ['name', 'candidate_name', 'full_name', 'applicant_name', 'student_name', 'candidate', 'candidate_name'],
        'gender': ['gender', 'sex'],
        'category': ['category', 'cat', 'caste', 'community', 'category_field'],
        'dob': ['dob', 'date_of_birth', 'birth_date', 'birthdate', 'dob2'],
        'state': ['state', 'candidate_state', 'applicant_state', 'venue_state', 'present_state'],
        'district': ['district', 'candidate_district', 'applicant_district', 'venue_district', 'present_district'],
        'venue_name': ['venue_name', 'venue', 'center_name', 'centre_name', 'exam_center', 'centre', 'center_name', 'venue'],
        'venue_address': ['venue_address', 'address', 'center_address', 'centre_address'],
        'venue_city': ['venue_city', 'city', 'center_city', 'centre_city'],
        'venue_state': ['venue_state', 'center_state', 'centre_state'],
        'venue_code': ['venue_code', 'center_code', 'centre_code', 'venuecode'],
        'shift': ['shift', 'session', 'slot'],
        'exam_date': ['examdate', 'exam_date', 'date', 'exam_date1', 'examdate1', 'examdate'],
        'downloaded': ['downloaded', 'download_status', 'admit_downloaded', 'is_downloaded'],
        'ph': ['ph', 'disability', 'pwbd', 'pwd', 'handicap'],
        'ph_code': ['ph_code', 'disability_code', 'pwbd_code'],
        'mobile': ['mobile', 'phone', 'contact', 'mobile_number', 'phone_number'],
        'email': ['email', 'email_id', 'mail'],
        'father_name': ['father_name', 'father', 'fname'],
        'mother_name': ['mother_name', 'mother', 'mname'],
        'old_center_code': ['old_center_code', 'old_centre_code', 'old_center'],
        'present_address': ['present_address', 'address', 'current_address'],
        'present_district': ['present_district', 'current_district'],
        'present_state': ['present_state', 'current_state'],
        'pincode': ['pincode', 'pin', 'zip', 'postal_code'],
        'remarks': ['remarks', 'remark', 'notes', 'comment'],
        'old_center_name': ['old_center_name', 'old_centre_name'],
        'batch': ['batch', 'batch_no'],
        'is_shifted': ['is_shifted', 'shifted'],
        'venue_district': ['venue_district', 'center_district', 'centre_district'],
        'scribe_required': ['scribe_required', 'scribe_req'],
        'own_scribe': ['own_scribe', 'scribe_own'],
        'scribe_medium': ['scribe_medium', 'scribe_med'],
        'identification_mark': ['identification_mark', 'ident_mark', 'id_mark'],
        'additional_kyc': ['additional_kyc', 'kyc']
    }
    
    @staticmethod
    def detect_columns(df):
        detected = {}
        df_cols_lower = {col.lower(): col for col in df.columns}
        for field, patterns in ColumnMapper.COLUMN_PATTERNS.items():
            for pattern in patterns:
                if pattern in df_cols_lower:
                    detected[field] = df_cols_lower[pattern]
                    break
        return detected
    
    @staticmethod
    def map_columns(df, mapping):
        df_mapped = df.copy()
        rename_dict = {v: k for k, v in mapping.items() if v}
        df_mapped.rename(columns=rename_dict, inplace=True)
        return df_mapped

# ============================================
# PHOTO/SIGNATURE MANAGER
# ============================================

class PhotoManager:
    def __init__(self):
        self.photo_cache = {}
        self.signature_cache = {}
        self.reg_numbers = set()
        self.photo_folder = None
        self.signature_folder = None
        self.processed_zips = set()
        self.total_zips_found = 0
        self.total_zips_processed = 0
        
    def set_photo_folder(self, folder_path):
        if folder_path and os.path.exists(folder_path):
            self.photo_folder = folder_path
            return True
        return False
    
    def set_signature_folder(self, folder_path):
        if folder_path and os.path.exists(folder_path):
            self.signature_folder = folder_path
            return True
        return False
    
    def find_all_zips(self, folder_path):
        zip_files = []
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                if file.lower().endswith('.zip'):
                    zip_files.append(os.path.join(root, file))
        return zip_files
    
    def scan_folder(self, folder_path):
        if not folder_path or not os.path.exists(folder_path):
            return 0, 0
        
        photo_count = 0
        signature_count = 0
        
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_lower = file.lower()
                if '_p.' in file_lower or '_p_' in file_lower:
                    reg_no = self._extract_reg_number(file, '_P')
                    if reg_no:
                        full_path = os.path.join(root, file)
                        self.photo_cache[reg_no] = full_path
                        self.reg_numbers.add(reg_no)
                        photo_count += 1
                elif '_s.' in file_lower or '_s_' in file_lower:
                    reg_no = self._extract_reg_number(file, '_S')
                    if reg_no:
                        full_path = os.path.join(root, file)
                        self.signature_cache[reg_no] = full_path
                        self.reg_numbers.add(reg_no)
                        signature_count += 1
        
        return photo_count, signature_count
    
    def process_zip_recursive(self, zip_path, temp_dir):
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
            
            photos = 0
            sigs = 0
            
            p, s = self.scan_folder(temp_dir)
            photos += p
            sigs += s
            
            nested_zips = []
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.lower().endswith('.zip'):
                        nested_zips.append(os.path.join(root, file))
            
            for nested_zip in nested_zips:
                nested_temp = tempfile.mkdtemp(dir=temp_dir)
                try:
                    p2, s2 = self.process_zip_recursive(nested_zip, nested_temp)
                    photos += p2
                    sigs += s2
                except:
                    pass
                finally:
                    try:
                        shutil.rmtree(nested_temp, ignore_errors=True)
                    except:
                        pass
            
            return photos, sigs
            
        except:
            return 0, 0
    
    def process_all_zips(self, folder_path):
        if not folder_path or not os.path.exists(folder_path):
            return 0, 0
        
        total_photos = 0
        total_signatures = 0
        
        zip_files = self.find_all_zips(folder_path)
        self.total_zips_found = len(zip_files)
        
        if zip_files:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i, zip_path in enumerate(zip_files):
                if zip_path in self.processed_zips:
                    continue
                
                status_text.text(f"Processing: {os.path.basename(zip_path)} ({i+1}/{len(zip_files)})")
                
                temp_dir = tempfile.mkdtemp()
                try:
                    photos, sigs = self.process_zip_recursive(zip_path, temp_dir)
                    total_photos += photos
                    total_signatures += sigs
                    self.processed_zips.add(zip_path)
                    self.total_zips_processed += 1
                except:
                    pass
                finally:
                    shutil.rmtree(temp_dir, ignore_errors=True)
                
                progress_bar.progress((i + 1) / len(zip_files))
            
            status_text.empty()
            progress_bar.progress(1.0)
        
        return total_photos, total_signatures
    
    def process_folder(self, folder_path):
        if not folder_path:
            return {"error": "No folder path provided"}
        
        folder_path = normalize_path(folder_path)
        if not os.path.exists(folder_path):
            return {"error": f"Folder not found: {folder_path}"}
        
        self.set_photo_folder(folder_path)
        self.set_signature_folder(folder_path)
        
        self.processed_zips = set()
        self.total_zips_found = 0
        self.total_zips_processed = 0
        
        photos, sigs = self.scan_folder(folder_path)
        
        total_photos = photos
        total_signatures = sigs
        
        zip_photos, zip_sigs = self.process_all_zips(folder_path)
        total_photos += zip_photos
        total_signatures += zip_sigs
        
        return {
            'photos_found': total_photos,
            'signatures_found': total_signatures,
            'total_candidates': len(self.reg_numbers),
            'zips_found': self.total_zips_found,
            'zips_processed': self.total_zips_processed
        }
    
    def _extract_reg_number(self, filename, suffix):
        name = os.path.splitext(filename)[0]
        if suffix in name:
            parts = name.split(suffix)
            if parts:
                reg_no = parts[0].strip()
                reg_no = reg_no.rstrip('_- ')
                reg_no = re.sub(r'_\d+$', '', reg_no)
                if reg_no:
                    return reg_no
        return None
    
    def get_photo_path(self, reg_number):
        if reg_number is None or pd.isna(reg_number):
            return None
        
        reg_str = str(reg_number).strip()
        
        if reg_str in self.photo_cache:
            if os.path.exists(self.photo_cache[reg_str]):
                return self.photo_cache[reg_str]
        
        reg_clean = reg_str.lstrip('0')
        if reg_clean in self.photo_cache:
            if os.path.exists(self.photo_cache[reg_clean]):
                return self.photo_cache[reg_clean]
        
        if self.photo_folder:
            for root, dirs, files in os.walk(self.photo_folder):
                for file in files:
                    file_lower = file.lower()
                    if reg_str in file and ('_p.' in file_lower or '_p_' in file_lower):
                        full_path = os.path.join(root, file)
                        self.photo_cache[reg_str] = full_path
                        return full_path
                    
                    if reg_clean in file and ('_p.' in file_lower or '_p_' in file_lower):
                        full_path = os.path.join(root, file)
                        self.photo_cache[reg_str] = full_path
                        return full_path
        
        return None
    
    def get_signature_path(self, reg_number):
        if reg_number is None or pd.isna(reg_number):
            return None
        
        reg_str = str(reg_number).strip()
        
        if reg_str in self.signature_cache:
            if os.path.exists(self.signature_cache[reg_str]):
                return self.signature_cache[reg_str]
        
        reg_clean = reg_str.lstrip('0')
        if reg_clean in self.signature_cache:
            if os.path.exists(self.signature_cache[reg_clean]):
                return self.signature_cache[reg_clean]
        
        if self.photo_folder:
            for root, dirs, files in os.walk(self.photo_folder):
                for file in files:
                    file_lower = file.lower()
                    if reg_str in file and ('_s.' in file_lower or '_s_' in file_lower):
                        full_path = os.path.join(root, file)
                        self.signature_cache[reg_str] = full_path
                        return full_path
                    
                    if reg_clean in file and ('_s.' in file_lower or '_s_' in file_lower):
                        full_path = os.path.join(root, file)
                        self.signature_cache[reg_str] = full_path
                        return full_path
        
        return None
    
    def get_photo(self, reg_number):
        return self.get_photo_path(reg_number)
    
    def get_signature(self, reg_number):
        return self.get_signature_path(reg_number)
    
    def get_photo_count(self):
        return len(self.photo_cache)
    
    def get_signature_count(self):
        return len(self.signature_cache)
    
    def get_total_count(self):
        return len(self.reg_numbers)

# ============================================
# PATH NORMALIZATION
# ============================================

def normalize_path(file_path):
    if not file_path:
        return None
    file_path = file_path.strip().strip('"').strip("'")
    if file_path.startswith('\\\\'):
        return file_path
    if '/' in file_path:
        file_path = file_path.replace('/', '\\')
    if '\\\\' in file_path and not file_path.startswith('\\\\'):
        file_path = file_path.replace('\\\\', '\\')
    return file_path

# ============================================
# DATA LOADER
# ============================================

def get_sqlite_tables(db_path):
    try:
        conn = sqlite3.connect(db_path)
        query = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        tables = pd.read_sql(query, conn)
        conn.close()
        return tables['name'].tolist()
    except Exception as e:
        st.error(f"Error reading SQLite database: {str(e)}")
        return []

@st.cache_data
def load_data_from_path(file_path):
    try:
        file_path = normalize_path(file_path)
        if not file_path:
            return None, "No file path provided"
        
        if not os.path.exists(file_path):
            return None, f"File not found: {file_path}"
        
        file_ext = os.path.splitext(file_path)[1].lower()
        st.info(f"📂 Loading: {os.path.basename(file_path)}")
        
        if file_ext == '.csv':
            file_size = os.path.getsize(file_path) / (1024 * 1024)
            st.info(f"📊 Size: {file_size:.1f} MB")
            
            if file_size > 200:
                st.warning(f"Large file ({file_size:.1f} MB). Loading in chunks...")
                chunk_iter = pd.read_csv(file_path, chunksize=50000, low_memory=False, encoding='utf-8-sig')
                chunks = []
                progress_bar = st.progress(0)
                total = int(file_size / 50) + 1
                for i, chunk in enumerate(chunk_iter):
                    chunks.append(chunk)
                    progress_bar.progress(min((i + 1) / total, 1.0))
                df = pd.concat(chunks, ignore_index=True)
                progress_bar.progress(1.0)
            else:
                df = pd.read_csv(file_path, low_memory=False, encoding='utf-8-sig')
            st.success(f"✅ Loaded {len(df):,} rows")
            
        elif file_ext in ['.xlsx', '.xls']:
            df = pd.read_excel(file_path, engine='openpyxl')
            st.success(f"✅ Loaded {len(df):,} rows")
            
        elif file_ext in ['.db', '.sqlite', '.sqlite3']:
            tables = get_sqlite_tables(file_path)
            if tables:
                return tables, "table_selection_needed"
            else:
                return None, "No tables found"
        else:
            return None, f"Unsupported format: {file_ext}"
        
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        df.columns = df.columns.str.replace(r'[^a-zA-Z0-9_]', '', regex=True)
        return df, None
        
    except Exception as e:
        return None, f"Error: {str(e)}"

@st.cache_data
def load_sqlite_table(db_path, table_name):
    try:
        conn = sqlite3.connect(db_path)
        df = pd.read_sql(f"SELECT * FROM {table_name}", conn)
        conn.close()
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        df.columns = df.columns.str.replace(r'[^a-zA-Z0-9_]', '', regex=True)
        return df, None
    except Exception as e:
        return None, f"Error loading table: {str(e)}"

def load_data_upload(uploaded_file):
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, low_memory=False, encoding='utf-8-sig')
        elif uploaded_file.name.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(uploaded_file)
        else:
            return None
        df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')
        df.columns = df.columns.str.replace(r'[^a-zA-Z0-9_]', '', regex=True)
        return df
    except Exception as e:
        st.error(f"Error: {str(e)}")
        return None

# ============================================
# DATA CLEANER
# ============================================

def clean_data(df):
    df_clean = df.copy()
    df_clean = df_clean.drop_duplicates()
    
    date_columns = ['dob', 'dob2', 'examdate', 'examdate1', 'exam_date', 'date']
    for col in date_columns:
        if col in df_clean.columns:
            try:
                df_clean[col] = pd.to_datetime(df_clean[col], errors='coerce')
            except:
                pass
    
    if 'gender' in df_clean.columns:
        df_clean['gender'] = df_clean['gender'].astype(str).str.strip().str.title()
        df_clean['gender'] = df_clean['gender'].replace({'M': 'Male', 'F': 'Female', 'O': 'Other'})
    
    if 'category' in df_clean.columns:
        df_clean['category'] = df_clean['category'].astype(str).str.strip().str.upper()
        df_clean['category'] = df_clean['category'].replace({
            'GEN': 'UR', 'GENERAL': 'UR', 'UR': 'UR',
            'OBC': 'OBC', 'SC': 'SC', 'ST': 'ST', 'EWS': 'EWS'
        })
    
    if 'dob' in df_clean.columns:
        df_clean['age'] = df_clean['dob'].apply(
            lambda x: (datetime.now() - x).days // 365 if pd.notnull(x) else np.nan
        )
        df_clean['age_group'] = pd.cut(
            df_clean['age'], 
            bins=[0, 20, 25, 30, 35, 100],
            labels=['<20', '20-25', '26-30', '31-35', '35+']
        )
    
    if 'downloaded' in df_clean.columns:
        df_clean['download_status'] = df_clean['downloaded'].apply(
            lambda x: 'Downloaded' if str(x).lower() in ['t', 'true', 'yes', '1', 'y'] else 'Not Downloaded'
        )
    
    if 'ph' in df_clean.columns:
        df_clean['is_pwbd'] = df_clean['ph'].apply(
            lambda x: 'Yes' if pd.notnull(x) and str(x) != '2' and str(x) != '' else 'No'
        )
    
    if 'shift' in df_clean.columns:
        df_clean['shift_label'] = df_clean['shift'].map(SHIFT_LABELS)
    
    return df_clean

# ============================================
# PDF GENERATOR FUNCTIONS
# ============================================

def generate_single_pdf(candidate_data, photo_manager):
    """Generate a single admit card PDF with barcode"""
    buffer = BytesIO()
    
    doc = SimpleDocTemplate(
        buffer, 
        pagesize=A4,
        rightMargin=1.2*cm, 
        leftMargin=1.2*cm,
        topMargin=1.2*cm, 
        bottomMargin=1.2*cm
    )
    
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=18,
        textColor=colors.HexColor('#1a237e'),
        alignment=TA_CENTER,
        spaceAfter=4,
        fontName='Helvetica-Bold'
    )
    
    subtitle_style = ParagraphStyle(
        'Subtitle',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#78909c'),
        alignment=TA_CENTER,
        spaceAfter=10,
        fontName='Helvetica'
    )
    
    name_style = ParagraphStyle(
        'NameStyle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.HexColor('#1a237e'),
        alignment=TA_LEFT,
        spaceAfter=4,
        fontName='Helvetica-Bold'
    )
    
    detail_style = ParagraphStyle(
        'DetailStyle',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#78909c'),
        alignment=TA_LEFT,
        spaceAfter=2,
        fontName='Helvetica'
    )
    
    section_style = ParagraphStyle(
        'SectionStyle',
        parent=styles['Heading2'],
        fontSize=12,
        textColor=colors.HexColor('#1a237e'),
        alignment=TA_LEFT,
        spaceAfter=6,
        spaceBefore=8,
        fontName='Helvetica-Bold'
    )
    
    label_style = ParagraphStyle(
        'LabelStyle',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#78909c'),
        fontName='Helvetica-Bold'
    )
    
    value_style = ParagraphStyle(
        'ValueStyle',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#000000'),
        fontName='Helvetica'
    )
    
    story = []
    
    reg_no = safe_get_value(candidate_data, 'reg_number', '')
    if reg_no == 'N/A' or reg_no == '':
        reg_no = ''
    reg_no = str(reg_no).strip()
    
    roll_no = safe_get_value(candidate_data, 'roll_number', '')
    if roll_no == 'N/A' or roll_no == '':
        roll_no = ''
    roll_no = str(roll_no).strip()
    
    photo_path = photo_manager.get_photo(reg_no) if photo_manager else None
    signature_path = photo_manager.get_signature(reg_no) if photo_manager else None
    
    story.append(Paragraph("ADMIT CARD", title_style))
    story.append(Paragraph("Staff Selection Commission • Examination", subtitle_style))
    
    line_table = Table([['']], colWidths=[16*cm])
    line_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#1a237e')),
        ('HEIGHT', (0, 0), (-1, -1), 0.08*cm),
    ]))
    story.append(line_table)
    story.append(Spacer(1, 0.15*inch))
    
    name_val = safe_get_value(candidate_data, 'name', 'N/A')
    
    left_content = []
    left_content.append(Paragraph(f"{name_val}", name_style))
    
    detail_lines = []
    if reg_no:
        detail_lines.append(f"Registration No: {reg_no}")
    if roll_no:
        detail_lines.append(f"Roll No: {roll_no}")
    
    detail_lines.append("─" * 30)
    
    dob_val = candidate_data.get('dob')
    if not pd.isna(dob_val):
        dob_str = format_date_safe(dob_val)
        age_val = safe_get_int(candidate_data, 'age', 0)
        if age_val > 0:
            detail_lines.append(f"DOB: {dob_str} | Age: {age_val} years")
        else:
            detail_lines.append(f"DOB: {dob_str}")
    
    exam_date_val = candidate_data.get('exam_date')
    if not pd.isna(exam_date_val):
        exam_date_str = format_date_safe(exam_date_val)
        detail_lines.append(f"Exam Date: {exam_date_str}")
    
    shift_val = safe_get_value(candidate_data, 'shift_label')
    if shift_val == 'N/A':
        shift_val = safe_get_value(candidate_data, 'shift')
    if shift_val != 'N/A':
        detail_lines.append(f"Shift: {shift_val}")
    
    for line in detail_lines:
        left_content.append(Paragraph(line, detail_style))
    
    right_content = []
    
    if photo_path and os.path.exists(photo_path):
        try:
            img = Image.open(photo_path)
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            img.thumbnail((150, 150), Image.Resampling.LANCZOS)
            img_bytes = BytesIO()
            img.save(img_bytes, format='JPEG', quality=85)
            img_bytes.seek(0)
            photo_img = RLImage(img_bytes, width=2.5*cm, height=2.5*cm)
            right_content.append(photo_img)
        except:
            right_content.append(Paragraph("No Photo", styles['Normal']))
    else:
        right_content.append(Paragraph("No Photo", styles['Normal']))
    
    right_content.append(Spacer(1, 0.08*inch))
    
    if signature_path and os.path.exists(signature_path):
        try:
            img = Image.open(signature_path)
            if img.mode in ('RGBA', 'LA', 'P'):
                img = img.convert('RGB')
            img.thumbnail((120, 60), Image.Resampling.LANCZOS)
            img_bytes = BytesIO()
            img.save(img_bytes, format='JPEG', quality=85)
            img_bytes.seek(0)
            sig_img = RLImage(img_bytes, width=2.0*cm, height=0.8*cm)
            right_content.append(sig_img)
        except:
            right_content.append(Paragraph("No Signature", styles['Normal']))
    else:
        right_content.append(Paragraph("No Signature", styles['Normal']))
    
    header_data = [
        [left_content, right_content]
    ]
    
    header_table = Table(header_data, colWidths=[10*cm, 6*cm])
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'LEFT'),
        ('ALIGN', (1, 0), (1, 0), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f5f5f5')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#bdbdbd')),
    ]))
    
    story.append(header_table)
    story.append(Spacer(1, 0.15*inch))
    
    if roll_no and BARCODE_AVAILABLE:
        try:
            barcode_buffer = generate_barcode(roll_no)
            if barcode_buffer:
                barcode_img = RLImage(barcode_buffer, width=5*cm, height=1.2*cm)
                barcode_center = Table([[barcode_img]], colWidths=[16*cm])
                barcode_center.setStyle(TableStyle([
                    ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                    ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ('TOPPADDING', (0, 0), (-1, -1), 4),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                ]))
                story.append(barcode_center)
                story.append(Spacer(1, 0.1*inch))
        except:
            pass
    
    story.append(Paragraph("PERSONAL DETAILS", section_style))
    
    personal_data = []
    
    dob_value = candidate_data.get('dob')
    if not pd.isna(dob_value):
        dob_value = format_date_safe(dob_value)
    else:
        dob_value = 'N/A'
    
    age_val = safe_get_int(candidate_data, 'age', 0)
    age_str = f"{age_val} years" if age_val > 0 else 'N/A'
    
    personal_fields = [
        ("Father's Name", safe_get_value(candidate_data, 'father_name')),
        ("Mother's Name", safe_get_value(candidate_data, 'mother_name')),
        ("Gender", safe_get_value(candidate_data, 'gender')),
        ("Category", safe_get_value(candidate_data, 'category')),
        ("Date of Birth", dob_value),
        ("Age", age_str),
        ("Mobile", safe_get_value(candidate_data, 'mobile')),
        ("Email", safe_get_value(candidate_data, 'email')),
        ("Identification Mark", safe_get_value(candidate_data, 'identification_mark')),
        ("Present Address", safe_get_value(candidate_data, 'present_address')),
        ("Present District", safe_get_value(candidate_data, 'present_district')),
        ("Present State", safe_get_value(candidate_data, 'present_state')),
        ("Pincode", safe_get_value(candidate_data, 'pincode')),
    ]
    
    for label, value in personal_fields:
        if value != 'N/A' and not pd.isna(value):
            personal_data.append([Paragraph(label + ":", label_style), Paragraph(str(value), value_style)])
    
    is_pwbd = safe_get_value(candidate_data, 'is_pwbd', 'No')
    if is_pwbd == 'Yes':
        personal_data.append([Paragraph("Disability Status:", label_style), Paragraph("Yes", value_style)])
        ph_code = safe_get_value(candidate_data, 'ph_code')
        if ph_code != 'N/A':
            personal_data.append([Paragraph("PH Code:", label_style), Paragraph(str(ph_code), value_style)])
        scribe_req = safe_get_value(candidate_data, 'scribe_required')
        if scribe_req != 'N/A':
            personal_data.append([Paragraph("Scribe Required:", label_style), Paragraph(str(scribe_req), value_style)])
    
    if personal_data:
        mid = (len(personal_data) + 1) // 2
        col1 = personal_data[:mid]
        col2 = personal_data[mid:]
        while len(col2) < len(col1):
            col2.append(['', ''])
        
        table_data = []
        for i in range(len(col1)):
            table_data.append([col1[i][0], col1[i][1], col2[i][0], col2[i][1]])
        
        personal_table = Table(table_data, colWidths=[3.5*cm, 4.5*cm, 3.5*cm, 4.5*cm])
        personal_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ffffff')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f5f5f5')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#f5f5f5')),
        ]))
        story.append(personal_table)
        story.append(Spacer(1, 0.15*inch))
    
    story.append(Paragraph("VENUE DETAILS", section_style))
    
    venue_data = []
    venue_fields = [
        ("Venue Name", safe_get_value(candidate_data, 'venue_name')),
        ("Venue Code", safe_get_value(candidate_data, 'venue_code')),
        ("Address", safe_get_value(candidate_data, 'venue_address')),
        ("City", safe_get_value(candidate_data, 'venue_city')),
        ("District", safe_get_value(candidate_data, 'venue_district')),
        ("State", safe_get_value(candidate_data, 'venue_state')),
    ]
    
    for label, value in venue_fields:
        if value != 'N/A' and not pd.isna(value):
            venue_data.append([Paragraph(label + ":", label_style), Paragraph(str(value), value_style)])
    
    if venue_data:
        venue_table_data = []
        for i in range(0, len(venue_data), 2):
            row = []
            row.extend(venue_data[i])
            if i+1 < len(venue_data):
                row.extend(venue_data[i+1])
            else:
                row.extend(['', ''])
            venue_table_data.append(row)
        
        venue_table = Table(venue_table_data, colWidths=[2.5*cm, 5.5*cm, 2.5*cm, 5.5*cm])
        venue_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#ffffff')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('FONTSIZE', (0, 0), (-1, -1), 9),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e0e0e0')),
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f5f5f5')),
            ('BACKGROUND', (2, 0), (2, -1), colors.HexColor('#f5f5f5')),
        ]))
        story.append(venue_table)
        story.append(Spacer(1, 0.15*inch))
    
    doc.build(story)
    pdf_data = buffer.getvalue()
    buffer.close()
    
    return pdf_data

def generate_bulk_pdf(candidates_list, photo_manager):
    if not candidates_list:
        return None
    
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w') as zip_file:
        for idx, candidate in enumerate(candidates_list):
            try:
                pdf_data = generate_single_pdf(candidate, photo_manager)
                roll_no = safe_get_value(candidate, 'roll_number', f'candidate_{idx+1}')
                filename = f"{roll_no}.pdf"
                zip_file.writestr(filename, pdf_data)
            except Exception as e:
                pass
    
    zip_buffer.seek(0)
    return zip_buffer.getvalue()

# ============================================
# CANDIDATE PROFILE DISPLAY
# ============================================

def display_candidate_profile(candidate_data, photo_manager):
    st.markdown("### 🪪 Candidate Profile")
    st.markdown("---")
    
    reg_no = safe_get_value(candidate_data, 'reg_number', '')
    if reg_no == 'N/A':
        reg_no = ''
    reg_no = str(reg_no).strip()
    
    st.caption(f"🔍 Registration Number: {reg_no}")
    
    photo_path = photo_manager.get_photo(reg_no) if photo_manager else None
    signature_path = photo_manager.get_signature(reg_no) if photo_manager else None
    
    col1, col2, col3 = st.columns([1.2, 2.5, 1.2])
    
    with col1:
        st.markdown("**📷 Photo**")
        if photo_path and os.path.exists(photo_path):
            try:
                img = Image.open(photo_path)
                img.thumbnail((200, 200), Image.Resampling.LANCZOS)
                st.image(img, use_container_width=True)
                st.caption(f"✅ Photo: {os.path.basename(photo_path)}")
            except Exception as e:
                st.info(f"📷 Error loading: {str(e)}")
        else:
            st.info("📷 No Photo Available")
            if photo_manager and photo_manager.photo_folder:
                st.caption(f"📁 Photo folder: {photo_manager.photo_folder}")
    
    with col2:
        name = safe_get_value(candidate_data, 'name', 'N/A')
        st.markdown(f"<h2 style='text-align: center; color: #1a237e;'>{name}</h2>", unsafe_allow_html=True)
        
        details_html = "<div style='display: grid; grid-template-columns: 1fr 1fr; gap: 10px;'>"
        detail_items = [
            ("Reg No", reg_no if reg_no else 'N/A'),
            ("Roll No", safe_get_value(candidate_data, 'roll_number')),
            ("Gender", safe_get_value(candidate_data, 'gender')),
            ("Category", safe_get_value(candidate_data, 'category')),
        ]
        for label, value in detail_items:
            if value != 'N/A' and not pd.isna(value):
                details_html += f"<div><strong>{label}:</strong> {value}</div>"
        details_html += "</div>"
        st.markdown(details_html, unsafe_allow_html=True)
        
        if 'dob' in candidate_data and not pd.isna(candidate_data['dob']):
            dob_str = format_date_safe(candidate_data['dob'])
            age_val = safe_get_int(candidate_data, 'age', 0)
            if age_val > 0:
                st.markdown(f"<div style='text-align: center;'><strong>DOB:</strong> {dob_str} | <strong>Age:</strong> {age_val} years</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<div style='text-align: center;'><strong>DOB:</strong> {dob_str}</div>", unsafe_allow_html=True)
    
    with col3:
        st.markdown("**✍️ Signature**")
        if signature_path and os.path.exists(signature_path):
            try:
                img = Image.open(signature_path)
                img.thumbnail((200, 100), Image.Resampling.LANCZOS)
                st.image(img, use_container_width=True)
                st.caption("✅ Signature found")
            except:
                st.info("✍️ Error loading signature")
        else:
            st.info("✍️ No Signature Available")
    
    st.markdown("---")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("""
        <div style='background: #f5f5f5; padding: 15px; border-radius: 10px; border-left: 4px solid #1a237e;'>
        <h4 style='color: #1a237e; margin-top: 0;'>📋 Personal Details</h4>
        </div>
        """, unsafe_allow_html=True)
        
        dob_value = candidate_data.get('dob')
        if not pd.isna(dob_value):
            dob_value = format_date_safe(dob_value)
        else:
            dob_value = 'N/A'
        
        age_val = safe_get_int(candidate_data, 'age', 0)
        age_str = f"{age_val} years" if age_val > 0 else 'N/A'
        
        personal_fields = {
            "Date of Birth": dob_value,
            "Age": age_str,
            "Father's Name": safe_get_value(candidate_data, 'father_name'),
            "Mother's Name": safe_get_value(candidate_data, 'mother_name'),
            "Mobile": safe_get_value(candidate_data, 'mobile'),
            "Email": safe_get_value(candidate_data, 'email'),
            "Identification Mark": safe_get_value(candidate_data, 'identification_mark'),
            "Present Address": safe_get_value(candidate_data, 'present_address'),
            "Present District": safe_get_value(candidate_data, 'present_district'),
            "Present State": safe_get_value(candidate_data, 'present_state'),
            "Pincode": safe_get_value(candidate_data, 'pincode')
        }
        
        for label, value in personal_fields.items():
            if value != 'N/A' and not pd.isna(value):
                st.markdown(f"**{label}:** {value}")
        
        if safe_get_value(candidate_data, 'is_pwbd') == 'Yes':
            st.markdown("""
            <div style='background: #f5f5f5; padding: 15px; border-radius: 10px; border-left: 4px solid #b71c1c; margin-top: 15px;'>
            <h4 style='color: #b71c1c; margin-top: 0;'>♿ PwBD Details</h4>
            </div>
            """, unsafe_allow_html=True)
            
            pwbd_fields = {
                "PH Code": safe_get_value(candidate_data, 'ph_code'),
                "Scribe Required": safe_get_value(candidate_data, 'scribe_required'),
                "Own Scribe": safe_get_value(candidate_data, 'own_scribe'),
                "Scribe Medium": safe_get_value(candidate_data, 'scribe_medium')
            }
            
            for label, value in pwbd_fields.items():
                if value != 'N/A' and not pd.isna(value):
                    st.markdown(f"**{label}:** {value}")
    
    with col2:
        st.markdown("""
        <div style='background: #f5f5f5; padding: 15px; border-radius: 10px; border-left: 4px solid #0d47a1;'>
        <h4 style='color: #0d47a1; margin-top: 0;'>🏢 Exam Details</h4>
        </div>
        """, unsafe_allow_html=True)
        
        exam_date_value = candidate_data.get('exam_date')
        if not pd.isna(exam_date_value):
            exam_date_value = format_date_safe(exam_date_value)
        else:
            exam_date_value = 'N/A'
        
        shift_val = safe_get_value(candidate_data, 'shift_label')
        if shift_val == 'N/A':
            shift_val = safe_get_value(candidate_data, 'shift')
        
        exam_fields = {
            "Exam Date": exam_date_value,
            "Shift": shift_val,
            "Batch": safe_get_value(candidate_data, 'batch'),
            "Shifted": 'Yes' if safe_get_value(candidate_data, 'is_shifted') == 'Yes' else 'No'
        }
        
        for label, value in exam_fields.items():
            if value != 'N/A' and not pd.isna(value):
                st.markdown(f"**{label}:** {value}")
        
        st.markdown("""
        <div style='background: #f5f5f5; padding: 15px; border-radius: 10px; border-left: 4px solid #4a148c; margin-top: 15px;'>
        <h4 style='color: #4a148c; margin-top: 0;'>📍 Venue Details</h4>
        </div>
        """, unsafe_allow_html=True)
        
        venue_fields = {
            "Venue Name": safe_get_value(candidate_data, 'venue_name'),
            "Venue Code": safe_get_value(candidate_data, 'venue_code'),
            "Address": safe_get_value(candidate_data, 'venue_address'),
            "City": safe_get_value(candidate_data, 'venue_city'),
            "District": safe_get_value(candidate_data, 'venue_district'),
            "State": safe_get_value(candidate_data, 'venue_state')
        }
        
        for label, value in venue_fields.items():
            if value != 'N/A' and not pd.isna(value):
                st.markdown(f"**{label}:** {value}")

# ============================================
# FILTER ENGINE
# ============================================

def apply_filters(df, filters):
    filtered_df = df.copy()
    if filters.get('exam_date'):
        date_col = None
        for col in ['exam_date', 'examdate', 'date']:
            if col in filtered_df.columns:
                date_col = col
                break
        if date_col:
            filtered_df = filtered_df[filtered_df[date_col] == filters['exam_date']]
    if filters.get('shift') and 'shift' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['shift'] == filters['shift']]
    if filters.get('venue') and 'venue_name' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['venue_name'] == filters['venue']]
    if filters.get('category') and 'category' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['category'] == filters['category']]
    if filters.get('gender') and 'gender' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['gender'] == filters['gender']]
    if filters.get('state'):
        state_col = None
        for col in ['state', 'venue_state', 'present_state']:
            if col in filtered_df.columns:
                state_col = col
                break
        if state_col:
            filtered_df = filtered_df[filtered_df[state_col] == filters['state']]
    if filters.get('district'):
        district_col = None
        for col in ['district', 'venue_district', 'present_district']:
            if col in filtered_df.columns:
                district_col = col
                break
        if district_col:
            filtered_df = filtered_df[filtered_df[district_col] == filters['district']]
    if filters.get('search'):
        search_term = filters['search'].lower()
        search_cols = []
        for col in ['name', 'reg_number', 'roll_number', 'mobile', 'email']:
            if col in filtered_df.columns:
                search_cols.append(col)
        if search_cols:
            mask = False
            for col in search_cols:
                mask = mask | filtered_df[col].astype(str).str.lower().str.contains(search_term, na=False)
            filtered_df = filtered_df[mask]
    return filtered_df

def get_filter_options(df):
    options = {}
    date_col = None
    for col in ['exam_date', 'examdate', 'date']:
        if col in df.columns:
            date_col = col
            break
    if date_col:
        options['exam_dates'] = sorted(df[date_col].dropna().unique())
    if 'shift' in df.columns:
        options['shifts'] = sorted(df['shift'].dropna().unique())
    if 'venue_name' in df.columns:
        options['venues'] = sorted(df['venue_name'].dropna().unique())
    if 'category' in df.columns:
        options['categories'] = sorted(df['category'].dropna().unique())
    if 'gender' in df.columns:
        options['genders'] = sorted(df['gender'].dropna().unique())
    state_col = None
    for col in ['state', 'venue_state', 'present_state']:
        if col in df.columns:
            state_col = col
            break
    if state_col:
        options['states'] = sorted(df[state_col].dropna().unique())
    district_col = None
    for col in ['district', 'venue_district', 'present_district']:
        if col in df.columns:
            district_col = col
            break
    if district_col:
        options['districts'] = sorted(df[district_col].dropna().unique())
    return options

# ============================================
# CHART GENERATOR FUNCTIONS
# ============================================

def create_kpi_metrics(df):
    metrics = {'total': len(df)}
    if 'gender' in df.columns:
        metrics['female'] = len(df[df['gender'] == 'Female'])
    if 'is_pwbd' in df.columns:
        metrics['pwbd'] = len(df[df['is_pwbd'] == 'Yes'])
    if 'download_status' in df.columns:
        metrics['downloaded'] = len(df[df['download_status'] == 'Downloaded'])
    if 'shift' in df.columns:
        for i in [1, 2, 3]:
            metrics[f'shift_{i}'] = len(df[df['shift'] == i])
    if 'category' in df.columns:
        for cat in ['UR', 'OBC', 'SC', 'ST', 'EWS']:
            metrics[f'category_{cat.lower()}'] = len(df[df['category'] == cat])
    if 'venue_name' in df.columns:
        metrics['venues'] = df['venue_name'].nunique()
    date_col = None
    for col in ['exam_date', 'examdate', 'date']:
        if col in df.columns:
            date_col = col
            break
    if date_col:
        metrics['exam_dates'] = df[date_col].nunique()
    return metrics

def create_gender_chart(df):
    if 'gender' not in df.columns:
        return None
    gender_counts = df['gender'].value_counts().reset_index()
    gender_counts.columns = ['Gender', 'Count']
    fig = px.pie(gender_counts, values='Count', names='Gender', title='Gender Distribution',
                 color='Gender', color_discrete_map={'Male': '#1f77b4', 'Female': '#ff7f0e', 'Other': '#9467bd'},
                 hole=0.4)
    fig.update_traces(textposition='inside', textinfo='percent+label')
    return fig

def create_category_chart(df):
    if 'category' not in df.columns:
        return None
    cat_counts = df['category'].value_counts().reset_index()
    cat_counts.columns = ['Category', 'Count']
    fig = px.bar(cat_counts, x='Category', y='Count', title='Category Distribution',
                 color='Category', color_discrete_map=CATEGORY_COLORS, text='Count')
    fig.update_traces(textposition='outside')
    return fig

def create_venue_chart(df, top_n=20):
    if 'venue_name' not in df.columns:
        return None
    venue_counts = df['venue_name'].value_counts().head(top_n).reset_index()
    venue_counts.columns = ['Venue', 'Candidates']
    fig = px.bar(venue_counts, x='Candidates', y='Venue', title=f'Top {top_n} Venues',
                 orientation='h', color='Candidates', color_continuous_scale='Viridis')
    fig.update_layout(height=600)
    return fig

def create_shift_chart(df):
    if 'shift' not in df.columns:
        return None
    shift_counts = df['shift'].value_counts().sort_index().reset_index()
    shift_counts.columns = ['Shift', 'Count']
    shift_counts['Shift'] = shift_counts['Shift'].map(SHIFT_LABELS)
    fig = px.bar(shift_counts, x='Shift', y='Count', title='Shift Distribution',
                 color='Shift', text='Count')
    fig.update_traces(textposition='outside')
    return fig

def create_state_chart(df, top_n=15):
    state_col = None
    for col in ['state', 'venue_state', 'present_state']:
        if col in df.columns:
            state_col = col
            break
    if not state_col:
        return None
    state_counts = df[state_col].value_counts().head(top_n).reset_index()
    state_counts.columns = ['State', 'Count']
    fig = px.bar(state_counts, x='State', y='Count', title=f'Top {top_n} States',
                 color='Count', color_continuous_scale='Plasma')
    fig.update_layout(xaxis_tickangle=-45)
    return fig

def create_download_chart(df):
    if 'download_status' not in df.columns:
        return None
    download_counts = df['download_status'].value_counts().reset_index()
    download_counts.columns = ['Status', 'Count']
    fig = px.pie(download_counts, values='Count', names='Status', title='Download Status',
                 color='Status', color_discrete_map={'Downloaded': '#2ca02c', 'Not Downloaded': '#d62728'},
                 hole=0.4)
    fig.update_traces(textposition='inside', textinfo='percent+label')
    return fig

def create_pwbd_chart(df):
    if 'is_pwbd' not in df.columns:
        return None
    pwbd_counts = df['is_pwbd'].value_counts().reset_index()
    pwbd_counts.columns = ['PwBD', 'Count']
    fig = px.pie(pwbd_counts, values='Count', names='PwBD', title='PwBD Distribution',
                 color='PwBD', color_discrete_map={'Yes': '#9467bd', 'No': '#7f7f7f'},
                 hole=0.4)
    fig.update_traces(textposition='inside', textinfo='percent+label')
    return fig

def create_age_histogram(df):
    if 'age' not in df.columns:
        return None
    fig = px.histogram(df[df['age'].notna()], x='age', nbins=20, title='Age Distribution',
                       color_discrete_sequence=['#1f77b4'], labels={'age': 'Age', 'count': 'Number'})
    if df['age'].notna().any():
        fig.add_vline(x=df['age'].mean(), line_dash="dash", line_color="red", 
                       annotation_text=f"Mean: {df['age'].mean():.1f}")
    return fig

def create_district_chart(df, top_n=15):
    district_col = None
    for col in ['district', 'venue_district', 'present_district']:
        if col in df.columns:
            district_col = col
            break
    if not district_col:
        return None
    district_counts = df[district_col].value_counts().head(top_n).reset_index()
    district_counts.columns = ['District', 'Count']
    fig = px.bar(district_counts, x='District', y='Count', title=f'Top {top_n} Districts',
                 color='Count', color_continuous_scale='Inferno')
    fig.update_layout(xaxis_tickangle=-45)
    return fig

def create_date_timeline(df):
    date_col = None
    for col in ['exam_date', 'examdate', 'date']:
        if col in df.columns:
            date_col = col
            break
    if not date_col:
        return None
    date_counts = df[date_col].value_counts().sort_index().reset_index()
    date_counts.columns = ['Date', 'Count']
    fig = px.line(date_counts, x='Date', y='Count', title='Candidates by Date', markers=True)
    fig.update_layout(xaxis_tickangle=-45)
    return fig

# ============================================
# MAIN DASHBOARD
# ============================================

def show_dashboard(df, photo_manager=None):
    df = clean_data(df)
    metrics = create_kpi_metrics(df)
    
    if photo_manager and photo_manager.get_total_count() > 0:
        st.sidebar.success(f"📸 Photos: {photo_manager.get_photo_count():,}")
        st.sidebar.success(f"✍️ Signatures: {photo_manager.get_signature_count():,}")
        st.sidebar.success(f"👤 Candidates: {photo_manager.get_total_count():,}")
    
    st.sidebar.markdown("---")
    st.sidebar.header("🔍 Filters")
    
    filter_options = get_filter_options(df)
    filters = {}
    
    if filter_options.get('exam_dates'):
        selected_date = st.sidebar.selectbox("Exam Date", ["All"] + list(filter_options['exam_dates']), key="filter_date")
        if selected_date != "All":
            filters['exam_date'] = selected_date
    if filter_options.get('shifts'):
        selected_shift = st.sidebar.selectbox("Shift", ["All"] + list(filter_options['shifts']), key="filter_shift")
        if selected_shift != "All":
            filters['shift'] = selected_shift
    if filter_options.get('venues'):
        selected_venue = st.sidebar.selectbox("Venue", ["All"] + list(filter_options['venues']), key="filter_venue")
        if selected_venue != "All":
            filters['venue'] = selected_venue
    if filter_options.get('categories'):
        selected_category = st.sidebar.selectbox("Category", ["All"] + list(filter_options['categories']), key="filter_category")
        if selected_category != "All":
            filters['category'] = selected_category
    if filter_options.get('genders'):
        selected_gender = st.sidebar.selectbox("Gender", ["All"] + list(filter_options['genders']), key="filter_gender")
        if selected_gender != "All":
            filters['gender'] = selected_gender
    if filter_options.get('states'):
        selected_state = st.sidebar.selectbox("State", ["All"] + list(filter_options['states']), key="filter_state")
        if selected_state != "All":
            filters['state'] = selected_state
    if filter_options.get('districts'):
        selected_district = st.sidebar.selectbox("District", ["All"] + list(filter_options['districts']), key="filter_district")
        if selected_district != "All":
            filters['district'] = selected_district
    
    if filters:
        filtered_df = apply_filters(df, filters)
    else:
        filtered_df = df
    
    # ============================================
    # MAIN TABS
    # ============================================
    
    main_tabs = st.tabs([
        "📊 Dashboard", 
        "👥 Demographics", 
        "🏢 Venues", 
        "🔎 Search & Profile", 
        "📄 Admit Card",
        "🔎 Data",
        "📈 Analytics"
    ])
    
    # ============================================
    # TAB 1: DASHBOARD
    # ============================================
    with main_tabs[0]:
        st.markdown("### 📊 Executive Dashboard")
        
        cols = st.columns(6)
        with cols[0]:
            st.metric("📊 Total", f"{len(filtered_df):,}")
        if 'female' in metrics:
            with cols[1]:
                female_pct = (metrics.get('female', 0) / len(filtered_df) * 100) if len(filtered_df) > 0 else 0
                st.metric("👩 Female", f"{metrics.get('female', 0):,} ({female_pct:.1f}%)")
        else:
            with cols[1]:
                st.metric("👩 Female", "N/A")
        if 'pwbd' in metrics:
            with cols[2]:
                pwbd_pct = (metrics.get('pwbd', 0) / len(filtered_df) * 100) if len(filtered_df) > 0 else 0
                st.metric("♿ PwBD", f"{metrics.get('pwbd', 0):,} ({pwbd_pct:.1f}%)")
        else:
            with cols[2]:
                st.metric("♿ PwBD", "N/A")
        if 'downloaded' in metrics:
            with cols[3]:
                dl_pct = (metrics.get('downloaded', 0) / len(filtered_df) * 100) if len(filtered_df) > 0 else 0
                st.metric("✅ Downloaded", f"{metrics.get('downloaded', 0):,} ({dl_pct:.1f}%)")
        else:
            with cols[3]:
                st.metric("✅ Downloaded", "N/A")
        if 'venues' in metrics:
            with cols[4]:
                st.metric("🏢 Venues", f"{metrics.get('venues', 0):,}")
        else:
            with cols[4]:
                st.metric("🏢 Venues", "N/A")
        if 'exam_dates' in metrics:
            with cols[5]:
                st.metric("📅 Exam Days", f"{metrics.get('exam_dates', 0):,}")
        else:
            with cols[5]:
                st.metric("📅 Exam Days", "N/A")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            fig = create_gender_chart(filtered_df)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = create_category_chart(filtered_df)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        with col3:
            fig = create_download_chart(filtered_df)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        
        col1, col2 = st.columns(2)
        with col1:
            fig = create_shift_chart(filtered_df)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = create_pwbd_chart(filtered_df)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
    
    # ============================================
    # TAB 2: DEMOGRAPHICS
    # ============================================
    with main_tabs[1]:
        st.markdown("### 👥 Demographics")
        
        col1, col2 = st.columns(2)
        with col1:
            fig = create_age_histogram(filtered_df)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = create_date_timeline(filtered_df)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        
        col1, col2 = st.columns(2)
        with col1:
            fig = create_state_chart(filtered_df)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
        with col2:
            fig = create_district_chart(filtered_df)
            if fig:
                st.plotly_chart(fig, use_container_width=True)
    
    # ============================================
    # TAB 3: VENUES
    # ============================================
    with main_tabs[2]:
        st.markdown("### 🏢 Venues")
        
        fig = create_venue_chart(filtered_df)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        
        if 'venue_name' in filtered_df.columns:
            st.markdown("### 📋 Venue Details")
            if 'reg_number' in filtered_df.columns:
                venue_stats = filtered_df.groupby('venue_name').agg({
                    'reg_number': 'count'
                }).reset_index()
            else:
                venue_stats = filtered_df.groupby('venue_name').size().reset_index(name='Candidates')
            venue_stats.columns = ['Venue', 'Candidates']
            venue_stats = venue_stats.sort_values('Candidates', ascending=False)
            st.dataframe(venue_stats, use_container_width=True, height=400)
    
    # ============================================
    # TAB 4: SEARCH & PROFILE
    # ============================================
    with main_tabs[3]:
        st.markdown("### 🔍 Search Candidate")
        
        search_col1, search_col2, search_col3 = st.columns([2, 1, 1])
        with search_col1:
            search_term = st.text_input("Search by Name, Registration No, or Roll No", placeholder="e.g., 10000817332", key="search_input")
        with search_col2:
            search_by = st.selectbox("Search By", ["All Fields", "Name", "Registration No", "Roll No"], key="search_by")
        with search_col3:
            if st.button("🔍 Search", type="primary", use_container_width=True, key="search_btn"):
                if search_term:
                    search_term_lower = search_term.lower().strip()
                    if search_by == "Name":
                        if 'name' in df.columns:
                            filtered_df = df[df['name'].astype(str).str.lower().str.contains(search_term_lower, na=False)]
                        else:
                            filtered_df = df
                    elif search_by == "Registration No":
                        if 'reg_number' in df.columns:
                            filtered_df = df[df['reg_number'].astype(str).str.contains(search_term, na=False)]
                        else:
                            filtered_df = df
                    elif search_by == "Roll No":
                        if 'roll_number' in df.columns:
                            filtered_df = df[df['roll_number'].astype(str).str.contains(search_term, na=False)]
                        else:
                            filtered_df = df
                    else:
                        search_cols = []
                        for col in ['name', 'reg_number', 'roll_number']:
                            if col in df.columns:
                                search_cols.append(col)
                        if search_cols:
                            mask = False
                            for col in search_cols:
                                mask = mask | df[col].astype(str).str.lower().str.contains(search_term_lower, na=False)
                            filtered_df = df[mask]
                        else:
                            filtered_df = df
                    st.session_state.search_results = filtered_df
                    st.session_state.search_performed = True
                    st.rerun()
        
        if st.session_state.get('search_performed', False) and st.session_state.get('search_results') is not None:
            results = st.session_state.search_results
            if len(results) == 0:
                st.info("🔍 No candidates found")
                st.session_state.search_performed = False
            elif len(results) == 1:
                candidate = results.iloc[0].to_dict()
                st.success(f"✅ Found 1 candidate")
                display_candidate_profile(candidate, photo_manager)
                st.markdown("---")
                st.markdown("### 📄 Download Admit Card")
                try:
                    with st.spinner("Generating Admit Card PDF..."):
                        pdf_data = generate_single_pdf(candidate, photo_manager)
                        roll_no_val = safe_get_value(candidate, 'roll_number', 'unknown')
                        if roll_no_val == 'N/A' or roll_no_val == '':
                            roll_no_val = 'unknown'
                        st.download_button(
                            label="📥 Download Admit Card",
                            data=pdf_data,
                            file_name=f"{roll_no_val}.pdf",
                            mime="application/pdf",
                            key="pdf_download_search",
                            use_container_width=True
                        )
                        st.success("✅ Admit Card ready for download!")
                except Exception as e:
                    st.error(f"Error generating PDF: {str(e)}")
                col1, col2 = st.columns([1, 1])
                with col2:
                    if st.button("✖️ Close", use_container_width=True):
                        st.session_state.search_performed = False
                        st.session_state.search_results = None
                        st.rerun()
                st.session_state.search_performed = False
            else:
                st.success(f"✅ Found {len(results)} candidates")
                cols_per_row = 4
                for row in range((len(results) + cols_per_row - 1) // cols_per_row):
                    cols = st.columns(cols_per_row)
                    for col_idx in range(cols_per_row):
                        idx = row * cols_per_row + col_idx
                        if idx < len(results):
                            with cols[col_idx]:
                                candidate = results.iloc[idx]
                                reg_no = str(safe_get_value(candidate, 'reg_number', '')).strip()
                                name = safe_get_value(candidate, 'name', 'N/A')
                                photo_path = photo_manager.get_photo(reg_no) if photo_manager else None
                                with st.container(border=True):
                                    if photo_path and os.path.exists(photo_path):
                                        try:
                                            img = Image.open(photo_path)
                                            img.thumbnail((150, 150), Image.Resampling.LANCZOS)
                                            st.image(img, use_container_width=False)
                                        except:
                                            st.info("📷 No Photo")
                                    else:
                                        st.info("📷 No Photo")
                                    st.markdown(f"**{name}**")
                                    st.caption(f"Reg: {reg_no}")
                                    if st.button(f"View Profile", key=f"view_{reg_no}_{idx}"):
                                        st.session_state.selected_candidate = candidate.to_dict()
                                        st.session_state.show_profile = True
                                        st.rerun()
                with st.expander("📋 Show All Results"):
                    display_cols = []
                    for col in ['name', 'reg_number', 'roll_number', 'gender', 'category', 'venue_name']:
                        if col in results.columns:
                            display_cols.append(col)
                    st.dataframe(results[display_cols], use_container_width=True)
        
        if st.session_state.get('show_profile', False) and st.session_state.get('selected_candidate'):
            st.markdown("---")
            st.markdown("### 📄 Candidate Details")
            display_candidate_profile(st.session_state.selected_candidate, photo_manager)
            st.markdown("---")
            st.markdown("### 📄 Download Admit Card")
            candidate = st.session_state.selected_candidate
            try:
                with st.spinner("Generating Admit Card PDF..."):
                    pdf_data = generate_single_pdf(candidate, photo_manager)
                    roll_no_val = safe_get_value(candidate, 'roll_number', 'unknown')
                    if roll_no_val == 'N/A' or roll_no_val == '':
                        roll_no_val = 'unknown'
                    st.download_button(
                        label="📥 Download Admit Card",
                        data=pdf_data,
                        file_name=f"{roll_no_val}.pdf",
                        mime="application/pdf",
                        key="pdf_download_profile",
                        use_container_width=True
                    )
                    st.success("✅ Admit Card ready for download!")
            except Exception as e:
                st.error(f"Error generating PDF: {str(e)}")
            col1, col2 = st.columns([1, 1])
            with col2:
                if st.button("✖️ Close Profile", use_container_width=True):
                    st.session_state.show_profile = False
                    st.session_state.selected_candidate = None
                    st.rerun()
            st.markdown("---")
    
    # ============================================
    # TAB 5: ADMIT CARD GENERATOR
    # ============================================
    with main_tabs[4]:
        st.markdown("### 📄 Admit Card Generator")
        
        col1, col2, col3 = st.columns([1, 1, 1])
        with col1:
            output_format = st.radio(
                "Output Format",
                ["📄 PDF"],
                key="admit_output_format",
                horizontal=True
            )
        
        with col2:
            gen_mode = st.radio(
                "Select Candidates",
                ["🔍 Single", "📋 Paste List", "📚 ALL"],
                key="admit_gen_mode",
                horizontal=True
            )
        
        with col3:
            st.info("📄 PDF format only")
        
        st.markdown("---")
        
        if gen_mode == "🔍 Single":
            col1, col2 = st.columns([2, 1])
            with col1:
                reg_input = st.text_input("Enter Registration Number", key="admit_reg_input", placeholder="e.g., 10000817332")
            with col2:
                if st.button("🚀 Generate", type="primary", use_container_width=True, key="admit_gen_single"):
                    if reg_input:
                        result = df[df['reg_number'].astype(str).str.contains(reg_input, na=False)]
                        if len(result) > 0:
                            candidate = result.iloc[0].to_dict()
                            with st.spinner("Generating Admit Card PDF..."):
                                pdf_data = generate_single_pdf(candidate, photo_manager)
                                roll_no = safe_get_value(candidate, 'roll_number', 'unknown')
                                st.download_button(
                                    label="📥 Download PDF",
                                    data=pdf_data,
                                    file_name=f"{roll_no}.pdf",
                                    mime="application/pdf",
                                    key="admit_download_pdf",
                                    use_container_width=True
                                )
                                st.success("✅ Generated successfully!")
                        else:
                            st.warning("Candidate not found")
                    else:
                        st.warning("Please enter a Registration Number")
        
        elif gen_mode == "📋 Paste List":
            st.markdown("**Enter Registration Numbers (one per line):**")
            bulk_reg_input = st.text_area(
                "Registration Numbers",
                placeholder="10000817332\n10001259955\n10002129510",
                height=150,
                key="bulk_reg_input"
            )
            
            if st.button("🚀 Generate from List", type="primary", use_container_width=True, key="admit_gen_list"):
                if bulk_reg_input:
                    reg_numbers = [x.strip() for x in bulk_reg_input.split('\n') if x.strip()]
                    candidates_found = []
                    candidates_not_found = []
                    
                    for reg_no in reg_numbers:
                        result = df[df['reg_number'].astype(str).str.contains(reg_no, na=False)]
                        if len(result) > 0:
                            candidates_found.append(result.iloc[0].to_dict())
                        else:
                            candidates_not_found.append(reg_no)
                    
                    if candidates_found:
                        if candidates_not_found:
                            st.warning(f"⚠️ Not found: {', '.join(candidates_not_found)}")
                        
                        with st.spinner(f"Generating {len(candidates_found)} admit cards..."):
                            zip_data = generate_bulk_pdf(candidates_found, photo_manager)
                            if zip_data:
                                st.download_button(
                                    label=f"📥 Download {len(candidates_found)} PDFs",
                                    data=zip_data,
                                    file_name=f"Admit_Cards_{len(candidates_found)}.zip",
                                    mime="application/zip",
                                    key="admit_download_list_pdf",
                                    use_container_width=True
                                )
                                st.success(f"✅ {len(candidates_found)} generated successfully!")
                    else:
                        st.warning("No candidates found")
                else:
                    st.warning("Please enter Registration Numbers")
        
        else:  # ALL Candidates
            col1, col2 = st.columns([1, 1])
            with col1:
                if st.button("🚀 Generate ALL", type="primary", use_container_width=True, key="admit_gen_all"):
                    candidates = filtered_df.to_dict('records')
                    if candidates:
                        with st.spinner(f"Generating {len(candidates)} admit cards..."):
                            zip_data = generate_bulk_pdf(candidates, photo_manager)
                            if zip_data:
                                st.download_button(
                                    label=f"📥 Download {len(candidates)} PDFs",
                                    data=zip_data,
                                    file_name=f"Admit_Cards_{len(candidates)}.zip",
                                    mime="application/zip",
                                    key="admit_download_all_pdf",
                                    use_container_width=True
                                )
                                st.success(f"✅ {len(candidates)} generated successfully!")
                    else:
                        st.warning("No candidates found")
            
            with col2:
                st.info(f"📊 {len(filtered_df)} candidates will be generated")
    
    # ============================================
    # TAB 6: DATA
    # ============================================
    with main_tabs[5]:
        st.markdown("### 🔎 Data Viewer")
        st.dataframe(filtered_df, use_container_width=True, height=500)
        
        col1, col2 = st.columns(2)
        with col1:
            csv = filtered_df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download CSV", csv, "data.csv", "text/csv")
        with col2:
            output = BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                filtered_df.to_excel(writer, sheet_name='Data', index=False)
            st.download_button("📥 Download Excel", output.getvalue(), "data.xlsx", 
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    
    # ============================================
    # TAB 7: ANALYTICS
    # ============================================
    with main_tabs[6]:
        st.markdown("### 📈 Analytics")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Rows", f"{len(filtered_df):,}")
            st.metric("Total Columns", len(filtered_df.columns))
        with col2:
            st.metric("Duplicate Rows", filtered_df.duplicated().sum())
            st.metric("Memory Usage", f"{filtered_df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
        with col3:
            missing = filtered_df.isnull().sum().sum()
            st.metric("Missing Values", missing)
            st.metric("Unique Values", filtered_df.nunique().sum())
        
        st.markdown("### 📋 Column Info")
        col_info = pd.DataFrame({
            'Column': filtered_df.columns,
            'Type': filtered_df.dtypes.astype(str),
            'Nulls': filtered_df.isnull().sum(),
            'Unique': filtered_df.nunique(),
            'Sample': [str(filtered_df[col].iloc[0])[:50] if len(filtered_df) > 0 else '' for col in filtered_df.columns]
        })
        st.dataframe(col_info, use_container_width=True)

# ============================================
# MAIN
# ============================================

def main():
    st.title("🎯 Exam Analytics Studio Pro")
    st.markdown("*Complete Exam Intelligence Platform with Admit Card Generator*")
    
    # Initialize session state
    if 'df' not in st.session_state:
        st.session_state.df = None
    if 'data_loaded' not in st.session_state:
        st.session_state.data_loaded = False
    if 'sqlite_tables' not in st.session_state:
        st.session_state.sqlite_tables = []
    if 'current_db_path' not in st.session_state:
        st.session_state.current_db_path = None
    if 'photo_manager' not in st.session_state:
        st.session_state.photo_manager = PhotoManager()
    if 'show_profile' not in st.session_state:
        st.session_state.show_profile = False
    if 'selected_candidate' not in st.session_state:
        st.session_state.selected_candidate = None
    if 'search_results' not in st.session_state:
        st.session_state.search_results = None
    if 'search_performed' not in st.session_state:
        st.session_state.search_performed = False
    if 'photo_folder_path' not in st.session_state:
        st.session_state.photo_folder_path = ""
    if 'data_file_path' not in st.session_state:
        st.session_state.data_file_path = ""
    
    with st.sidebar:
        st.header("📁 Data Upload")
        upload_method = st.radio("Upload Method", ["📤 Upload File", "📂 File Path"])
        if upload_method == "📤 Upload File":
            uploaded_file = st.file_uploader("Upload Data File", type=['xlsx', 'xls', 'csv'], key="file_upload")
            if st.button("🚀 Process File", type="primary"):
                if uploaded_file is not None:
                    with st.spinner("Loading..."):
                        df = load_data_upload(uploaded_file)
                        if df is not None:
                            st.session_state.df = df
                            st.session_state.data_loaded = True
                            st.success(f"✅ Loaded {len(df):,} rows")
                            st.rerun()
        else:
            st.info("💡 Enter the full file path")
            file_path = st.text_input("📄 File Path", key="file_path", 
                                     placeholder="E:\\2025\\Constable (Driver) - Male in Delhi Police Examination 2025\\data.csv",
                                     value=st.session_state.data_file_path if st.session_state.data_file_path else "")
            if file_path and file_path.lower().endswith(('.db', '.sqlite', '.sqlite3')):
                if st.button("🔍 Check Tables"):
                    tables = get_sqlite_tables(file_path)
                    if tables:
                        st.session_state.sqlite_tables = tables
                        st.session_state.current_db_path = file_path
                        st.success(f"✅ Found {len(tables)} tables")
            if st.session_state.sqlite_tables and st.session_state.current_db_path:
                selected_table = st.selectbox("Select Table", st.session_state.sqlite_tables)
                if st.button("📥 Load Table", type="primary"):
                    with st.spinner(f"Loading {selected_table}..."):
                        df, error = load_sqlite_table(st.session_state.current_db_path, selected_table)
                        if df is not None:
                            st.session_state.df = df
                            st.session_state.data_loaded = True
                            st.session_state.data_file_path = file_path
                            st.success(f"✅ Loaded {len(df):,} rows")
                            st.rerun()
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🚀 Load Data", type="primary"):
                    if file_path:
                        with st.spinner("Loading..."):
                            result, error = load_data_from_path(file_path)
                            if isinstance(result, list):
                                st.session_state.sqlite_tables = result
                                st.session_state.current_db_path = file_path
                            elif result is not None and isinstance(result, pd.DataFrame):
                                st.session_state.df = result
                                st.session_state.data_loaded = True
                                st.session_state.data_file_path = file_path
                                detected = ColumnMapper.detect_columns(result)
                                if detected:
                                    mapping = {}
                                    for field, col in detected.items():
                                        mapping[field] = col
                                    st.session_state.df = ColumnMapper.map_columns(result, mapping)
                                    st.success(f"✅ Auto-mapped {len(detected)} columns!")
                                st.rerun()
            with col2:
                if st.button("🗑️ Clear Data"):
                    st.session_state.df = None
                    st.session_state.data_loaded = False
                    st.session_state.data_file_path = ""
                    st.session_state.photo_manager = PhotoManager()
                    st.rerun()
        
        # Photo/Signature
        st.markdown("---")
        st.header("📸 Photos & Signatures")
        st.info("Enter the folder path containing photos (searches recursively)")
        st.caption("✅ Searches all subfolders")
        st.caption("✅ Searches inside all ZIP files")
        st.caption("✅ Searches inside nested ZIP files (ZIP inside ZIP)")
        st.caption("Naming: REGNO_P.jpg and REGNO_S.jpg")
        if st.session_state.photo_folder_path:
            st.caption(f"📁 Current path: {st.session_state.photo_folder_path}")
        photo_folder = st.text_input(
            "📁 Photos Folder Path",
            key="photo_folder_input",
            placeholder="E:\\2025\\Constable (Driver) - Male in Delhi Police Examination 2025\\Photo & Sign",
            value=st.session_state.photo_folder_path if st.session_state.photo_folder_path else ""
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📥 Load Photos (Recursive + Nested ZIP)", type="primary"):
                if photo_folder:
                    st.session_state.photo_folder_path = photo_folder
                    with st.spinner("Loading photos recursively (this may take a while)..."):
                        result = st.session_state.photo_manager.process_folder(photo_folder)
                        if result and 'error' not in result:
                            st.success(f"""
                            ✅ Photos loaded successfully!
                            - Photos found: {result['photos_found']:,}
                            - Signatures found: {result['signatures_found']:,}
                            - Total candidates: {result['total_candidates']:,}
                            - ZIPs found: {result.get('zips_found', 0)}
                            - ZIPs processed: {result.get('zips_processed', 0)}
                            """)
                            st.rerun()
                        elif result and 'error' in result:
                            st.error(result['error'])
                else:
                    st.warning("Please enter a folder path")
        with col2:
            if st.button("🗑️ Clear Photos"):
                st.session_state.photo_manager = PhotoManager()
                st.session_state.photo_folder_path = ""
                st.rerun()
        if st.session_state.photo_manager.get_total_count() > 0:
            st.info(f"📸 {st.session_state.photo_manager.get_photo_count():,} photos loaded")
            st.info(f"✍️ {st.session_state.photo_manager.get_signature_count():,} signatures loaded")
            st.info(f"👤 {st.session_state.photo_manager.get_total_count():,} candidates")
        
        # Column Mapping
        if st.session_state.df is not None:
            st.markdown("---")
            with st.expander("🔧 Column Mapping"):
                df = st.session_state.df
                detected = ColumnMapper.detect_columns(df)
                mapping = {}
                available_cols = [col for col in df.columns]
                for field in ColumnMapper.COLUMN_PATTERNS.keys():
                    options = ["Select..."] + available_cols
                    default_value = "Select..."
                    if field in detected:
                        default_value = detected[field]
                    selected = st.selectbox(
                        f"{field.replace('_', ' ').title()}",
                        options,
                        index=options.index(default_value) if default_value in options else 0,
                        key=f"map_{field}"
                    )
                    if selected != "Select..." and selected not in mapping.values():
                        mapping[field] = selected
                if st.button("✅ Apply Manual Mapping"):
                    if mapping:
                        st.session_state.df = ColumnMapper.map_columns(df, mapping)
                        st.success("✅ Mapping applied!")
                        st.rerun()
    
    # Show dashboard if data loaded
    if st.session_state.data_loaded and st.session_state.df is not None:
        show_dashboard(st.session_state.df, st.session_state.photo_manager)
    else:
        st.markdown("---")
        st.markdown("""
        ### 🚀 Welcome to Exam Analytics Studio Pro!
        
        **Features:**
        - ✅ Handles UNC paths and local paths
        - ✅ Loads files > 200MB with chunking
        - ✅ **7 Tabs**: Dashboard, Demographics, Venues, Search & Profile, Admit Card, Data, Analytics
        - ✅ **Admit Card Generator**: Single, Paste List, or ALL Candidates
        - ✅ **Photo & Signature Support**: Automatically includes photo and signature
        - ✅ **Barcode Generation**: Roll number barcode on admit card
        - ✅ **PDF Output**: Professional admit card PDF
        
        **How to use:**
        1. **Load your data file** (CSV/Excel/SQLite)
        2. **Enter the photos folder path** and load photos
        3. **Search for a candidate** or generate bulk admit cards
        4. **Download Admit Cards** with Photo, Signature & Barcode!
        
        **Photo Naming Convention:**
        - Photo: `REGNO_P.jpg` (e.g., `10000817332_P.jpg`)
        - Signature: `REGNO_S.jpg` (e.g., `10000817332_S.jpg`)
        """)

if __name__ == "__main__":
    main()
