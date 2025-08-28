import streamlit as st
import pandas as pd
import gspread
from google.auth import default
import plotly.express as px
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, Dimension, Metric, DateRange, OrderBy
import google.generativeai as genai
from datetime import datetime
from dateutil.relativedelta import relativedelta
import math

# --- ▼▼ 設定項目 ▼▼ ---
# Streamlit Community CloudのSecretsから読み込む
# GA4_PROPERTY_ID は選択されたサイトのものを使うので、ここでは不要
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
GOOGLE_SHEET_URL = st.secrets["GOOGLE_SHEET_URL"]
# --- ▲▲ 設定はここまで ▲▲ ---

# ------------------------------------------------------------------------------------
# Streamlitの画面設定
# ------------------------------------------------------------------------------------
st.set_page_config(
    page_title="経営層向け GA4分析ダッシュボード",
    page_icon="🚀",
    layout="wide"
)
st.title("🚀 経営層向け GA4分析ダッシュボード")

# ------------------------------------------------------------------------------------
# Googleサービスへの接続（キャッシュで高速化）
# ------------------------------------------------------------------------------------
@st.cache_resource
def get_ga_client():
    return BetaAnalyticsDataClient()

@st.cache_resource
def get_gsheet():
    creds, _ = default()
    gc = gspread.authorize(creds)
    return gc.open_by_url(GOOGLE_SHEET_URL).sheet1

# ------------------------------------------------------------------------------------
# その他のヘルパー関数
# ------------------------------------------------------------------------------------
def run_ga4_report(client, property_id, dimensions, metrics, date_ranges, order_bys=None):
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=dimensions, metrics=metrics,
        date_ranges=date_ranges, order_bys=order_bys
    )
    return client.run_report(request)

def format_duration(seconds):
    if seconds == 0: return "0秒"
    minutes = math.floor(seconds / 60)
    remaining_seconds = round(seconds % 60)
    return f"{minutes}分{remaining_seconds}秒"

# ------------------------------------------------------------------------------------
# メインのダッシュボード表示エリア
# ------------------------------------------------------------------------------------
try:
    sheet = get_gsheet()
    sites = pd.DataFrame(sheet.get_all_records())

    if sites.empty:
        st.warning("分析対象のサイトが登録されていません。左のメニューから「⚙️ Settings」ページに移動して、サイトを登録してください。")
    else:
        # --- サイト選択と目標入力 ---
        site_options = sites['SiteName'].tolist()
        selected_site_name = st.selectbox("分析したいサイトを選択してください", site_options)
        selected_property_id = sites[sites['SiteName'] == selected_site_name]['PropertyID'].iloc[0]

        business_goal = st.text_input(
            "このサイトの最も重要なビジネス目標は何ですか？",
            "サイト経由の売上を増やす"
        )
        
        if st.button("📈 最新ダッシュボードを生成する"):
            # ここから先のロジックは前回とほぼ同じ。選択された property_id を使う点が異なる。
            client = get_ga_client()
            today = datetime.now()
            last_30_days_start = (today - relativedelta(days=29)).strftime('%Y-%m-%d')
            prev_30_days_start = (today - relativedelta(days=59)).strftime('%Y-%m-%d')
            prev_30_days_end = (today - relativedelta(days=30)).strftime('%Y-%m-%d')
            date_range_current = DateRange(start_date=last_30_days_start, end_date="today")
            date_range_previous = DateRange(start_date=prev_30_days_start, end_date=prev_30_days_end)

            with st.spinner("各種データをGA4から取得中..."):
                # (KPI、詳細、人気ページのデータ取得ロジックは前回と同じなので省略...
                # ただし、GA4_PROPERTY_ID の代わりに selected_property_id を使う)
                response_kpi = run_ga4_report(
                    client=client, property_id=selected_property_id, dimensions=[],
                    metrics=[Metric(name="activeUsers"), Metric(name="sessions"), Metric(name="conversions"), Metric(name="averageSessionDuration")],
                    date_ranges=[date_range_current, date_range_previous]
                )
                current_metrics = [float(v.value) for v in response_kpi.rows[0].metric_values] if response_kpi.rows else [0, 0, 0, 0]
                prev_metrics = [float(v.value) for v in response_kpi.rows[1].metric_values] if len(response_kpi.rows) > 1 else [0, 0, 0, 0]

                response_details = run_ga4_report(
                    client=client, property_id=selected_property_id,
                    dimensions=[Dimension(name="sessionDefaultChannelGroup"), Dimension(name="deviceCategory"), Dimension(name="userAgeBracket")],
                    metrics=[Metric(name="activeUsers")], date_ranges=[date_range_current]
                )
                details_data = [{"チャネル": row.dimension_values[0].value, "デバイス": row.dimension_values[1].value, 
                                "年齢層": row.dimension_values[2].value, "ユーザー数": int(row.metric_values[0].value)} for row in response_details.rows]
                df_details = pd.DataFrame(details_data)

                response_pages = run_ga4_report(
                    client=client, property_id=selected_property_id,
                    dimensions=[Dimension(name="pageTitle")], metrics=[Metric(name="screenPageViews")],
                    date_ranges=[date_range_current], order_bys=[OrderBy(metric={'metric_name': 'screenPageViews'}, desc=True)]
                )
                page_data = [{"ページタイトル": row.dimension_values[0].value, "表示回数": int(row.metric_values[0].value)} for row in response_pages.rows]
                df_pages = pd.DataFrame(page_data).head(5)

            # UI描画 (前回と同じ)
            st.header("1. サイトの健康状態")
            kpi_cols = st.columns(4)
            kpi_cols[0].metric("訪問ユーザー数", f"{int(current_metrics[0]):,}", f"{int(current_metrics[0] - prev_metrics[0]):,}")
            kpi_cols[1].metric("サイト訪問回数", f"{int(current_metrics[1]):,}", f"{int(current_metrics[1] - prev_metrics[1]):,}")
            kpi_cols[2].metric("平均サイト滞在時間", format_duration(current_metrics[3]), f"{format_duration(current_metrics[3] - prev_metrics[3])}")
            kpi_cols[3].metric("成果（CV）数", f"{int(current_metrics[2]):,}", f"{int(current_metrics[2] - prev_metrics[2]):,}")
            
            st.header("2. 顧客インサイト")
            viz_cols = st.columns(4)

            if not df_details.empty:
                df_channel = df_details.groupby("チャネル")["ユーザー数"].sum().nlargest(5)
                viz_cols[0].bar_chart(df_channel, use_container_width=True)
                df_age = df_details.groupby("年齢層")["ユーザー数"].sum().sort_index()
                viz_cols[2].bar_chart(df_age, use_container_width=True)
                df_device = df_details.groupby("デバイス")["ユーザー数"].sum()
                viz_cols[3].bar_chart(df_device, use_container_width=True)
            else:
                viz_cols[0].write("チャネル データなし"); viz_cols[2].write("年齢層 データなし"); viz_cols[3].write("デバイス データなし")
            
            if not df_pages.empty:
                df_pages_chart = df_pages.set_index("ページタイトル")["表示回数"]
                viz_cols[1].bar_chart(df_pages_chart, use_container_width=True)
            else:
                viz_cols[1].write("人気ページ データなし")

            # Geminiによる提案 (前回と同じ)
            with st.spinner("AIが「次の一手」を分析・提案中..."):
                channel_str = df_channel.to_string() if 'df_channel' in locals() and not df_channel.empty else "データなし"
                pages_str = df_pages['ページタイトル'].to_string(index=False) if not df_pages.empty else "データなし"
                summary_text = f"""
                # 主要指標: 訪問ユーザー数 {int(current_metrics[0])}, 成果数 {int(current_metrics[2])}, 平均滞在時間 {format_duration(current_metrics[3])}
                # 流入経路 TOP5: {channel_str}
                # 人気ページ TOP5: {pages_str}
                """
                prompt = "..." # 省略: 前回と同じ長いプロンプト
                genai.configure(api_key=GEMINI_API_KEY)
                model = genai.GenerativeModel('gemini-1.5-flash')
                report = model.generate_content(prompt).text
            
            st.header("3. AIによる分析と提案")
            st.markdown(report)

except Exception as e:
    st.error(f"エラーが発生しました: {e}")
    st.info("解決しない場合は、左のメニューから設定ページに移動し、サイト情報が正しく登録されているか確認してください。")