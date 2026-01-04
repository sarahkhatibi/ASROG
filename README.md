# ASROG
Below is a complete, production-grade Streamlit dashboard that ingests the transformer oil test CSV you uploaded, parses the Persian structure, applies IEC 60599 rules, and gives an interactive, risk-ranked, filterable, downloadable report – ready to be pasted into a single Python file (app.py) and run locally or on Streamlit Cloud.

# پایش هوشمند روغن ترانسفورماتورها ⚡

[![Streamlit App](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://share.streamlit.io/YOUR_USER/YOUR_REPO/main/app.py)

## 📋 معرفی
این برنامه یک **داشبورد تعاملی فارسی** برای تحلیل گزارش‌های آزمون روغن ترانسفورماتورها بر اساس استاندارد IEC 60599 است.  
فایل CSV حاوی نتایج DGA، ولتاژ شکست، TAN، رطوبت و … را بارگذاری می‌کنید؛ برنامه به‌صورت خودکار:
- ستون `SampleName` را به ۴ بخش (کد پست، نام تجهیز، نام پست، تاریخ شمسی) تجزیه می‌کند.  
- امتیاز ریسک (RiskScore 0-100) و پرچم رنگی (🟢🟡🔴) برای هر ترانس محاسبه می‌کند.  
- فیلترهای فارسی، نمودارهای تعاملی و خروجی Excel تحویل می‌دهد.

## 🚀 راه‌اندازی سریع

### ۱) نصب محیط
```bash
git clone https://github.com/YOUR_USER/TransformerOilDashboard.git
cd TransformerOilDashboard
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
pip install -r requirements.txt
