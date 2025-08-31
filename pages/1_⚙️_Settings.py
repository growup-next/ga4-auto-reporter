import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from gspread_dataframe import get_as_dataframe, set_with_dataframe

st.set_page_config(page_title="設定", page_icon="⚙️", layout="wide")

# --- 認証情報 (サービスアカウント) ---
@st.cache_resource
def authorize_gcp():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
        return creds
    except Exception as e:
        st.error(f"GCPサービスアカウントの認証情報（Secrets）に問題があります: {e}")
        st.stop()

credentials = authorize_gcp()
GOOGLE_SHEET_URL = st.secrets["GOOGLE_SHEET_URL"]

# --- UI ---
st.title("⚙️ 設定ページ")
st.write("ここで分析対象のWebサイト情報を登録・管理します。")

# --- メインロジック ---
try:
    @st.cache_resource
    def get_gsheet_client():
        return gspread.authorize(credentials)
    
    gsheet_client = get_gsheet_client()
    sheet = gsheet_client.open_by_url(GOOGLE_SHEET_URL).sheet1

    st.header("登録済みサイト一覧")
    sites_df = get_as_dataframe(sheet).dropna(how='all')
    st.dataframe(sites_df, use_container_width=True)

    st.markdown("---")
    st.header("新しいサイトを登録")
    with st.form("add_site_form", clear_on_submit=True):
        new_site_name = st.text_input("サイト名")
        new_property_id = st.text_input("GA4プロパティID")
        submitted_add = st.form_submit_button("このサイトを登録する")

        if submitted_add:
            if new_site_name and new_property_id:
                sheet.append_row([new_site_name, str(new_property_id)])
                st.success(f"「{new_site_name}」を登録しました。")
                st.cache_data.clear()
                st.rerun()
            else:
                st.warning("サイト名とプロパティIDの両方を入力してください。")

    if not sites_df.empty:
        st.markdown("---")
        st.header("登録済みサイトを削除")
        site_to_delete = st.selectbox("削除したいサイトを選択してください", options=[""] + sites_df['SiteName'].tolist())
        
        if st.button("このサイトを削除する", type="primary"):
            if site_to_delete:
                cell = sheet.find(site_to_delete)
                if cell:
                    sheet.delete_rows(cell.row)
                    st.success(f"「{site_to_delete}」を削除しました。")
                    st.cache_data.clear()
                    st.rerun()
            else:
                st.warning("削除するサイトを選択してください。")

except Exception as e:
    st.error(f"エラーが発生しました: {e}")