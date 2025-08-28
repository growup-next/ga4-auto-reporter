import streamlit as st
import pandas as pd
import gspread
from google.auth import default

st.set_page_config(page_title="設定", page_icon="⚙️", layout="wide")

st.title("⚙️ 設定ページ")
st.write("ここで分析対象のWebサイト情報を登録・管理します。")

# Googleスプレッドシートへの接続（キャッシュで高速化）
@st.cache_resource
def get_gsheet():
    creds, _ = default()
    gc = gspread.authorize(creds)
    # SecretsからスプレッドシートのURLを読み込む
    sheet_url = st.secrets["GOOGLE_SHEET_URL"]
    return gc.open_by_url(sheet_url).sheet1

try:
    sheet = get_gsheet()

    # --- 現在の登録サイト一覧を表示 ---
    st.header("登録済みサイト一覧")
    sites = pd.DataFrame(sheet.get_all_records())
    if sites.empty:
        st.info("まだサイトが登録されていません。")
    else:
        st.dataframe(sites, use_container_width=True)

    st.markdown("---")

    # --- 新しいサイトを登録 ---
    st.header("新しいサイトを登録")
    with st.form("add_site_form", clear_on_submit=True):
        new_site_name = st.text_input("サイト名（例：自社コーポレートサイト）", key="new_name")
        new_property_id = st.text_input("GA4プロパティID（例：123456789）", key="new_id")
        submitted_add = st.form_submit_button("登録する")

        if submitted_add:
            if new_site_name and new_property_id:
                # 最終行に追記
                sheet.append_row([new_site_name, new_property_id])
                st.success(f"「{new_site_name}」を登録しました。")
                st.rerun()
            else:
                st.warning("サイト名とプロパティIDの両方を入力してください。")

    # --- 登録済みサイトを削除 ---
    if not sites.empty:
        st.markdown("---")
        st.header("登録済みサイトを削除")
        
        site_to_delete = st.selectbox(
            "削除したいサイトを選択してください",
            options=[""] + sites['SiteName'].tolist(),
            index=0
        )
        
        if st.button("削除を実行する", type="primary"):
            if site_to_delete:
                # 該当するサイト名の行を探して削除
                cell = sheet.find(site_to_delete)
                if cell:
                    sheet.delete_rows(cell.row)
                    st.success(f"「{site_to_delete}」を削除しました。")
                    st.rerun()
                else:
                    st.error("サイトが見つかりませんでした。")
            else:
                st.warning("削除したいサイトを選択してください。")

except Exception as e:
    st.error(f"エラーが発生しました: {e}")
    st.error("GoogleスプレッドシートのURLが正しいか、共有設定が「編集者」になっているか確認してください。")