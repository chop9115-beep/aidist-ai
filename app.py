import streamlit as st
import json
import os
import pandas as pd
import io
import time
import concurrent.futures
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.cloud import documentai
from google.oauth2 import service_account

# ---------------------------------------------------------
# 1. 基本設定 ＆ APIキー/認証読み込み
# ---------------------------------------------------------
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MASTER_FILE_PATH = "welfare_master_data.json"

# Document AI の設定情報
DOCAI_PROCESSOR_ID = "bc9848f52b942b34"
DOCAI_LOCATION = "us"

st.set_page_config(page_title="Aidist AI - 福祉用具選定", page_icon="🦼", layout="wide")

st.markdown(
    """
    <style>
        html, body, [class*="css"] { font-size: 13.5px; }
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
# 2. データ保存・読み込み・補助関数
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

def normalize_str(s):
    if not s: return ""
    return str(s).replace("-", "").replace(" ", "").replace(" ", "").upper()

def get_tais_maker_prefix(tais_code):
    tais_str = str(tais_code).strip()
    if not tais_str or tais_str == "nan": return ""
    prefix = tais_str.split("-")[0] if "-" in tais_str else tais_str[:5]
    prefix = ''.join(filter(str.isdigit, prefix))[:5]
    return prefix.zfill(5) if prefix else ""

# =========================================================
# Google Cloud 認証 ＆ Document AI 処理関数
# =========================================================
def get_gcp_credentials():
    if "GCP_KEY_JSON" in st.secrets:
        key_dict = json.loads(st.secrets["GCP_KEY_JSON"])
        return service_account.Credentials.from_service_account_info(key_dict)
    elif "gcp_service_account" in st.secrets:
        return service_account.Credentials.from_service_account_info(st.secrets["gcp_service_account"])
    elif os.getenv("GOOGLE_APPLICATION_CREDENTIALS"):
        return service_account.Credentials.from_service_account_file(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
    else:
        raise ValueError("Google Cloud 認証情報が設定されていません。")

def process_document_ocr(file_bytes):
    creds = get_gcp_credentials()
    project_id = creds.project_id
    
    opts = {"api_endpoint": f"{DOCAI_LOCATION}-documentai.googleapis.com"}
    client = documentai.DocumentProcessorServiceClient(credentials=creds, client_options=opts)
    
    name = client.processor_path(project_id, DOCAI_LOCATION, DOCAI_PROCESSOR_ID)
    raw_document = documentai.RawDocument(content=file_bytes, mime_type="application/pdf")
    request = documentai.ProcessRequest(name=name, raw_document=raw_document)
    
    result = client.process_document(request=request)
    return result.document.text

# ---------------------------------------------------------
# 3. ダイアログ（ポップアップ）
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
# 4. サイドバー
# ---------------------------------------------------------
with st.sidebar:
    st.markdown("### 🦼 メニュー")
    page_mode = st.radio("表示する画面を選択", ["📝 アセスメント ＆ AI提案", "⚙️ ナレッジ・マスタ管理"])
    st.markdown("---")
    st.info("👤 アカウント: 管理者 (1/5)")

# =========================================================
# 画面A：ナレッジ・マスタ管理
# =========================================================
if page_mode == "⚙️ ナレッジ・マスタ管理":
    st.markdown("## ⚙️ ナレッジ・マスタ管理")
    st.markdown("---")

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
                df = df.fillna("")
                
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
                            "tais_code": str(row[map_tais]).strip() if map_tais != "(未割り当て)" else "",
                            "category": str(row[map_category]).strip() if map_category != "(未割り当て)" else "【貸与】未分類",
                            "name": str(row[map_name]).strip() if map_name != "(未割り当て)" else "",
                            "maker": str(row[map_maker]).strip() if map_maker != "(未割り当て)" else "",
                            "model": str(row[map_model]).strip() if map_model != "(未割り当て)" else "",
                            "rental_price": str(row[map_price]).strip() if map_price != "(未割り当て)" else "",
                            "is_active": True, "memo": "", "delete_flag": False
                        })
                    st.session_state.master_data.extend(new_items)
                    save_master_data()
                    st.success(f"{len(new_items)}件をマスタに登録しました！リストを更新します...")
                    time.sleep(1) 
                    st.rerun()    
            except Exception as e:
                st.error(f"CSV読み込みエラー: {e}")

    with st.expander("📚 2. ハイブリッドAI カタログ全自動結合（Document AI × Gemini）", expanded=True):
        st.markdown("専用OCRでテキストを完全抽出し、AIで漏れなくマスタへ結合します。")
        
        maker_options = ["(選択してください)"]
        maker_dict = {}
        for item in st.session_state.master_data:
            maker = item.get("maker", "").strip()
            prefix = get_tais_maker_prefix(item.get("tais_code", ""))
            if prefix:
                opt_label = f"{maker if maker else 'メーカー不明'} (TAIS: {prefix})"
                if opt_label not in maker_options:
                    maker_options.append(opt_label)
                    maker_dict[opt_label] = prefix 

        selected_maker_label = st.selectbox("🎯 対象のメーカー / TAISコード(5桁) を検索・選択", maker_options)
        
        if selected_maker_label != "(選択してください)":
            target_prefix = maker_dict[selected_maker_label]
            uploaded_pdfs = st.file_uploader("カタログPDFを選択（複数ファイルをドロップ可）", type=["pdf"], accept_multiple_files=True)
            
            if uploaded_pdfs and st.button("🚀 ハイブリッド解析スタート", type="primary"):
                progress_bar = st.progress(0)
                status_text = st.empty()
                results_summary = []
                client_ai = genai.Client(api_key=GEMINI_API_KEY)

                def analyze_pdf(pdf_bytes):
                    ocr_text = process_document_ocr(pdf_bytes)
                    
                    # ⚠️AIの出力ミスを防ぐための厳格なプロンプトに変更
                    prompt = f"""以下のOCR抽出テキスト（福祉用具カタログ）を隅々まで解析し、記載されている全ての商品を抽出してください。

【抽出項目】"model" (型式), "name" (商品名), "tais_code" (TAISコード:記載がある場合のみ)
【スライド要素】
- "catchphrase": 利用者が直感的にメリットを感じる一言（20文字以内）
- "benefit_1"〜"benefit_3": 視覚的・機能的メリット（各30文字以内）
- "safety_note": 現場で伝えるべき注意事項

【⚠️プログラミング上の絶対ルール（必ず守ること）⚠️】
1. 出力するテキストの中に「改行（\\n）」を絶対に入れないでください。
2. テキストの中に「"（ダブルクォーテーション）」を含めないでください。必要な場合は「'（シングルクォーテーション）」に置き換えてください。
3. 完璧なJSON配列として出力し、途中で途切れないようにしてください。

【フォーマット厳守】 [{{"model":"", "name":"", "tais_code":"", "catchphrase":"", "benefit_1":"", "benefit_2":"", "benefit_3":"", "safety_note":""}}]

--- OCR抽出テキスト ---
{ocr_text}
"""
                    config = types.GenerateContentConfig(
                        response_mime_type="application/json", 
                        temperature=0.0, # ブレをなくすため0.0に変更
                        max_output_tokens=8192
                    )
                    response = client_ai.models.generate_content(model="gemini-3.6-flash", contents=prompt, config=config)
                    clean_json = response.text.strip().replace("```json", "").replace("```", "")
                    
                    try:
                        return json.loads(clean_json)
                    except json.JSONDecodeError as e:
                        # 万が一AIがミスをした場合のエラーハンドリングを追加
                        raise ValueError(f"AIのデータ形式エラー。再実行してください。（詳細: {str(e)}）")

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    futures = {executor.submit(analyze_pdf, pdf_file.getvalue()): pdf_file for pdf_file in uploaded_pdfs}
                    
                    completed = 0
                    for future in concurrent.futures.as_completed(futures):
                        pdf_file = futures[future]
                        try:
                            result_list = future.result()
                            if isinstance(result_list, dict): result_list = [result_list]
                            
                            match_count = 0
                            for res in result_list:
                                extracted_model = normalize_str(res.get("model", ""))
                                extracted_name = normalize_str(res.get("name", ""))
                                extracted_tais = normalize_str(res.get("tais_code", ""))
                                
                                for item in st.session_state.master_data:
                                    item_prefix = get_tais_maker_prefix(item.get("tais_code", ""))
                                    if item_prefix == target_prefix:
                                        master_model = normalize_str(item.get("model", ""))
                                        master_name = normalize_str(item.get("name", ""))
                                        master_tais = normalize_str(item.get("tais_code", ""))
                                        
                                        is_match = False
                                        if extracted_tais and extracted_tais in master_tais: is_match = True
                                        elif extracted_model and len(extracted_model) > 2 and extracted_model in master_model: is_match = True
                                        elif extracted_name and len(extracted_name) > 2 and extracted_name in master_name: is_match = True
                                            
                                        if is_match:
                                            item["catchphrase"] = res.get("catchphrase", "")
                                            item["benefit_1"] = res.get("benefit_1", "")
                                            item["benefit_2"] = res.get("benefit_2", "")
                                            item["benefit_3"] = res.get("benefit_3", "")
                                            item["safety_note"] = res.get("safety_note", "")
                                            match_count += 1
                                            results_summary.append(f"✅ 結合成功: {pdf_file.name} ➔ {item.get('name')} (型式: {item.get('model')})")
                                            break
                            
                            if match_count == 0: results_summary.append(f"⚠️ マッチ対象なし: {pdf_file.name}")
                            else: results_summary.append(f"📄 {pdf_file.name} から計 {match_count} 件の商品を抽出し、マスタに結合しました。")

                        except Exception as e:
                            results_summary.append(f"❌ 解析エラー ({pdf_file.name}): {e}")
                        
                        completed += 1
                        progress_bar.progress(completed / len(uploaded_pdfs))
                        status_text.text(f"解析中... ({completed}/{len(uploaded_pdfs)})")
                
                save_master_data()
                status_text.text("🎉 すべての処理が完了しました！")
                
                with st.expander("処理結果の詳細を見る", expanded=True):
                    for msg in results_summary:
                        if "✅" in msg: st.success(msg)
                        elif "⚠️" in msg: st.warning(msg)
                        elif "📄" in msg: st.info(msg)
                        else: st.error(msg)

    st.markdown("#### ✏️ 3. マスタデータの一覧編集 ＆ 削除")
    if st.session_state.master_data:
        df_master = pd.DataFrame(st.session_state.master_data)
        if "delete_flag" not in df_master.columns: df_master["delete_flag"] = False
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
            if st.button("🚨 一括削除", use_container_width=True): confirm_delete_all()
    else:
        st.warning("現在登録されているマスタデータはありません。")

# =========================================================
# 画面B：アセスメント ＆ AI提案
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
            available_categories = sorted(list(set([item.get("category", "") for item in st.session_state.master_data if item.get("category")])))
            selected_cats = st.multiselect("マスタから選定する種目を選択", available_categories, default=available_categories[:1] if available_categories else None)

    generate_btn = st.button("🔍 実情に寄り添うパッケージ提案を生成", type="primary", use_container_width=True)

    def call_gemini(prompt: str, is_json: bool = False) -> str:
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

                system_prompt = f"""あなたは福祉用具専門相談員のアシスタントAIです。
以下の【マスタ】の中に存在する商品のみを使って、指定された【複数種目の用具】を組み合わせたパッケージを2軸で提案してください。
【マスタ】{master_text}
【対象者情報】状況: {user_status} / 環境: {env_status}

【厳守JSONフォーマット】
{{
  "proposals": [
    {{
      "axis_title": "① 【自立支援 特化セット】", 
      "tool_name": "提案する具体的な商品名と型式",
      "tais_codes": ["マスタに存在するTAISコード1"], 
      "axis_description": "選定の狙い",
      "talk_script": "スタッフへの提案ヒント", 
      "plan_target": "計画書の目標", 
      "plan_reason": "選定理由"
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
                    else: st.caption("※該当商品のスライドデータがありません")
                
                st.code(f"【利用目標】\n{p['plan_target']}\n\n【選定理由】\n{p['plan_reason']}", language="text")

        st.markdown("---")
        with st.container(border=True):
            if st.session_state.meeting_summary: st.code(st.session_state.meeting_summary, language="text")
            st.text_area("提案後のメモ", placeholder="例：ご本人様より「転倒が不安」との声があり、①で合意。", height=80, label_visibility="collapsed")
