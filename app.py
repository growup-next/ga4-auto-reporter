import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe
import plotly.express as px
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import RunReportRequest, Dimension, Metric, DateRange, OrderBy
import google.generativeai as genai
from datetime import datetime
from dateutil.relativedelta import relativedelta
import math

# --- アプリの基本設定 ---
st.set_page_config(page_title="経営層向け GA4分析ダッシュボード", page_icon="🚀", layout="wide")

# --- Googleサービスへの認証 ---
@st.cache_resource
def authorize_gcp():
    """StreamlitのSecretsを使い、サービスアカウントとしてGoogleの各サービスを認証する"""
    try:
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/analytics.readonly"
        ]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        return creds
    except Exception as e:
        st.error(f"GCPサービスアカウントの認証情報（Secrets）に問題があります: {e}")
        st.stop()

credentials = authorize_gcp()
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
GOOGLE_SHEET_URL = st.secrets["GOOGLE_SHEET_URL"]

# --- UI表示 ---
st.title("🚀 経営層向け GA4分析ダッシュボード")
st.write("サイトの現状をひと目で把握し、データに基づいた「次の一手」を提案します。")

# --- ヘルパー関数 ---
@st.cache_resource
def get_ga_client():
    """GA4のクライアントを初期化"""
    return BetaAnalyticsDataClient(credentials=credentials)

@st.cache_resource
def get_gsheet_client():
    """Googleスプレッドシートのクライアントを初期化"""
    return gspread.authorize(credentials)

@st.cache_data(ttl=600) # 10分間キャッシュ
def get_sites_data(_gsheet_client):
    """スプレッドシートからサイト一覧を取得"""
    try:
        sheet = _gsheet_client.open_by_url(GOOGLE_SHEET_URL).sheet1
        df = get_as_dataframe(sheet, evaluate_formulas=True).dropna(how='all')
        return df
    except Exception as e:
        st.error(f"Googleスプレッドシートの読み込みに失敗しました: {e}")
        return pd.DataFrame()

def run_ga4_report(client, property_id, dimensions, metrics, date_ranges, order_bys=None):
    """GA4にレポートリクエストを送信する汎用関数"""
    request = RunReportRequest(property=f"properties/{property_id}", dimensions=dimensions, metrics=metrics, date_ranges=date_ranges, order_bys=order_bys)
    return client.run_report(request)

def format_duration(seconds):
    """秒数を「X分Y秒」の形式に変換"""
    if seconds == 0: return "0秒"
    minutes = math.floor(seconds / 60)
    remaining_seconds = round(seconds % 60)
    return f"{minutes}分{remaining_seconds}秒"

# --- メインロジック ---
try:
    gsheet_client = get_gsheet_client()
    sites = get_sites_data(gsheet_client)

    if sites.empty:
        st.warning("分析対象のサイトが登録されていません。左のメニューから「⚙️ Settings」ページに移動して、サイトを登録してください。")
    else:
        site_options = sites['SiteName'].tolist()
        selected_site_name = st.selectbox("分析したいサイトを選択してください", site_options)
        
        if selected_site_name:
            property_id_from_sheet = sites[sites['SiteName'] == selected_site_name]['PropertyID'].iloc[0]
            selected_property_id = str(int(property_id_from_sheet))

            goal_options = [
                "サイト経由の売上を増やす",
                "問い合わせや見込み客の件数を増やす",
                "ブランドの認知度を向上させる",
                "リピーターを増やし、顧客との関係を深める"
            ]

            business_goal = st.selectbox(
                "このサイトの最も重要なビジネス目標を選択してください",
                goal_options
            )
            
            if st.button("📈 最新ダッシュボードを生成する"):
                ga_client = get_ga_client()
                today = datetime.now()
                last_30_days_start = (today - relativedelta(days=29)).strftime('%Y-%m-%d')
                prev_30_days_start = (today - relativedelta(days=59)).strftime('%Y-%m-%d')
                prev_30_days_end = (today - relativedelta(days=30)).strftime('%Y-%m-%d')
                date_range_current = DateRange(start_date=last_30_days_start, end_date="today")
                date_range_previous = DateRange(start_date=prev_30_days_start, end_date=prev_30_days_end)

                with st.spinner("各種データをGA4から取得中..."):
                    # 主要指標
                    response_kpi = run_ga4_report(client=ga_client, property_id=selected_property_id, dimensions=[], metrics=[Metric(name="activeUsers"), Metric(name="sessions"), Metric(name="conversions"), Metric(name="averageSessionDuration")], date_ranges=[date_range_current, date_range_previous])
                    current_metrics = [float(v.value) for v in response_kpi.rows[0].metric_values] if response_kpi.rows else [0, 0, 0, 0]
                    prev_metrics = [float(v.value) for v in response_kpi.rows[1].metric_values] if len(response_kpi.rows) > 1 else [0, 0, 0, 0]
                    # 詳細データ
                    response_details = run_ga4_report(client=ga_client, property_id=selected_property_id, dimensions=[Dimension(name="sessionDefaultChannelGroup"), Dimension(name="deviceCategory"), Dimension(name="userAgeBracket")], metrics=[Metric(name="activeUsers")], date_ranges=[date_range_current])
                    details_data = [{"チャネル": row.dimension_values[0].value, "デバイス": row.dimension_values[1].value, "年齢層": row.dimension_values[2].value, "ユーザー数": int(row.metric_values[0].value)} for row in response_details.rows]
                    df_details = pd.DataFrame(details_data)
                    # 人気ページ
                    response_pages = run_ga4_report(client=ga_client, property_id=selected_property_id, dimensions=[Dimension(name="pageTitle")], metrics=[Metric(name="screenPageViews")], date_ranges=[date_range_current], order_bys=[OrderBy(metric={'metric_name': 'screenPageViews'}, desc=True)])
                    page_data = [{"ページタイトル": row.dimension_values[0].value, "表示回数": int(row.metric_values[0].value)} for row in response_pages.rows]
                    df_pages = pd.DataFrame(page_data).head(5)

                st.header("1. サイトの健康状態")
                kpi_cols = st.columns(4)
                kpi_cols[0].metric("訪問ユーザー数", f"{int(current_metrics[0]):,}", f"{int(current_metrics[0] - prev_metrics[0]):,}")
                kpi_cols[1].metric("サイト訪問回数", f"{int(current_metrics[1]):,}", f"{int(current_metrics[1] - prev_metrics[1]):,}")
                kpi_cols[2].metric("平均サイト滞在時間", format_duration(current_metrics[3]), f"{format_duration(current_metrics[3] - prev_metrics[3])}")
                kpi_cols[3].metric("成果（CV）数", f"{int(current_metrics[2]):,}", f"{int(current_metrics[2] - prev_metrics[2]):,}")
                
                st.header("2. 顧客インサイト")
                viz_cols = st.columns(4)
                if not df_details.empty:
                    df_channel = df_details.groupby("チャネル")["ユーザー数"].sum().nlargest(5); viz_cols[0].bar_chart(df_channel, use_container_width=True)
                    df_age = df_details.groupby("年齢層")["ユーザー数"].sum().sort_index(); viz_cols[2].bar_chart(df_age, use_container_width=True)
                    df_device = df_details.groupby("デバイス")["ユーザー数"].sum(); viz_cols[3].bar_chart(df_device, use_container_width=True)
                else:
                    viz_cols[0].write("チャネル データなし"); viz_cols[2].write("年齢層 データなし"); viz_cols[3].write("デバイス データなし")
                
                if not df_pages.empty:
                    df_pages_chart = df_pages.set_index("ページタイトル")["表示回数"]; viz_cols[1].bar_chart(df_pages_chart, use_container_width=True)
                else:
                    viz_cols[1].write("人気ページ データなし")

                with st.spinner("AIが「次の一手」を分析・提案中..."):
                    channel_str = df_channel.to_string() if 'df_channel' in locals() and not df_channel.empty else "データなし"
                    pages_str = df_pages['ページタイトル'].to_string(index=False) if not df_pages.empty else "データなし"
                    summary_text = f"""# 主要指標: 訪問ユーザー数 {int(current_metrics[0])}, 成果数 {int(current_metrics[2])}, 平均滞在時間 {format_duration(current_metrics[3])}\n# 流入経路 TOP5: {channel_str}\n# 人気ページ TOP5: {pages_str}"""
                    prompt = f"""あなたは、企業の成長を支援する腕利きの経営コンサルタントです。以下のWebサイトのデータとビジネス目標を分析し、経営者に向けて「次に取るべき最も重要な一手」を提案してください。\n# ビジネス目標\n{business_goal}\n# 分析対象データ\n{summary_text}\n# 指示\nデータから最大の課題またはチャンスを1つだけ特定し、それに対する具体的なアクションを提案してください。提案は以下のフォーマットで、専門用語を使わずに記述してください。\n---\n### 📊 現状のサマリー\n（データ全体からわかるサイトの健康状態を2行で要約）\n\n### 💡 最も重要な「次の一手」\n**アクション：** （明日からでも始められる、具体的で現実的なアクションを1つだけ提案）\n\n**理由：** （なぜ、今このアクションが最も重要なのかを、データに基づいて解説）\n\n**期待される成果：** （このアクションを実行することで、ビジネス目標達成にどう繋がるかの予測）\n---"""
                    
                    genai.configure(api_key=GEMINI_API_KEY)
                    model = genai.GenerativeModel('gemini-1.5-flash')
                    report = model.generate_content(prompt).text
                
                st.header("3. AIによる分析と提案")
                st.markdown(report)

except Exception as e:
    st.error(f"アプリの処理中にエラーが発生しました: {e}")