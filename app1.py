# app.py
# -*- coding: utf-8 -*-
import sys, traceback
try:
    import streamlit as st
    import pandas as pd
    import plotly.express as px
    import plotly.graph_objects as go
    from io import BytesIO
    import re
    from datetime import datetime
    import numpy as np
    # لاگ موفقیت
    print("✅ All imports successful", file=sys.stderr)
except Exception as e:
    print("🔴 Startup import error:", e, file=sys.stderr)
    traceback.print_exc()
    raise

# --------------------  Persian styling  --------------------
st.set_page_config(
    page_title="پایش هوشمند روغن ترانسفورماتورها",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Vazirmatn:wght@300;400;600;900&display=swap');
    html, body, [class*="css"] {
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
</style>
""", unsafe_allow_html=True)

# --------------------  helpers  --------------------
@st.cache_data
def load_and_parse(file):
    df = pd.read_csv(file, low_memory=False)
    # split SampleName
    df[['کد_پست', 'نام_تجهیز', 'نام_پست', 'تاریخ_شمسی']] = (
        df['SampleName'].str.extract(r'(\w+)\s+(\w+)\s+(.+)\s+(\d{4}-\d{2}-\d{2})'))
    df['تاریخ_میلادی'] = pd.to_datetime(df['InjDateTime'])
    # numeric cols
    num_cols = ['TCG', 'TAN', 'BreakdownVoltage', 'WaterContents', 'DDF']
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    return df

def risk_score(row):
    # simple rule-based score 0-100
    score = 0
    if pd.notna(row['TCG']) and row['TCG'] > 2000:          score += 30
    if pd.notna(row['TAN']) and row['TAN'] > 0.1:           score += 15
    if pd.notna(row['BreakdownVoltage']) and row['BreakdownVoltage'] < 50: score += 20
    if pd.notna(row['WaterContents']) and row['WaterContents'] > 30:      score += 15
    if 'حالت 5' in str(row['ASROG']):                       score += 20
    if 'تجزیه حرارتی' in str(row['ASROG']):                 score += 10
    return min(100, score)

def flag_color(risk):
    if risk >= 60: return '🔴'
    if risk >= 35: return '🟡'
    return '🟢'

# --------------------  sidebar  --------------------
with st.sidebar:
    st.markdown('<div class="rtl">', unsafe_allow_html=True)
    uploaded = st.file_uploader("📁 فایل CSV آزمون روغن را بارگذاری کنید", type=['csv'])
    if uploaded:
        df = load_and_parse(uploaded)
        st.success(f"✅ {len(df)} رکورد بارگذاری شد")
    else:
        st.info("👈 لطفاً فایل CSV را آپلود کنید")
        st.stop()
    st.markdown('</div>')

# --------------------  body  --------------------
st.markdown('<div class="rtl">', unsafe_allow_html=True)
st.title("⚡ پایش هوشمند روغن ترانسفورماتورها")
st.caption("بر پایه استاندارد IEC 60599 | Risk-Based Maintenance")

# risk calculation
df['RiskScore'] = df.apply(risk_score, axis=1)
df['RiskFlag']  = df['RiskScore'].apply(flag_color)

# --------------------  KPI row  --------------------
kpi1, kpi2, kpi3, kpi4 = st.columns(4)
with kpi1:
    st.metric("تعداد ترانس‌ها", len(df))
with kpi2:
    st.metric("🔴 پرریسک", (df['RiskScore'] >= 60).sum())
with kpi3:
    st.metric("🟡 متوسط ریسک", ((df['RiskScore'] >= 35) & (df['RiskScore'] < 60)).sum())
with kpi4:
    st.metric("میانگین TCG", f"{df['TCG'].mean():.0f}")

# --------------------  filters  --------------------
with st.expander("🔍 فیلترها"):
    c1, c2, c3 = st.columns(3)
    with c1:
        post_options = ['همه'] + df['نام_پست'].dropna().unique().tolist()
        post_filter = st.selectbox("نام پست:", post_options)
    with c2:
        taj_options = ['همه'] + df['نام_تجهیز'].dropna().unique().tolist()
        taj_filter = st.selectbox("نام تجهیز:", taj_options)
    with c3:
        risk_slider = st.slider("ریسک ≤", 0, 100, 100)

mask = True
if post_filter != 'همه': mask &= df['نام_پست'].eq(post_filter)
if taj_filter != 'همه': mask &= df['نام_تجهیز'].eq(taj_filter)
mask &= df['RiskScore'] <= risk_slider
dff = df[mask]

st.info(f"تعداد رکوردهای فیلترشده: {len(dff)}")

# --------------------  tabs  --------------------
tab1, tab2, tab3, tab4 = st.tabs(["📊 داشبورد", "📈 نمودارها", "📋 جدول ریسک", "📥 خروجی"])

with tab1:
    # top risk table
    st.subheader("🔴 ۱۰ ترانس با بالاترین ریسک")
    top_risk = dff.nlargest(10, 'RiskScore')[['کد_پست', 'نام_تجهیز', 'نام_پست', 'RiskScore', 'RiskFlag', 'ASROG']]
    st.dataframe(top_risk, use_container_width=True, hide_index=True)

    # 2-col charts
    col1, col2 = st.columns(2)
    with col1:
        fig = px.pie(dff, names='RiskFlag', title='توزیع ریسک‌ها', hole=0.5,
                     color_discrete_map={'🔴':'red','🟡':'gold','🟢':'green'})
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        fig = px.histogram(dff, x='TCG', nbins=30, title='توزیع TCG')
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.subheader("📈 نمودارهای تعاملی")
    # scatter
    fig = px.scatter(dff, x='TCG', y='TAN', color='RiskScore',
                     hover_data=['کد_پست','نام_پست'], title='TCG vs TAN (رنگ=ریسک)')
    st.plotly_chart(fig, use_container_width=True)
    # box
    fig = px.box(dff, x='نام_تجهیز', y='BreakdownVoltage', title='ولتاژ شکست بر حسب نوع تجهیز')
    st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.subheader("📋 جدول قابل جستجو")
    cols = ['کد_پست','نام_تجهیز','نام_پست','تاریخ_شمسی','RiskFlag','RiskScore','TCG','TAN','BreakdownVoltage','WaterContents','ASROG']
    st.dataframe(dff[cols], use_container_width=True, hide_index=True)

with tab4:
    st.subheader("📥 دانلود گزاراک نهایی")
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
        dff.to_excel(writer, sheet_name='RawData', index=False)
        dff.nlargest(20, 'RiskScore')[cols].to_excel(writer, sheet_name='Top20Risk', index=False)
    excel_buffer.seek(0)
    st.download_button(
        label="📊 دانلود Excel کامل",
        data=excel_buffer,
        file_name=f"TransformerOilDashboard_{datetime.now():%Y%m%d_%H%M}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

st.markdown('</div>')  # end rtl
