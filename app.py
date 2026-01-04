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
        # Pattern: "6515A T1 SANATI BAHARESTAN 1404-09-29"
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
        
        # Convert numeric columns
        num_cols = ['TCG', 'TAN', 'BreakdownVoltage', 'WaterContents', 'DDF']
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

# -------------------- Main Application --------------------
st.markdown('<div class="rtl">', unsafe_allow_html=True)

# Title
st.title("⚡ پایش هوشمند روغن ترانسفورماتورها")
st.caption("بر پایه استاندارد IEC 60599 | نسخه ۱.۰")

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
            
            st.session_state.df = df
        else:
            st.error("خطا در پردازش فایل")
            st.stop()
    else:
        st.info("👈 لطفاً فایل CSV را بارگذاری کنید")
        
        # Demo data option
        if st.button("استفاده از داده‌های نمونه", type="secondary"):
            # Create sample data
            sample_data = {
                'SampleName': ['6515A T1 SANATI BAHARESTAN 1404-09-29', 
                              '5165I T2 ANDISHEH3 1404-09-28',
                              '7427T T1 HEMATI 1404-09-27'],
                'TCG': [1500, 3500, 800],
                'TAN': [0.05, 0.25, 0.08],
                'BreakdownVoltage': [60, 35, 55],
                'WaterContents': [20, 45, 25],
                'ASROG': ['بدون عیب', 'حالت 5 : خطای حرارتی', 'تخلیه جزیی']
            }
            df = pd.DataFrame(sample_data)
            # Convert to CSV bytes and parse
            csv_bytes = df.to_csv(index=False).encode('utf-8')
            df_parsed = load_and_parse(BytesIO(csv_bytes))
            if df_parsed is not None:
                df_parsed['RiskScore'] = df_parsed.apply(calculate_risk_score, axis=1)
                df_parsed['RiskFlag'] = df_parsed['RiskScore'].apply(get_risk_flag)
                df_parsed['RiskLevel'] = df_parsed['RiskScore'].apply(get_risk_level)
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
    
    # Tabs
    tab1, tab2, tab3, tab4 = st.tabs(["📊 داشبورد", "📈 نمودارها", "📋 داده‌ها", "📥 خروجی"])
    
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
        # Data table
        st.subheader("📋 جدول کامل داده‌ها")
        
        if not filtered_df.empty:
            display_cols = [
                'کد_پست', 'نام_تجهیز', 'نام_پست', 'تاریخ_شمسی',
                'RiskFlag', 'RiskScore', 'RiskLevel',
                'TCG', 'TAN', 'BreakdownVoltage', 'WaterContents', 'ASROG'
            ]
            
            # Only show columns that exist
            display_cols = [col for col in display_cols if col in filtered_df.columns]
            
            st.dataframe(
                filtered_df[display_cols],
                use_container_width=True,
                hide_index=True
            )
        else:
            st.warning("❌ داده‌ای برای نمایش وجود ندارد")
    
    with tab4:
        # Export
        st.subheader("📥 خروجی و گزارش")
        
        if not filtered_df.empty:
            col1, col2 = st.columns(2)
            
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
                
                excel_buffer.seek(0)
                
                st.download_button(
                    label="📊 دانلود گزارش Excel",
                    data=excel_buffer,
                    file_name=f"transformer_report_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            # Report summary
            st.markdown("---")
            st.subheader("📋 خلاصه گزارش")
            
            summary_col1, summary_col2, summary_col3 = st.columns(3)
            
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
        else:
            st.warning("❌ داده‌ای برای خروجی گرفتن وجود ندارد")

st.markdown('</div>')  # End RTL

print("✅ App loaded successfully", file=sys.stderr)
