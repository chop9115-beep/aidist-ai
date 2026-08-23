import streamlit as st
import json
import os
import pandas as pd
import io
from dotenv import load_dotenv
from google import genai
from google.genai import types

# ---------------------------------------------------------
# 1. 基本設定 ＆ APIキー読み込み
# ---------------------------------------------------------
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MASTER_FILE_PATH = "welfare_master_data.json"

st.set_page_config(page_title="Aidist AI - 福祉用具選定", page_icon="🦼", layout="wide")

st.markdown(
    """
    <style>
        html, body, [class*="css"] { font-size: 13.5px; }
        header[data-testid="stHeader"] { display: none !important; }
        .block-container { padding: 15px 2rem 150px 2rem !important; }
        .sub-check-box { margin-top: -10px; margin-bottom: 15px; padding-left: 15px; border-left: 3px solid #cbd5e1; }
        .slide-catchphrase { font-size: 1.8rem; font-weight: 800; color: #1E40AF; text-align: center; margin-bottom: 1rem; }
        .slide-benefit { font-size: 1.3rem; font-weight: 700; color: #334155; margin-bottom: 0.8rem; padding: 15px; background-color: #F8FAFC; border-left: 6px solid #3B82F6; border-radius: 4px; }
        .slide-note { font-size: 1.1rem; color: #991B1B; background-color: #FEF2F2; padding: 15px; border-radius: 4px; margin-top: 20px; font-weight: 600; }
        .slide-price { font-size: 1.2rem; font-weight: 700; color: #047857; text-align: right; margin-top: 10px;}
    </style>
    """,
    unsafe_allow_html=True
)

# ---------------------------------------------------------
# 2. データ保存・読み込み関数
# ---------------------------------------------------------
def save_master_data():
    with open(MASTER_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump({"master": st.session_state.master_data}, f, ensure_ascii=False, indent=2)

def load_master_data():
    if os.path.exists(MASTER_FILE_PATH):
        try:
            with open(MASTER_FILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f).get("master", [])
        except Exception:
            pass
    return []

if "master_data" not in st.session_state:
    st.session_state.master_data = load_master_data()
if "proposals_data" not in st.session_state: st.session_state.proposals_data = None
if "meeting_summary" not in st.session_state: st.session_state.meeting_summary = ""
if "temp_edited_data" not in st.session_state: st.session_state.temp_edited_data = []

# ---------------------------------------------------------
# 3. 削除用ポップアップ（ダイアログ）
# ---------------------------------------------------------
@st.dialog("⚠️ 選択削除の確認")
def confirm_delete_selected():
    st.warning("「delete_flag」にチェックを入れた項目を削除します。よろしいですか？")
    if st.button("はい、削除します", type="primary"):
        st.session_state.master_data = [row for row in st.session_state.temp_edited_data if not row.get("delete_flag", False)]
        save_master_data()
        st.success("削除しました！")
        st.rerun()

@st.dialog("🚨 一括削除の確認")
def confirm_delete_all():
    st.error("全てのマスタデータを完全に削除します。本当によろしいですか？")
    if st.button("はい、全て削除します", type="primary"):
        st.session_state.master_data = []
        save_master_data()
        st.success("全てのデータを削除しました！")
        st.rerun()

@st.dialog("✨ ご利用者向け 提案スライド", width="large")
def show_presentation_slide(item):
    st.markdown(f"<div class='slide-catchphrase'>{item.get('catchphrase', '安心・安全な生活をサポートします')}</div>", unsafe_allow_html=True)
    st.markdown(f"**■ {item.get('name','')}** （{item.get('maker','')}） / 型式: {item.get('model','')}")
    for i in range(1, 4):
        if item.get(f'benefit_{i}'): st.markdown(f"<div class='slide-benefit'>💡 {item[f'benefit_{i}']}</div>", unsafe_allow_html=True)
    if item.get('safety_note'): st.markdown(f"<div class='slide-note'>{item['safety_note']}</div>", unsafe_allow_html=True)
    if item.get('rental_price'): st.markdown(f"<div class='slide-price'>目安ご利用料金： {item['rental_price']}</div>", unsafe_allow_html=True)

# ---------------------------------------------------------
# 4. サイドバー（画面切り替えメニュー）
# ---------------------------------------------------------
with st.sidebar:
    st.markdown("### 🦼 メニュー")
    page_mode = st.radio("表示する画面を選択", ["📝 アセスメント ＆ AI提案", "⚙️ ナレッジ・マスタ管理"])
    st.markdown("---")
    st.info("👤 アカウント: 管理者 (1/5)")

# =========================================================
# 画面A：ナレッジ・マスタ管理（フルスクリーン表示）
# =========================================================
if page_mode == "⚙️ ナレッジ・マスタ管理":
    st.markdown("## ⚙️ ナレッジ・マスタ管理")
    st.markdown("CSVの取り込みや、マスタデータの一覧編集をこの画面で広く行えます。")
    st.markdown("---")

    st.markdown("#### 📊 1. CSVインポート（マッピング）")
    
    col_csv, col_opt = st.columns([2, 1])
    with col_csv:
        uploaded_csv = st.file_uploader("基幹システムのCSVファイルを選択", type=["csv"])
    with col_opt:
        header_row = st.number_input("列名（ヘッダー）がある行番号", min_value=1, value=1, help="もし1行目がファイル名などになっている場合は「2」や「3」に変更してください。")

    if uploaded_csv:
        try:
            # 文字コードを安全に読み込む処理
            bytes_data = uploaded_csv.getvalue()
            try:
                csv_text = bytes_data.decode('utf-8')
            except UnicodeDecodeError:
                try:
                    csv_text = bytes_data.decode('shift_jis')
                except UnicodeDecodeError:
                    csv_text = bytes_data.decode('cp932')

            # 指定された行番号をヘッダーとしてDataFrameに変換
            df = pd.read_csv(io.StringIO(csv_text), header=header_row - 1)
            
            st.write("▼ 読み込んだCSVのプレビュー (最初の3行)")
            st.dataframe(df.head(3), use_container_width=True)
            
            cols = ["(未割り当て)"] + [str(c) for c in df.columns.tolist()]
            
            st.markdown("**列の紐付け（マッピング）**")
            c1, c2, c3, c4, c5, c6 = st.columns(6)
            map_tais = c1.selectbox("TAISコード", cols, index=0)
            map_category = c2.selectbox("種目", cols, index=0)
            map_name = c3.selectbox("商品名", cols, index=0)
            map_maker = c4.selectbox("メーカー", cols, index=0)
            map_model = c5.selectbox("型式", cols, index=0)
            map_price = c6.selectbox("レンタル価格", cols, index=0)
            
            if st.button("マッピングしてシステムに登録", type="primary"):
                new_items = []
                for _, row in df.iterrows():
                    new_items.append({
                        "tais_code": str(row[map_tais]) if map_tais != "(未割り当て)" else "",
                        "category": str(row[map_category]) if map_category != "(未割り当て)" else "【貸与】未分類",
                        "name": str(row[map_name]) if map_name != "(未割り当て)" else "",
                        "maker": str(row[map_maker]) if map_maker != "(未割り当て)" else "",
                        "model": str(row[map_model]) if map_model != "(未割り当て)" else "",
                        "rental_price": str(row[map_price]) if map_price != "(未割り当て)" else "",
                        "is_active": True, "memo": "", "delete_flag": False
                    })
                st.session_state.master_data.extend(new_items)
                save_master_data()
                st.success(f"{len(new_items)}件をマスタに登録しました！")
        except Exception as e:
            st.error(f"CSV読み込みエラー: {e} （行番号の指定などが間違っていないかご確認ください）")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### ✏️ 2. マスタデータの一覧編集 ＆ 削除")
    if st.session_state.master_data:
        df_master = pd.DataFrame(st.session_state.master_data)
        if "delete_flag" not in df_master.columns: df_master["delete_flag"] = False
        
        st.info("直接セルをクリックして文字を編集できます。削除したい場合は右端の「delete_flag」にチェックを入れてください。")
        edited_df = st.data_editor(df_master, num_rows="dynamic", use_container_width=True, hide_index=True, height=400)
        
        c_save, c_del, c_delall, _ = st.columns([2, 2, 2, 4])
        with c_save:
            if st.button("💾 編集を保存", use_container_width=True):
                st.session_state.master_data = edited_df.to_dict(orient="records")
                save_master_data()
                st.success("保存しました！")
        with c_del:
            if st.button("🗑️ 選択削除", use_container_width=True):
                st.session_state.temp_edited_data = edited_df.to_dict(orient="records")
                confirm_delete_selected()
        with c_delall:
            if st.button("🚨 一括削除", use_container_width=True):
                confirm_delete_all()
    else:
        st.warning("現在登録されているマスタデータはありません。")

# =========================================================
# 画面B：アセスメント ＆ AI提案（メイン画面）
# =========================================================
elif page_mode == "📝 アセスメント ＆ AI提案":
    st.markdown("## 🦼 Aidist AI - 福祉用具選定アシスト")
    st.markdown("---")

    with st.expander("📝 対象者アセスメント・利用環境の入力", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            care_level = st.selectbox("要介護度", ["要支援1", "要支援2", "要介護1", "要介護2", "要介護3", "要介護4", "要介護5"], index=3)
            user_status = st.text_area("身体状況・主訴・ADL", value="80代女性。圧迫骨折後で腰部痛あり。歩行意欲はあるが転倒不安が強い。", height=80)
            env_status = st.text_area("住環境・介助体制", value="マンション。主な介助者は80代の夫で負担軽減が必要。", height=50)

        with c2:
            st.markdown("**📦 複合パッケージ（選定種目）の指定**")
            main_categories = st.multiselect("基本の福祉用具", ["特殊寝台（ベッド）", "車いす", "手すり", "未分類"], default=["特殊寝台（ベッド）"])
            
            selected_cats = []
            if "特殊寝台（ベッド）" in main_categories:
                selected_cats.append("【貸与】特殊寝台本体")
                st.markdown("<div class='sub-check-box'>", unsafe_allow_html=True)
                if st.checkbox("＋ マットレス", value=True): selected_cats.append("【貸与】特殊寝台付属品（マットレス）")
                st.markdown("</div>", unsafe_allow_html=True)
            if "車いす" in main_categories: selected_cats.append("【貸与】車いす本体")
            if "手すり" in main_categories: selected_cats.append("【貸与】手すり")
            if "未分類" in main_categories: selected_cats.append("【貸与】未分類")

    generate_btn = st.button("🔍 実情に寄り添うパッケージ提案を生成", type="primary", use_container_width=True)

    def call_gemini(prompt: str, is_json: bool = False) -> str:
        if not GEMINI_API_KEY: raise ValueError("APIキーが設定されていません。")
        client = genai.Client(api_key=GEMINI_API_KEY)
        config = types.GenerateContentConfig(response_mime_type="application/json" if is_json else "text/plain", temperature=0.2)
        response = client.models.generate_content(model="gemini-3.6-flash", contents=prompt, config=config)
        return response.text.strip()

    if generate_btn:
        with st.spinner("AIが最適な複合パッケージを構築中..."):
            try:
                active_items = [item for item in st.session_state.master_data if item.get("is_active", True) and item.get("category") in selected_cats]
                master_text = "【利用可能な自社登録マスタ】\n"
                for item in active_items:
                    master_text += f"- TAIS:{item.get('tais_code','')} | 品名:{item.get('name','')} | 種目:{item.get('category','')} | 型式:{item.get('model','')}\n"

                system_prompt = f"""
あなたは福祉用具専門相談員のアシスタントAIです。以下の【マスタ】から指定された【複数種目の用具】を組み合わせたパッケージを2軸で提案してください。
【マスタ】{master_text}
【対象者情報】状況: {user_status} / 環境: {env_status}
【厳守JSONフォーマット】
{{
  "proposals": [
    {{
      "axis_title": "① 【自立支援 特化セット】", "tool_name": "提案する用具一式",
      "tais_codes": ["00789-000001"], "axis_description": "選定の狙い",
      "talk_script": "スタッフへの提案ヒント（箇条書き）", "plan_target": "計画書の目標", "plan_reason": "選定理由"
    }},
    {{ "axis_title": "② 【介助軽減 特化セット】", "tool_name": "...", "tais_codes": [], "axis_description": "...", "talk_script": "...", "plan_target": "...", "plan_reason": "..." }}
  ], "meeting_summary": "アセスメントの要約"
}}
"""
                result_data = json.loads(call_gemini(system_prompt, is_json=True))
                st.session_state.proposals_data = result_data
                st.session_state.meeting_summary = result_data.get("meeting_summary", "")
                st.rerun()
            except Exception as e:
                st.error(f"提案生成中にエラーが発生しました: {e}")

    if st.session_state.proposals_data:
        data = st.session_state.proposals_data
        st.markdown("---")
        tabs = st.tabs([p["axis_title"] for p in data["proposals"]])

        for i, tab in enumerate(tabs):
            p = data["proposals"][i]
            with tab:
                col_main, col_slide = st.columns([3, 1.5])
                with col_main:
                    st.markdown(f"**提案パッケージ:** `{p['tool_name']}`")
                    st.markdown(f"**選定の狙い:** {p['axis_description']}")
                    st.info(p["talk_script"])
                    
                with col_slide:
                    st.markdown("**📺 ご利用者向けスライド（可視化）**")
                    tais_list = p.get("tais_codes", [])
                    found_items = [item for item in st.session_state.master_data if item.get("tais_code") in tais_list]
                    
                    if found_items:
                        for item in found_items:
                            if st.button(f"📱 {item.get('name','')} の図解", key=f"slide_btn_{i}_{item.get('tais_code','x')}", use_container_width=True):
                                show_presentation_slide(item)
                    else:
                        st.caption("※該当商品のスライドデータがありません")
                
                st.code(f"【利用目標】\n{p['plan_target']}\n\n【選定理由】\n{p['plan_reason']}", language="text")

        st.markdown("---")
        with st.container(border=True):
            if st.session_state.meeting_summary:
                st.code(st.session_state.meeting_summary, language="text")
            st.text_area("提案後のメモ", placeholder="例：ご本人様より「転倒が不安」との声があり、①で合意。", height=80, label_visibility="collapsed")
