# app.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
import re
from datetime import datetime
import numpy as np
import sys
import math

print("🔄 Application starting...", file=sys.stderr)

# -------------------- Persian styling --------------------
st.set_page_config(
    page_title="پایش هوشمند روغن ترانسفورماتورها",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;600;900&display=swap');
    * {
        font-family: 'Vazirmatn', sans-serif;
    }
    .rtl {
        direction: rtl;
        text-align: right;
    }
    .metric-card {
        background: #fff;
        padding: 15px;
        border-radius: 12px;
        border-right: 5px solid #0d6efd;
        box-shadow: 0 4px 8px rgba(0,0,0,.1);
        margin-bottom: 10px;
    }
    .danger { border-right-color: #dc3545; background: #ffe6e6; }
    .warning { border-right-color: #ffc107; background: #fff3cd; }
    .success { border-right-color: #28a745; background: #e8f5e9; }
    .st-emotion-cache-16txtl3 {
        padding: 1rem 1rem 0rem;
    }
</style>
""", unsafe_allow_html=True)

# -------------------- Helper functions --------------------
@st.cache_data
def load_and_parse(file):
    """Load and parse the CSV file"""
    try:
        # Try different encodings
        try:
            df = pd.read_csv(file, encoding='utf-8')
        except:
            df = pd.read_csv(file, encoding='utf-8-sig')
        
        # Debug: Show columns
        print(f"📋 Columns loaded: {list(df.columns)}", file=sys.stderr)
        
        # Check if SampleName exists
        if 'SampleName' not in df.columns:
            st.error("❌ ستون 'SampleName' در فایل CSV یافت نشد!")
            st.write("ستون‌های موجود:", list(df.columns))
            return None
            
        # Extract components from SampleName
        pattern = r'^(\S+)\s+(\S+)\s+(.+?)\s+(\d{4}-\d{2}-\d{2})$'
        
        # Apply regex extraction
        extracted = df['SampleName'].str.extract(pattern)
        
        if extracted.shape[1] == 4:
            df[['کد_پست', 'نام_تجهیز', 'نام_پست', 'تاریخ_شمسی']] = extracted
            print("✅ Successfully parsed SampleName", file=sys.stderr)
        else:
            # Fallback: split by space
            print("⚠️ Using fallback parsing", file=sys.stderr)
            parts = df['SampleName'].str.split()
            df['کد_پست'] = parts.str[0]
            df['نام_تجهیز'] = parts.str[1] if len(parts.str) > 1 else ''
            df['نام_پست'] = parts.str[2] if len(parts.str) > 2 else ''
            df['تاریخ_شمسی'] = parts.str[-1] if len(parts.str) > 3 else ''
        
        # Try to parse InjDateTime
        if 'InjDateTime' in df.columns:
            try:
                df['تاریخ_میلادی'] = pd.to_datetime(df['InjDateTime'])
            except:
                df['تاریخ_میلادی'] = pd.NaT
        
        # Convert numeric columns - اضافه کردن ستون‌های گازها برای تحلیل DGA
        num_cols = ['TCG', 'TAN', 'BreakdownVoltage', 'WaterContents', 'DDF',
                   'hydrogen', 'Methane', 'Ethane', 'Ethylene', 'Acetylene',
                   'CarbonMonoxide', 'CarbonDioxide', 'propane', 'propylene']
        for col in num_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            else:
                print(f"⚠️ Column {col} not found", file=sys.stderr)
        
        print(f"✅ Loaded {len(df)} records", file=sys.stderr)
        return df
        
    except Exception as e:
        st.error(f"❌ خطا در بارگذاری فایل: {str(e)}")
        print(f"🔴 Error loading file: {e}", file=sys.stderr)
        return None

def calculate_risk_score(row):
    """Calculate risk score 0-100"""
    score = 0
    
    # TCG score
    if pd.notna(row.get('TCG')):
        if row['TCG'] > 3000:
            score += 40
        elif row['TCG'] > 2000:
            score += 25
        elif row['TCG'] > 1000:
            score += 10
    
    # TAN score
    if pd.notna(row.get('TAN')):
        if row['TAN'] > 0.2:
            score += 25
        elif row['TAN'] > 0.1:
            score += 15
    
    # Breakdown Voltage
    if pd.notna(row.get('BreakdownVoltage')):
        if row['BreakdownVoltage'] < 40:
            score += 25
        elif row['BreakdownVoltage'] < 50:
            score += 15
    
    # Water content
    if pd.notna(row.get('WaterContents')):
        if row['WaterContents'] > 40:
            score += 20
        elif row['WaterContents'] > 30:
            score += 10
    
    # ASROG conditions
    if pd.notna(row.get('ASROG')):
        asrog_str = str(row['ASROG'])
        if 'حالت 5' in asrog_str:
            score += 30
        if 'تجزیه حرارتی' in asrog_str:
            score += 20
        if 'تخلیه جزیی' in asrog_str:
            score += 10
    
    return min(100, score)

def get_risk_flag(score):
    """Get risk flag emoji"""
    if score >= 60:
        return '🔴'
    elif score >= 35:
        return '🟡'
    else:
        return '🟢'

def get_risk_level(score):
    """Get risk level text"""
    if score >= 60:
        return 'پرریسک'
    elif score >= 35:
        return 'متوسط'
    else:
        return 'کم‌ریسک'

# -------------------- DGA Analysis Functions --------------------
def calculate_duval_triangle(row):
    """Calculate Duval Triangle percentages"""
    try:
        # گازهای مورد نیاز برای مثلث دووال
        gases_needed = ['Methane', 'Ethane', 'Ethylene', 'Acetylene']
        
        # بررسی وجود ستون‌ها
        missing_gases = [gas for gas in gases_needed if gas not in row.index or pd.isna(row[gas])]
        if missing_gases:
            return None, None, None
        
        CH4 = float(row['Methane'])
        C2H6 = float(row['Ethane'])
        C2H4 = float(row['Ethylene'])
        C2H2 = float(row['Acetylene'])
        
        # محاسبه مجموع
        total = CH4 + C2H6 + C2H4 + C2H2
        
        if total == 0:
            return None, None, None
        
        # محاسبه درصدها (بر اساس مثلث دووال ۱)
        # در مثلث دووال: CH4%, C2H4%, C2H2%
        CH4_percent = (CH4 / total) * 100
        C2H4_percent = (C2H4 / total) * 100
        C2H2_percent = (C2H2 / total) * 100
        
        return CH4_percent, C2H4_percent, C2H2_percent
        
    except Exception as e:
        print(f"Error in Duval calculation: {e}", file=sys.stderr)
        return None, None, None

def duval_zone_detection(CH4, C2H4, C2H2):
    """Determine Duval Triangle zone"""
    if CH4 is None or C2H4 is None or C2H2 is None:
        return "داده ناکافی"
    
    # مناطق مثلث دووال (مثلث ۱)
    if C2H2 < 4:
        if C2H4 < 23:
            if CH4 < 50:
                return "تخلیه جزئی (PD)"
            else:
                return "تخلیه جزئی (PD) با قوس"
        else:
            if C2H4 < 40:
                return "کرونا با تخلیه (D1)"
            else:
                return "تخلیه با انرژی بالا (D2)"
    else:
        if C2H2 < 13:
            return "تخلیه با انرژی کم (D1)"
        elif C2H2 < 29:
            if C2H4 < 13:
                return "گرمایش کم دما (T1) <300°C"
            else:
                return "گرمایش متوسط (T2) 300-700°C"
        else:
            if C2H4 < 15:
                return "گرمایش زیاد دما (T3) >700°C"
            else:
                return "گرمایش و تخلیه ترکیبی (DT)"

def calculate_ternary_ratios(row):
    """Calculate ratios for ternary plot"""
    try:
        # نسبت‌های راجرز
        gases_needed = ['hydrogen', 'Methane', 'Ethane', 'Ethylene', 'Acetylene']
        
        missing_gases = [gas for gas in gases_needed if gas not in row.index or pd.isna(row[gas])]
        if missing_gases:
            return None, None, None
        
        H2 = float(row['hydrogen'])
        CH4 = float(row['Methane'])
        C2H6 = float(row['Ethane'])
        C2H4 = float(row['Ethylene'])
        C2H2 = float(row['Acetylene'])
        
        # جلوگیری از تقسیم بر صفر
        def safe_divide(a, b):
            return a / b if b != 0 else 0
        
        # نسبت‌های سه‌گانه برای نمودار ترنری
        # ۱. نسبت H2/CH4 (تخلیه/گرمایش)
        ratio1 = safe_divide(H2, CH4) if CH4 > 0 else 0
        
        # ۲. نسبت C2H4/C2H6 (درجه حرارت)
        ratio2 = safe_divide(C2H4, C2H6) if C2H6 > 0 else 0
        
        # ۳. نسبت C2H2/C2H4 (تخلیه انرژی بالا)
        ratio3 = safe_divide(C2H2, C2H4) if C2H4 > 0 else 0
        
        # نرمال‌سازی به درصد
        total = ratio1 + ratio2 + ratio3
        if total > 0:
            percent1 = (ratio1 / total) * 100
            percent2 = (ratio2 / total) * 100
            percent3 = (ratio3 / total) * 100
            return percent1, percent2, percent3
        else:
            return 33.33, 33.33, 33.33
        
    except Exception as e:
        print(f"Error in ternary calculation: {e}", file=sys.stderr)
        return None, None, None

def create_duval_triangle_plot(df):
    """Create Duval Triangle visualization"""
    
    # محاسبه نقاط برای هر رکورد
    points = []
    colors = []
    labels = []
    
    for idx, row in df.iterrows():
        CH4, C2H4, C2H2 = calculate_duval_triangle(row)
        
        if CH4 is not None and C2H4 is not None and C2H2 is not None:
            # تبدیل به مختصات مثلث متساوی الاضلاع
            # مثلث با رأس: A(0,0), B(100,0), C(50, 86.6)
            x = (C2H4 * 0.5 + CH4 * 0 + C2H2 * 1) / 100 * 100
            y = (C2H4 * 0.866 + CH4 * 0 + C2H2 * 0) / 100 * 86.6
            
            points.append((x, y))
            
            # رنگ بر اساس ریسک
            risk = row.get('RiskScore', 0)
            if risk >= 60:
                colors.append('red')
            elif risk >= 35:
                colors.append('orange')
            else:
                colors.append('green')
            
            labels.append(f"{row.get('کد_پست', '')} - {row.get('نام_تجهیز', '')}")
    
    if not points:
        return None
    
    # ایجاد نمودار
    fig = go.Figure()
    
    # اضافه کردن نقاط
    if points:
        x_vals, y_vals = zip(*points)
        fig.add_trace(go.Scatter(
            x=x_vals,
            y=y_vals,
            mode='markers',
            marker=dict(
                size=10,
                color=colors,
                opacity=0.8,
                line=dict(width=1, color='white')
            ),
            text=labels,
            hoverinfo='text',
            name='ترانسفورماتورها'
        ))
    
    # رسم مثلث دووال
    # رأس مثلث
    triangle_x = [0, 100, 50, 0]
    triangle_y = [0, 0, 86.6, 0]
    
    fig.add_trace(go.Scatter(
        x=triangle_x,
        y=triangle_y,
        mode='lines',
        line=dict(color='black', width=2),
        fill='toself',
        fillcolor='rgba(240, 240, 240, 0.3)',
        name='محدوده مثلث'
    ))
    
    # اضافه کردن برچسب مناطق
    zones = [
        {'name': 'PD', 'x': 10, 'y': 10, 'color': 'blue'},
        {'name': 'D1', 'x': 35, 'y': 50, 'color': 'purple'},
        {'name': 'D2', 'x': 65, 'y': 50, 'color': 'brown'},
        {'name': 'T1', 'x': 15, 'y': 70, 'color': 'green'},
        {'name': 'T2', 'x': 50, 'y': 70, 'color': 'orange'},
        {'name': 'T3', 'x': 85, 'y': 70, 'color': 'red'},
    ]
    
    for zone in zones:
        fig.add_annotation(
            x=zone['x'],
            y=zone['y'],
            text=zone['name'],
            showarrow=False,
            font=dict(size=10, color=zone['color'])
        )
    
    # تنظیمات layout
    fig.update_layout(
        title='مثلث دووال (Duval Triangle) - تشخیص نوع خطا',
        xaxis=dict(
            title='%C₂H₄',
            range=[-10, 110],
            showgrid=False,
            zeroline=False,
            showticklabels=False
        ),
        yaxis=dict(
            title='%CH₄ / %C₂H₂',
            range=[-10, 100],
            showgrid=False,
            zeroline=False,
            showticklabels=False,
            scaleanchor="x",
            scaleratio=0.866
        ),
        showlegend=False,
        plot_bgcolor='white',
        width=800,
        height=600,
        annotations=[
            dict(
                x=0, y=0,
                xref="x", yref="y",
                text="C₂H₂",
                showarrow=False,
                font=dict(size=12)
            ),
            dict(
                x=100, y=0,
                xref="x", yref="y",
                text="C₂H₄",
                showarrow=False,
                font=dict(size=12)
            ),
            dict(
                x=50, y=86.6,
                xref="x", yref="y",
                text="CH₄",
                showarrow=False,
                font=dict(size=12)
            )
        ]
    )
    
    return fig

def create_ternary_plot(df):
    """Create Ternary Plot visualization"""
    
    # محاسبه نقاط
    points = []
    colors = []
    labels = []
    zone_labels = []
    
    for idx, row in df.iterrows():
        ratio1, ratio2, ratio3 = calculate_ternary_ratios(row)
        
        if ratio1 is not None and ratio2 is not None and ratio3 is not None:
            # در نمودار ترنری، مجموع سه نسبت باید ۱۰۰ باشد
            total = ratio1 + ratio2 + ratio3
            if total > 0:
                norm_ratio1 = (ratio1 / total) * 100
                norm_ratio2 = (ratio2 / total) * 100
                norm_ratio3 = (ratio3 / total) * 100
                
                points.append((norm_ratio1, norm_ratio2, norm_ratio3))
                
                # تشخیص منطقه
                zone = "ناشناخته"
                if norm_ratio1 > 60:
                    zone = "تخلیه جزئی"
                elif norm_ratio2 > 60:
                    zone = "گرمایش"
                elif norm_ratio3 > 60:
                    zone = "تخلیه با انرژی بالا"
                elif norm_ratio1 > 40 and norm_ratio2 > 40:
                    zone = "ترکیبی (تخلیه/گرمایش)"
                
                zone_labels.append(zone)
                
                # رنگ بر اساس ریسک
                risk = row.get('RiskScore', 0)
                if risk >= 60:
                    colors.append('red')
                elif risk >= 35:
                    colors.append('orange')
                else:
                    colors.append('green')
                
                labels.append(f"{row.get('کد_پست', '')} - {zone}")
    
    if not points:
        return None
    
    # ایجاد نمودار ترنری
    fig = go.Figure()
    
    # اضافه کردن نقاط
    if points:
        a_vals, b_vals, c_vals = zip(*points)
        
        # برای plotly ternary، مقادیر باید بین ۰ تا ۱ باشد
        a_vals = np.array(a_vals) / 100
        b_vals = np.array(b_vals) / 100
        c_vals = np.array(c_vals) / 100
        
        fig.add_trace(go.Scatterternary({
            'mode': 'markers',
            'a': a_vals,
            'b': b_vals,
            'c': c_vals,
            'marker': {
                'symbol': 100,
                'color': colors,
                'size': 12,
                'line': {'width': 1, 'color': 'white'}
            },
            'text': labels,
            'hoverinfo': 'text',
            'name': 'ترانسفورماتورها'
        }))
    
    # تنظیمات layout
    fig.update_layout({
        'title': 'نمودار ترنری (سه‌متغیره) - تحلیل نسبت گازها',
        'ternary': {
            'sum': 1,
            'aaxis': {
                'title': 'H₂/CH₄ (تخلیه/گرمایش)',
                'min': 0.01,
                'linewidth': 2,
                'ticks': 'outside'
            },
            'baxis': {
                'title': 'C₂H₄/C₂H₆ (درجه حرارت)',
                'min': 0.01,
                'linewidth': 2,
                'ticks': 'outside'
            },
            'caxis': {
                'title': 'C₂H₂/C₂H₄ (تخلیه انرژی بالا)',
                'min': 0.01,
                'linewidth': 2,
                'ticks': 'outside'
            }
        },
        'showlegend': False,
        'width': 800,
        'height': 600
    })
    
    return fig

# -------------------- Main Application --------------------
st.markdown('<div class="rtl">', unsafe_allow_html=True)

# Title
st.title("⚡ پایش هوشمند روغن ترانسفورماتورها")
st.caption("بر پایه استاندارد IEC 60599 | تحلیل گازهای محلول (DGA) | نسخه ۲.۰")

# Sidebar
with st.sidebar:
    st.markdown("### 📁 بارگذاری داده‌ها")
    
    uploaded_file = st.file_uploader(
        "فایل CSV آزمون روغن را انتخاب کنید",
        type=['csv'],
        help="فایل CSV با ستون SampleName"
    )
    
    if uploaded_file is not None:
        with st.spinner("در حال بارگذاری و پردازش داده‌ها..."):
            df = load_and_parse(uploaded_file)
            
        if df is not None:
            st.success(f"✅ {len(df)} رکورد با موفقیت بارگذاری شد")
            
            # Show file info
            with st.expander("📊 اطلاعات فایل"):
                st.write(f"**تعداد رکوردها:** {len(df)}")
                st.write(f"**تعداد ستون‌ها:** {len(df.columns)}")
                
                # FIXED: تاریخ شمسی با بررسی NaN
                if 'تاریخ_شمسی' in df.columns:
                    valid_dates = df['تاریخ_شمسی'].dropna()
                    if not valid_dates.empty:
                        min_date = valid_dates.min()
                        max_date = valid_dates.max()
                        st.write(f"**بازه تاریخی:** {min_date} تا {max_date}")
                    else:
                        st.write("**بازه تاریخی:** اطلاعات تاریخ موجود نیست")
                else:
                    st.write("**بازه تاریخی:** ستون تاریخ یافت نشد")
            
            # Calculate risk scores
            df['RiskScore'] = df.apply(calculate_risk_score, axis=1)
            df['RiskFlag'] = df['RiskScore'].apply(get_risk_flag)
            df['RiskLevel'] = df['RiskScore'].apply(get_risk_level)
            
            # محاسبه تحلیل DGA
            st.markdown("### 🔬 تحلیل گازهای محلول (DGA)")
            with st.spinner("در حال تحلیل گازهای محلول..."):
                # محاسبه مثلث دووال برای هر رکورد
                duval_results = []
                for idx, row in df.iterrows():
                    CH4, C2H4, C2H2 = calculate_duval_triangle(row)
                    zone = duval_zone_detection(CH4, C2H4, C2H2)
                    duval_results.append({
                        'CH4%': CH4,
                        'C2H4%': C2H4,
                        'C2H2%': C2H2,
                        'DuvalZone': zone
                    })
                
                duval_df = pd.DataFrame(duval_results)
                df = pd.concat([df, duval_df], axis=1)
            
            st.session_state.df = df
            st.success("✅ تحلیل DGA تکمیل شد")
            
        else:
            st.error("خطا در پردازش فایل")
            st.stop()
    else:
        st.info("👈 لطفاً فایل CSV را بارگذاری کنید")
        
        # Demo data option با داده‌های گازی کامل
        if st.button("استفاده از داده‌های نمونه", type="secondary"):
            # Create sample data با مقادیر گاز
            sample_data = {
                'SampleName': ['6515A T1 SANATI BAHARESTAN 1404-09-29', 
                              '5165I T2 ANDISHEH3 1404-09-28',
                              '7427T T1 HEMATI 1404-09-27',
                              '7407H T3 JAMKARAN230 1404-09-25',
                              '5245L T2 SAYAR GOLShAHR 1404-09-22'],
                'TCG': [1500, 3500, 800, 1004, 976],
                'TAN': [0.05, 0.25, 0.08, 0.003, 0.003],
                'BreakdownVoltage': [60, 35, 55, 67, 66],
                'WaterContents': [20, 45, 25, 9, 9],
                'ASROG': ['بدون عیب', 'حالت 5 : خطای حرارتی', 'تخلیه جزیی', 
                         'تخلیه جزیی', 'خطای حرارتی بیشتر از 700 درجه'],
                'hydrogen': [75, 394, 157, 176, 23],
                'Methane': [19, 1126, 10, 35, 69],
                'Ethane': [0, 525, 1, 20, 33],
                'Ethylene': [3, 1669, 7, 12, 280],
                'Acetylene': [0, 8, 3, 0, 3],
                'CarbonMonoxide': [400, 1700, 251, 744, 511],
                'CarbonDioxide': [1566, 4002, 1044, 3044, 2401]
            }
            df = pd.DataFrame(sample_data)
            # Convert to CSV bytes and parse
            csv_bytes = df.to_csv(index=False).encode('utf-8')
            df_parsed = load_and_parse(BytesIO(csv_bytes))
            if df_parsed is not None:
                df_parsed['RiskScore'] = df_parsed.apply(calculate_risk_score, axis=1)
                df_parsed['RiskFlag'] = df_parsed['RiskScore'].apply(get_risk_flag)
                df_parsed['RiskLevel'] = df_parsed['RiskScore'].apply(get_risk_level)
                
                # محاسبه تحلیل DGA
                duval_results = []
                for idx, row in df_parsed.iterrows():
                    CH4, C2H4, C2H2 = calculate_duval_triangle(row)
                    zone = duval_zone_detection(CH4, C2H4, C2H2)
                    duval_results.append({
                        'CH4%': CH4,
                        'C2H4%': C2H4,
                        'C2H2%': C2H2,
                        'DuvalZone': zone
                    })
                
                duval_df = pd.DataFrame(duval_results)
                df_parsed = pd.concat([df_parsed, duval_df], axis=1)
                
                st.session_state.df = df_parsed
            st.rerun()
        
        st.stop()

# Main content
if 'df' in st.session_state:
    df = st.session_state.df
    
    # KPI Cards
    st.subheader("📊 شاخص‌های کلیدی")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_trans = len(df)
        st.metric("تعداد کل ترانس‌ها", f"{total_trans:,}")
    
    with col2:
        high_risk = (df['RiskScore'] >= 60).sum()
        delta_value = f"{high_risk/total_trans*100:.1f}%" if total_trans > 0 else "0%"
        st.metric("🔴 پرریسک", f"{high_risk:,}", delta=delta_value)
    
    with col3:
        medium_risk = ((df['RiskScore'] >= 35) & (df['RiskScore'] < 60)).sum()
        st.metric("🟡 متوسط ریسک", f"{medium_risk:,}")
    
    with col4:
        if 'TCG' in df.columns:
            avg_tcg = df['TCG'].mean()
            if pd.notna(avg_tcg):
                st.metric("میانگین TCG", f"{avg_tcg:,.0f}")
            else:
                st.metric("میانگین TCG", "ندارد")
        else:
            st.metric("میانگین TCG", "ستون TCG نیست")
    
    # Filters
    st.subheader("🔍 فیلترهای پیشرفته")
    
    with st.expander("فیلترها", expanded=True):
        filter_col1, filter_col2, filter_col3 = st.columns(3)
        
        with filter_col1:
            post_options = ['همه'] + sorted(df['نام_پست'].dropna().unique().tolist())
            selected_post = st.selectbox("نام پست:", post_options)
        
        with filter_col2:
            equipment_options = ['همه'] + sorted(df['نام_تجهیز'].dropna().unique().tolist())
            selected_equipment = st.selectbox("نام تجهیز:", equipment_options)
        
        with filter_col3:
            min_score = int(df['RiskScore'].min()) if not df.empty else 0
            max_score = int(df['RiskScore'].max()) if not df.empty else 100
            risk_range = st.slider("محدوده ریسک:", min_score, max_score, (min_score, max_score))
    
    # Apply filters
    filtered_df = df.copy()
    
    if selected_post != 'همه':
        filtered_df = filtered_df[filtered_df['نام_پست'] == selected_post]
    
    if selected_equipment != 'همه':
        filtered_df = filtered_df[filtered_df['نام_تجهیز'] == selected_equipment]
    
    filtered_df = filtered_df[
        (filtered_df['RiskScore'] >= risk_range[0]) & 
        (filtered_df['RiskScore'] <= risk_range[1])
    ]
    
    st.info(f"📋 **{len(filtered_df)}** رکورد مطابق فیلترها یافت شد")
    
    # Tabs - اضافه کردن تب جدید برای تحلیل DGA
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["📊 داشبورد", "📈 نمودارها", "🔬 تحلیل DGA", "📋 داده‌ها", "📥 خروجی"])
    
    with tab1:
        # Top risks
        st.subheader("🔴 ترانس‌های با بالاترین ریسک")
        
        if not filtered_df.empty:
            top_10 = filtered_df.nlargest(10, 'RiskScore')[[
                'کد_پست', 'نام_تجهیز', 'نام_پست', 'RiskFlag', 
                'RiskScore', 'RiskLevel', 'TCG', 'TAN', 'ASROG'
            ]]
            
            # Add row numbers
            top_10 = top_10.reset_index(drop=True)
            top_10.index = top_10.index + 1
            
            st.dataframe(
                top_10,
                use_container_width=True,
                column_config={
                    'RiskScore': st.column_config.ProgressColumn(
                        "ریسک",
                        help="امتیاز ریسک",
                        format="%d",
                        min_value=0,
                        max_value=100
                    )
                }
            )
        else:
            st.warning("❌ داده‌ای برای نمایش وجود ندارد")
        
        # Charts in columns
        chart_col1, chart_col2 = st.columns(2)
        
        with chart_col1:
            if not filtered_df.empty:
                # Risk distribution pie
                risk_counts = filtered_df['RiskFlag'].value_counts()
                fig = px.pie(
                    values=risk_counts.values,
                    names=risk_counts.index,
                    title='توزیع ریسک',
                    color=risk_counts.index,
                    color_discrete_map={'🔴': '#dc3545', '🟡': '#ffc107', '🟢': '#28a745'}
                )
                fig.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("📊 نمودار توزیع ریسک: داده‌ای موجود نیست")
        
        with chart_col2:
            if not filtered_df.empty and 'TCG' in filtered_df.columns:
                # TCG histogram
                fig = px.histogram(
                    filtered_df, 
                    x='TCG',
                    nbins=20,
                    title='توزیع TCG',
                    labels={'TCG': 'TCG (ppm)', 'count': 'تعداد'}
                )
                fig.update_layout(bargap=0.1)
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("📊 نمودار TCG: داده‌ای موجود نیست")
    
    with tab2:
        # Interactive charts
        st.subheader("📈 نمودارهای تعاملی")
        
        if not filtered_df.empty and 'TCG' in filtered_df.columns and 'TAN' in filtered_df.columns:
            # Scatter plot
            fig = px.scatter(
                filtered_df,
                x='TCG',
                y='TAN',
                color='RiskLevel',
                size='RiskScore',
                hover_data=['کد_پست', 'نام_پست', 'نام_تجهیز'],
                title='نقشه پراکندگی TCG vs TAN',
                labels={'TCG': 'TCG (ppm)', 'TAN': 'TAN (mg KOH/g)'},
                color_discrete_map={'پرریسک': 'red', 'متوسط': 'orange', 'کم‌ریسک': 'green'}
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Box plot
            if 'BreakdownVoltage' in filtered_df.columns:
                fig = px.box(
                    filtered_df,
                    x='RiskLevel',
                    y='BreakdownVoltage',
                    color='RiskLevel',
                    title='ولتاژ شکست بر اساس سطح ریسک',
                    labels={'BreakdownVoltage': 'ولتاژ شکست (kV)', 'RiskLevel': 'سطح ریسک'},
                    color_discrete_map={'پرریسک': 'red', 'متوسط': 'orange', 'کم‌ریسک': 'green'}
                )
                st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("📈 برای نمایش نمودارها، داده‌های کافی موجود نیست")
    
    with tab3:
        # DGA Analysis
        st.subheader("🔬 تحلیل گازهای محلول (DGA)")
        
        # بررسی وجود ستون‌های گازی
        required_gases = ['hydrogen', 'Methane', 'Ethane', 'Ethylene', 'Acetylene']
        missing_gases = [gas for gas in required_gases if gas not in filtered_df.columns]
        
        if missing_gases:
            st.warning(f"❌ ستون‌های گازی زیر برای تحلیل DGA موجود نیستند: {', '.join(missing_gases)}")
            st.info("لطفاً فایل CSV را با ستون‌های گازی کامل بارگذاری کنید.")
        elif filtered_df.empty:
            st.warning("❌ داده‌ای برای تحلیل وجود ندارد")
        else:
            # خلاصه تحلیل DGA
            st.markdown("### 📋 خلاصه تحلیل DGA")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                # تعداد ترانس با داده‌های گازی کامل
                complete_dga = filtered_df.dropna(subset=required_gases).shape[0]
                st.metric("داده‌های کامل DGA", f"{complete_dga}/{len(filtered_df)}")
            
            with col2:
                # شایع‌ترین منطقه دووال
                if 'DuvalZone' in filtered_df.columns:
                    common_zone = filtered_df['DuvalZone'].mode()
                    if not common_zone.empty:
                        st.metric("شایع‌ترین خطا", common_zone.iloc[0])
                    else:
                        st.metric("شایع‌ترین خطا", "ندارد")
                else:
                    st.metric("شایع‌ترین خطا", "محاسبه نشده")
            
            with col3:
                # میانگین TCG برای DGA
                avg_tcg_dga = filtered_df['TCG'].mean() if 'TCG' in filtered_df.columns else 0
                st.metric("میانگین TCG", f"{avg_tcg_dga:,.0f}")
            
            with col4:
                # درصد ترانس با تخلیه الکتریکی (C2H2 > 0)
                if 'Acetylene' in filtered_df.columns:
                    discharge_count = (filtered_df['Acetylene'] > 0).sum()
                    discharge_percent = (discharge_count / len(filtered_df)) * 100 if len(filtered_df) > 0 else 0
                    st.metric("تخلیه الکتریکی", f"{discharge_percent:.1f}%")
                else:
                    st.metric("تخلیه الکتریکی", "ندارد")
            
            # نمودارهای DGA
            st.markdown("### 📊 نمودارهای تشخیص خطا")
            
            # مثلث دووال
            st.markdown("#### 📐 مثلث دووال (Duval Triangle)")
            st.caption("روش تشخیص نوع خطا بر اساس نسبت گازهای CH₄، C₂H₄ و C₂H₂")
            
            duval_fig = create_duval_triangle_plot(filtered_df)
            if duval_fig:
                st.plotly_chart(duval_fig, use_container_width=True)
                
                # تفسیر مناطق دووال
                with st.expander("📖 راهنمای مناطق مثلث دووال"):
                    st.markdown("""
                    **PD (Partial Discharge) - تخلیه جزئی:**
                    - تخلیه الکتریکی با انرژی کم
                    - معمولاً در حباب‌های گاز یا حفره‌ها رخ می‌دهد
                    
                    **D1 (Low Energy Discharge) - تخلیه با انرژی کم:**
                    - تخلیه بین سیم پیچ‌ها یا به زمین
                    - ممکن است باعث ایجاد کربن در روغن شود
                    
                    **D2 (High Energy Discharge) - تخلیه با انرژی بالا:**
                    - تخلیه قوس الکتریکی شدید
                    - خطرناک و نیاز به توجه فوری
                    
                    **T1 (Thermal Fault <300°C) - گرمایش کم دما:**
                    - گرمایش تا ۳۰۰ درجه سانتیگراد
                    - معمولاً ناشی از اتصالات شل یا نقص عایقی
                    
                    **T2 (Thermal Fault 300-700°C) - گرمایش متوسط:**
                    - گرمایش بین ۳۰۰ تا ۷۰۰ درجه
                    - ممکن است ناشی از اتصال کوتاه حلقه‌ها باشد
                    
                    **T3 (Thermal Fault >700°C) - گرمایش زیاد دما:**
                    - گرمایش شدید بالای ۷۰۰ درجه
                    - خطرناک و نیاز به تعمیر فوری
                    """)
            else:
                st.info("📊 داده‌های کافی برای رسم مثلث دووال موجود نیست")
            
            # نمودار ترنری
            st.markdown("#### 🔶 نمودار ترنری (Ternary Plot)")
            st.caption("تحلیل سه‌بعدی نسبت‌های گازی H₂/CH₄، C₂H₄/C₂H₆ و C₂H₂/C₂H₄")
            
            ternary_fig = create_ternary_plot(filtered_df)
            if ternary_fig:
                st.plotly_chart(ternary_fig, use_container_width=True)
                
                # تفسیر نمودار ترنری
                with st.expander("📖 راهنمای نمودار ترنری"):
                    st.markdown("""
                    **H₂/CH₄ (رأس بالایی):**
                    - نسبت بالا: احتمال تخلیه الکتریکی
                    - نسبت پایین: احتمال گرمایش
                    
                    **C₂H₄/C₂H₆ (رأس چپ):**
                    - نسبت بالا: درجه حرارت بالا
                    - نسبت پایین: درجه حرارت پایین
                    
                    **C₂H₂/C₂H₄ (رأس راست):**
                    - نسبت بالا: تخلیه با انرژی بالا
                    - نسبت پایین: تخلیه با انرژی کم یا گرمایش
                    """)
            else:
                st.info("📊 داده‌های کافی برای رسم نمودار ترنری موجود نیست")
            
            # جدول نتایج DGA
            st.markdown("### 📋 نتایج تحلیل DGA")
            
            if 'DuvalZone' in filtered_df.columns:
                dga_display_cols = [
                    'کد_پست', 'نام_تجهیز', 'نام_پست', 
                    'RiskFlag', 'RiskScore', 'TCG',
                    'CH4%', 'C2H4%', 'C2H2%', 'DuvalZone'
                ]
                
                # Only show columns that exist
                dga_display_cols = [col for col in dga_display_cols if col in filtered_df.columns]
                
                st.dataframe(
                    filtered_df[dga_display_cols],
                    use_container_width=True,
                    hide_index=True
                )
                
                # توزیع مناطق دووال
                st.markdown("#### 📊 توزیع انواع خطا")
                if not filtered_df['DuvalZone'].isna().all():
                    zone_counts = filtered_df['DuvalZone'].value_counts()
                    fig = px.bar(
                        x=zone_counts.index,
                        y=zone_counts.values,
                        title='توزیع مناطق تشخیص خطا',
                        labels={'x': 'نوع خطا', 'y': 'تعداد'}
                    )
                    fig.update_layout(xaxis_tickangle=-45)
                    st.plotly_chart(fig, use_container_width=True)
    
    with tab4:
        # Data table
        st.subheader("📋 جدول کامل داده‌ها")
        
        if not filtered_df.empty:
            display_cols = [
                'کد_پست', 'نام_تجهیز', 'نام_پست', 'تاریخ_شمسی',
                'RiskFlag', 'RiskScore', 'RiskLevel',
                'TCG', 'TAN', 'BreakdownVoltage', 'WaterContents', 'ASROG'
            ]
            
            # اضافه کردن ستون‌های DGA اگر موجود باشند
            dga_cols = ['CH4%', 'C2H4%', 'C2H2%', 'DuvalZone']
            for col in dga_cols:
                if col in filtered_df.columns:
                    display_cols.append(col)
            
            # Only show columns that exist
            display_cols = [col for col in display_cols if col in filtered_df.columns]
            
            st.dataframe(
                filtered_df[display_cols],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.warning("❌ داده‌ای برای نمایش وجود ندارد")
    
    with tab5:
        # Export
        st.subheader("📥 خروجی و گزارش")
        
        if not filtered_df.empty:
            col1, col2, col3 = st.columns(3)
            
            with col1:
                # Export filtered data
                csv_data = filtered_df.to_csv(index=False, encoding='utf-8-sig').encode('utf-8-sig')
                st.download_button(
                    label="📥 دانلود CSV فیلترشده",
                    data=csv_data,
                    file_name=f"transformer_filtered_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                    mime="text/csv",
                    type="primary"
                )
            
            with col2:
                # Export full report
                excel_buffer = BytesIO()
                with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                    filtered_df.to_excel(writer, sheet_name='داده‌های کامل', index=False)
                    
                    # Summary sheet
                    summary_df = filtered_df.groupby('RiskLevel').agg({
                        'کد_پست': 'count',
                        'TCG': 'mean',
                        'TAN': 'mean',
                        'BreakdownVoltage': 'mean'
                    }).round(2)
                    summary_df.to_excel(writer, sheet_name='خلاصه')
                    
                    # DGA analysis sheet
                    if 'DuvalZone' in filtered_df.columns:
                        dga_summary = filtered_df.groupby('DuvalZone').agg({
                            'کد_پست': 'count',
                            'RiskScore': 'mean',
                            'TCG': 'mean'
                        }).round(2)
                        dga_summary.to_excel(writer, sheet_name='تحلیل_DGA')
                
                excel_buffer.seek(0)
                
                st.download_button(
                    label="📊 دانلود گزارش Excel",
                    data=excel_buffer,
                    file_name=f"transformer_report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            with col3:
                # Export DGA report
                if 'DuvalZone' in filtered_df.columns:
                    dga_report_df = filtered_df[['کد_پست', 'نام_تجهیز', 'نام_پست', 
                                                 'DuvalZone', 'RiskScore', 'TCG',
                                                 'CH4%', 'C2H4%', 'C2H2%']].dropna()
                    
                    if not dga_report_df.empty:
                        dga_buffer = BytesIO()
                        dga_report_df.to_csv(dga_buffer, index=False, encoding='utf-8-sig')
                        dga_buffer.seek(0)
                        
                        st.download_button(
                            label="🔬 دانلود گزارش DGA",
                            data=dga_buffer,
                            file_name=f"dga_analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                            mime="text/csv",
                            type="secondary"
                        )
            
            # Report summary
            st.markdown("---")
            st.subheader("📋 خلاصه گزارش")
            
            summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
            
            with summary_col1:
                high_risk_count = filtered_df[filtered_df['RiskLevel'] == 'پرریسک'].shape[0]
                st.metric("تعداد ترانس‌های پرریسک", high_risk_count)
            
            with summary_col2:
                avg_risk = filtered_df['RiskScore'].mean()
                if pd.notna(avg_risk):
                    st.metric("میانگین امتیاز ریسک", f"{avg_risk:.1f}")
                else:
                    st.metric("میانگین امتیاز ریسک", "ندارد")
            
            with summary_col3:
                if 'TCG' in filtered_df.columns:
                    high_tcg = filtered_df[filtered_df['TCG'] > 2000].shape[0]
                    st.metric("TCG بالای ۲۰۰۰", high_tcg)
                else:
                    st.metric("TCG بالای ۲۰۰۰", "ستون TCG نیست")
            
            with summary_col4:
                if 'DuvalZone' in filtered_df.columns:
                    critical_zones = filtered_df[filtered_df['DuvalZone'].str.contains('D2|T3|DT', na=False)].shape[0]
                    st.metric("خطاهای بحرانی DGA", critical_zones)
        else:
            st.warning("❌ داده‌ای برای خروجی گرفتن وجود ندارد")

st.markdown('</div>')  # End RTL

print("✅ App loaded successfully", file=sys.stderr)
