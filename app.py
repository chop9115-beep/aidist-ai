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

# マッチング精度を高めるための文字正規化ツール
def normalize_str(s):
    if not s: return ""
    return str(s).replace("-", "").replace(" ", "").replace(" ", "").upper()

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
    st.markdown("---")

    # --- 1. CSVインポート ---
    with st.expander("📊 1. CSVインポート（基本データの登録）", expanded=False):
        col_csv, col_opt = st.columns([2, 1])
        with col_csv:
            uploaded_csv = st.file_uploader("基幹システムのCSVファイルを選択", type=["csv"])
        with col_opt:
            header_row = st.number_input("列名（ヘッダー）がある行番号", min_value=1, value=1)

        if uploaded_csv:
            try:
                bytes_data = uploaded_csv.getvalue()
                try: csv_text = bytes_data.decode('utf-8')
                except UnicodeDecodeError:
                    try: csv_text = bytes_data.decode('shift_jis')
                    except UnicodeDecodeError: csv_text = bytes_data.decode('cp932')

                df = pd.read_csv(io.StringIO(csv_text), header=header_row - 1)
                st.write("▼ プレビュー (最初の3行)")
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
                st.error(f"CSV読み込みエラー: {e}")

    # --- 2. PDF一括ナレッジ結合（NEW） ---
    with st.expander("📚 2. カタログPDFからナレッジ一括自動生成（紐付け）", expanded=True):
        st.markdown("対象のメーカーを選択し、PDFファイルを一括でアップロードすると、AIが型式を照合してスライド要素を自動結合します。")
        
        # マスタからメーカーとTAISのプレフィックスを抽出して選択肢を作成
        maker_options = ["(選択してください)"]
        maker_dict = {}
        for item in st.session_state.master_data:
            maker = item.get("maker", "").strip()
            tais = item.get("tais_code", "").strip()
            if maker and tais:
                prefix = tais.split("-")[0] if "-" in tais else tais[:5]
                opt_label = f"{maker} (TAIS: {prefix})"
                if opt_label not in maker_options:
                    maker_options.append(opt_label)
                    maker_dict[opt_label] = maker

        selected_maker_label = st.selectbox("🎯 対象のメーカーを選択", maker_options)
        
        if selected_maker_label != "(選択してください)":
            target_maker_name = maker_dict[selected_maker_label]
            uploaded_pdfs = st.file_uploader("カタログPDFを選択（複数ファイルをドロップ可）", type=["pdf"], accept_multiple_files=True)
            
            if uploaded_pdfs and st.button("🚀 AI解析 ＆ マスタ自動結合スタート", type="primary"):
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                client = genai.Client(api_key=GEMINI_API_KEY)
                pdf_prompt = """以下の福祉用具PDFカタログから情報を抽出し、JSONで出力してください。
【抽出項目】"model" (型式：英数字など), "name" (商品名)
【スライド要素】
- "catchphrase": 利用者が直感的にメリットを感じる一言（20文字以内）
- "benefit_1"〜"benefit_3": 視覚的・機能的メリット（各30文字以内）
- "safety_note": 現場で伝えるべき注意事項
【フォーマット】 {"model":"", "name":"", "catchphrase":"", "benefit_1":"", "benefit_2":"", "benefit_3":"", "safety_note":""}"""

                for i, pdf_file in enumerate(uploaded_pdfs):
                    status_text.text(f"解析中... ({i+1}/{len(uploaded_pdfs)}) : {pdf_file.name}")
                    try:
                        pdf_part = types.Part.from_bytes(data=pdf_file.getvalue(), mime_type="application/pdf")
                        config = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
                        response = client.models.generate_content(model="gemini-3.6-flash", contents=[pdf_part, pdf_prompt], config=config)
                        
                        clean_json = response.text.strip().replace("```json", "").replace("```", "")
                        result = json.loads(clean_json)
                        
                        extracted_model = normalize_str(result.get("model", ""))
                        extracted_name = normalize_str(result.get("name", ""))
                        
                        # 自動マッチング（型式 または 商品名 で検索）
                        match_found = False
                        for item in st.session_state.master_data:
                            if item.get("maker") == target_maker_name:
                                master_model = normalize_str(item.get("model", ""))
                                master_name = normalize_str(item.get("name", ""))
                                
                                # 型式が一致、または商品名が部分一致すれば紐付け
                                if (extracted_model and extracted_model in master_model) or \
                                   (extracted_name and extracted_name in master_name):
                                    item["catchphrase"] = result.get("catchphrase", "")
                                    item["benefit_1"] = result.get("benefit_1", "")
                                    item["benefit_2"] = result.get("benefit_2", "")
                                    item["benefit_3"] = result.get("benefit_3", "")
                                    item["safety_note"] = result.get("safety_note", "")
                                    match_found = True
                                    st.success(f"✅ 結合成功: {pdf_file.name} ➔ マスタ: {item.get('name')}")
                                    break
                        
                        if not match_found:
                            st.warning(f"⚠️ マッチ対象なし: {pdf_file.name} (抽出型式: {result.get('model')})")

                    except Exception as e:
                        st.error(f"❌ 解析エラー ({pdf_file.name}): {e}")
                    
                    progress_bar.progress((i + 1) / len(uploaded_pdfs))
                
                save_master_data()
                status_text.text("🎉 すべての処理が完了しました！")

    # --- 3. マスタ編集 ---
    st.markdown("#### ✏️ 3. マスタデータの一覧編集 ＆ 削除")
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
            # マスタに存在するカテゴリを動的に取得して選択肢にする
            available_categories = sorted(list(set([item.get("category", "") for item in st.session_state.master_data if item.get("category")])))
            selected_cats = st.multiselect("マスタから選定する種目を選択", available_categories, default=available_categories[:1] if available_categories else None)

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
あなたは福祉用具専門相談員のアシスタントAIです。
以下の【マスタ】の中に存在する商品のみを使って、指定された【複数種目の用具】を組み合わせたパッケージを2軸で提案してください。
※提案する商品の TAISコード は、必ず【マスタ】にあるものを正確に出力してください。

【マスタ】{master_text}
【対象者情報】状況: {user_status} / 環境: {env_status}

【厳守JSONフォーマット】
{{
  "proposals": [
    {{
      "axis_title": "① 【自立支援 特化セット】", "tool_name": "提案する具体的な商品名（複数可）",
      "tais_codes": ["マスタに存在するTAISコード1", "TAISコード2"], "axis_description": "選定の狙い",
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
