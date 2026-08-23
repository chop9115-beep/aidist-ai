import streamlit as st
import json
import os
import pandas as pd
from dotenv import load_dotenv
from google import genai
from google.genai import types

# ---------------------------------------------------------
# 1. 基本設定 ＆ APIキー読み込み
# ---------------------------------------------------------
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MASTER_FILE_PATH = "welfare_master_data.json"

st.set_page_config(
    page_title="Aidist AI - 福祉用具選定",
    page_icon="🦼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------------------------------------------------------
# 2. スタイル設定
# ---------------------------------------------------------
st.markdown(
    """
    <style>
        html, body, [class*="css"] { font-size: 13.5px; }
        header[data-testid="stHeader"] { display: none !important; }
        .block-container { padding: 15px 2rem 200px 2rem !important; }
        .dock-title { font-size: 0.95rem; font-weight: 700; color: #5B7083; margin-bottom: 4px; }
        .sub-check-box { margin-top: -10px; margin-bottom: 15px; padding-left: 15px; border-left: 3px solid #cbd5e1; }
        /* プレゼンスライド用 */
        .slide-catchphrase { font-size: 1.8rem; font-weight: 800; color: #1E40AF; text-align: center; margin-bottom: 1rem; line-height: 1.4; }
        .slide-benefit { font-size: 1.3rem; font-weight: 700; color: #334155; margin-bottom: 0.8rem; padding: 15px; background-color: #F8FAFC; border-left: 6px solid #3B82F6; border-radius: 4px; }
        .slide-note { font-size: 1.1rem; color: #991B1B; background-color: #FEF2F2; padding: 15px; border-radius: 4px; margin-top: 20px; font-weight: 600; }
        .slide-price { font-size: 1.2rem; font-weight: 700; color: #047857; text-align: right; margin-top: 10px;}
    </style>
    """,
    unsafe_allow_html=True
)

# ---------------------------------------------------------
# 3. データ永続化（保存・読み込み）
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

# ---------------------------------------------------------
# 4. セッションステート ＆ 初期マスタ設定
# ---------------------------------------------------------
if "proposals_data" not in st.session_state: st.session_state.proposals_data = None
if "meeting_summary" not in st.session_state: st.session_state.meeting_summary = ""
if "master_data" not in st.session_state:
    loaded = load_master_data()
    if loaded:
        st.session_state.master_data = loaded
    else:
        st.session_state.master_data = [
            {
                "tais_code": "00789-000001", "category": "【貸与】特殊寝台本体", 
                "name": "楽匠プラス 2モーター", "maker": "パラマウントベッド", "model": "KQ-73310", "rental_price": "1,000円",
                "is_active": True, "memo": "腹部圧迫感が少なく好評。", 
                "catchphrase": "ベッドから安全に立ち上がれる安心感",
                "benefit_1": "独自の動きで、起き上がる時のお腹への圧迫感を和らげます",
                "benefit_2": "超低床設計でしっかり足が着き、転倒の不安を減らします",
                "benefit_3": "スマートフォンと連動し、ご家族が状態を確認できます",
                "safety_note": "⚠️ 背上げ操作をする際は、周囲に手を挟まないようご注意ください"
            }
        ]
        save_master_data()

# ---------------------------------------------------------
# 5. AI通信 ＆ 解析関数
# ---------------------------------------------------------
def call_gemini(prompt: str, is_json: bool = False) -> str:
    if not GEMINI_API_KEY: raise ValueError("APIキーが設定されていません。")
    client = genai.Client(api_key=GEMINI_API_KEY)
    config = types.GenerateContentConfig(response_mime_type="application/json" if is_json else "text/plain", temperature=0.2)
    response = client.models.generate_content(model="gemini-3.6-flash", contents=prompt, config=config)
    return response.text.strip()

def process_catalog_pdf(pdf_bytes: bytes, filename: str) -> list:
    if not GEMINI_API_KEY: raise ValueError("APIキーが設定されていません。")
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = """以下の福祉用具PDFから情報を抽出しJSONで出力してください。
【抽出項目】"tais_code", "name", "maker", "model", "category"
【スライド要素】
- "catchphrase": 利用者が直感的にメリットを感じる一言（20文字以内）
- "benefit_1"〜"benefit_3": 視覚的・機能的メリット（各30文字以内）
- "safety_note": 現場で伝えるべき注意事項
フォーマット: [{"tais_code":"", "name":"", "maker":"", "model":"", "category":"", "catchphrase":"", "benefit_1":"", "benefit_2":"", "benefit_3":"", "safety_note":""}]"""
    pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
    config = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
    response = client.models.generate_content(model="gemini-3.6-flash", contents=[pdf_part, prompt], config=config)
    clean_json = response.text.strip().replace("```json", "").replace("```", "")
    return json.loads(clean_json)

# ---------------------------------------------------------
# 6. 「ご利用者向けスライド」モーダル
# ---------------------------------------------------------
@st.dialog("✨ ご利用者向け 提案スライド", width="large")
def show_presentation_slide(item):
    st.markdown(f"<div class='slide-catchphrase'>{item.get('catchphrase', '安心・安全な生活をサポートします')}</div>", unsafe_allow_html=True)
    st.markdown(f"**■ {item.get('name','')}** （{item.get('maker','')}） / 型式: {item.get('model','')}")
    
    if item.get('benefit_1'): st.markdown(f"<div class='slide-benefit'>💡 {item['benefit_1']}</div>", unsafe_allow_html=True)
    if item.get('benefit_2'): st.markdown(f"<div class='slide-benefit'>💡 {item['benefit_2']}</div>", unsafe_allow_html=True)
    if item.get('benefit_3'): st.markdown(f"<div class='slide-benefit'>💡 {item['benefit_3']}</div>", unsafe_allow_html=True)
    
    if item.get('safety_note'): st.markdown(f"<div class='slide-note'>{item['safety_note']}</div>", unsafe_allow_html=True)
    if item.get('rental_price'): st.markdown(f"<div class='slide-price'>目安ご利用料金： {item['rental_price']}</div>", unsafe_allow_html=True)

# ---------------------------------------------------------
# 7. サイドバー：アカウント ＆ ナレッジ管理
# ---------------------------------------------------------
with st.sidebar:
    st.info("👤 アカウント: 管理者 (ライセンス 1/5)")
    st.success("📢 お知らせ: CSVマッピング機能が追加されました。")
    st.markdown("### ⚙️ ナレッジ・マスタ管理")
    
    with st.expander("📄 PDFカタログの登録"):
        uploaded_pdf = st.file_uploader("PDFを選択", type=["pdf"])
        if uploaded_pdf and st.button("AIで解析して追加"):
            with st.spinner("情報を抽出中..."):
                try:
                    new_items = process_catalog_pdf(uploaded_pdf.getvalue(), uploaded_pdf.name)
                    st.session_state.master_data.extend(new_items)
                    save_master_data()
                    st.success("追加しました！")
                except Exception as e:
                    st.error(f"エラー: {e}")

    with st.expander("📊 CSVインポート（マッピング）"):
        st.caption("基幹システム等のCSVを読み込み、列を紐付けます。")
        uploaded_csv = st.file_uploader("CSVを選択", type=["csv"])
        if uploaded_csv:
            try:
                df = pd.read_csv(uploaded_csv)
                st.write("▼ プレビュー (最初の3行)")
                st.dataframe(df.head(3))
                
                cols = ["(未割り当て)"] + df.columns.tolist()
                st.markdown("**列の紐付け（マッピング）**")
                col_tais = st.selectbox("TAISコード", cols, index=0)
                col_name = st.selectbox("商品名", cols, index=0)
                col_maker = st.selectbox("メーカー", cols, index=0)
                col_model = st.selectbox("型式", cols, index=0)
                col_price = st.selectbox("レンタル価格", cols, index=0)
                
                if st.button("マッピングして登録"):
                    new_items = []
                    for _, row in df.iterrows():
                        new_items.append({
                            "tais_code": str(row[col_tais]) if col_tais != "(未割り当て)" else "",
                            "name": str(row[col_name]) if col_name != "(未割り当て)" else "",
                            "maker": str(row[col_maker]) if col_maker != "(未割り当て)" else "",
                            "model": str(row[col_model]) if col_model != "(未割り当て)" else "",
                            "rental_price": str(row[col_price]) if col_price != "(未割り当て)" else "",
                            "category": "【貸与】未分類", 
                            "is_active": True,
                            "memo": ""
                        })
                    st.session_state.master_data.extend(new_items)
                    save_master_data()
                    st.success(f"{len(new_items)}件を登録しました！")
            except Exception as e:
                st.error("CSV読み込みエラーです。")

    with st.expander("✏️ マスタの検索・編集"):
        if st.session_state.master_data:
            df_master = pd.DataFrame(st.session_state.master_data)
            edited_df = st.data_editor(df_master, num_rows="dynamic", use_container_width=True, hide_index=True)
            if st.button("編集内容を保存"):
                st.session_state.master_data = edited_df.to_dict(orient="records")
                save_master_data()
                st.success("保存しました！")
        else:
            st.write("データがありません。")

# ---------------------------------------------------------
# 8. メイン画面：入力フォーム
# ---------------------------------------------------------
st.markdown("### 🦼 Aidist AI - 福祉用具選定アシスト")
st.markdown("---")

with st.expander("📝 対象者アセスメント・利用環境の入力", expanded=True):
    c1, c2 = st.columns(2)
    with c1:
        care_level = st.selectbox("要介護度", ["要支援1", "要支援2", "要介護1", "要介護2", "要介護3", "要介護4", "要介護5"], index=3)
        user_status = st.text_area("身体状況・主訴・ADL・心理状況", value="80代女性。圧迫骨折後で腰部痛あり。歩行意欲はあるが転倒不安が強い。", height=100)
        env_status = st.text_area("住環境・介助体制", value="マンション。主な介助者は80代の夫で負担軽減が必要。", height=70)

    with c2:
        st.markdown("**📦 複合パッケージ（選定種目）の指定**")
        main_categories = st.multiselect("基本の福祉用具", ["特殊寝台（ベッド）", "車いす", "手すり", "床ずれ防止用具", "未分類(CSV追加分)"], default=["特殊寝台（ベッド）"])
        
        selected_cats = []
        if "特殊寝台（ベッド）" in main_categories:
            selected_cats.append("【貸与】特殊寝台本体")
            st.markdown("<div class='sub-check-box'>", unsafe_allow_html=True)
            if st.checkbox("＋ マットレスも追加", value=True): selected_cats.append("【貸与】特殊寝台付属品（マットレス）")
            st.markdown("</div>", unsafe_allow_html=True)
        if "車いす" in main_categories: selected_cats.append("【貸与】車いす本体")
        if "手すり" in main_categories: selected_cats.append("【貸与】手すり")
        if "未分類(CSV追加分)" in main_categories: selected_cats.append("【貸与】未分類")

generate_btn = st.button("🔍 実情に寄り添うパッケージ提案を生成", type="primary", use_container_width=True)

# ---------------------------------------------------------
# 9. 生成処理の実行 (完全版AIプロンプト)
# ---------------------------------------------------------
if generate_btn:
    with st.spinner("AIが対象者の不安や疲労を読み解き、最適な複合パッケージを構築中..."):
        try:
            active_items = [item for item in st.session_state.master_data if item.get("is_active", True) and item.get("category") in selected_cats]
            master_text = "【利用可能な自社登録マスタ】\n"
            for item in active_items:
                master_text += f"- TAIS:{item.get('tais_code','')} | 品名:{item.get('name','')} | 種目:{item.get('category','')} | ノウハウ:{item.get('memo','')}\n"

            system_prompt = f"""
あなたは福祉用具専門相談員のアシスタントAIです。
以下の【マスタデータ】から、指定された【複数種目の用具】を組み合わせたパッケージを2軸で提案してください。
【マスタデータ】
{master_text}
【対象者情報】
・状況: {user_status}
・環境: {env_status}

【厳守JSONフォーマット】
{{
  "proposals": [
    {{
      "axis_title": "① 【自立支援・機能維持 特化セット】",
      "tool_name": "提案する用具一式",
      "tais_codes": ["00789-000001"], 
      "axis_description": "選定の狙い",
      "talk_script": "スタッフへの提案ヒント（箇条書き）",
      "plan_target": "計画書の目標",
      "plan_reason": "選定理由"
    }},
    {{ "axis_title": "② 【介助軽減 特化セット】", "tool_name": "...", "tais_codes": [], "axis_description": "...", "talk_script": "...", "plan_target": "...", "plan_reason": "..." }}
  ],
  "meeting_summary": "アセスメントと検討内容の要約"
}}
"""
            result_data = json.loads(call_gemini(system_prompt, is_json=True))
            st.session_state.proposals_data = result_data
            st.session_state.meeting_summary = result_data.get("meeting_summary", "")
            st.rerun()
        except Exception as e:
            st.error(f"提案生成中にエラーが発生しました: {e}")

# ---------------------------------------------------------
# 10. 結果表示 ＆ 【見える化スライドボタン】
# ---------------------------------------------------------
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
                st.markdown("**💡 スタッフへの提案ヒント・カンペ**")
                st.info(p["talk_script"])
                
            with col_slide:
                st.markdown("**📺 ご利用者向けスライド（可視化）**")
                tais_list = p.get("tais_codes", [])
                found_items = [item for item in st.session_state.master_data if item.get("tais_code") in tais_list]
                
                if found_items:
                    for item in found_items:
                        if st.button(f"📱 {item.get('name','')} の図解を見る", key=f"slide_btn_{i}_{item.get('tais_code','x')}", use_container_width=True):
                            show_presentation_slide(item)
                else:
                    st.caption("※該当商品のスライドデータがマスタにありません")
            
            st.markdown("**📋 福祉用具サービス計画書（原案テキスト）**")
            st.code(f"【利用目標】\n{p['plan_target']}\n\n【選定理由・具体的な適合状況】\n{p['plan_reason']}", language="text")

# ---------------------------------------------------------
# 11. 最下部スクロール固定：要点AIまとめ ＆ メモ入力欄
# ---------------------------------------------------------
st.markdown("---")
st.markdown("<div class='dock-title'>📑 要点AIまとめ ＆ 提案後メモ</div>", unsafe_allow_html=True)
with st.container(border=True):
    if st.session_state.meeting_summary:
        st.code(st.session_state.meeting_summary, language="text")
    st.text_area("提案後のメモ", placeholder="例：提案後、ご本人様より「転倒が不安」との声があり、①のセットで合意。", height=80, label_visibility="collapsed")
