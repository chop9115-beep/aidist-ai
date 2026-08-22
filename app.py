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
    page_title="Aidist AI - 福祉用具選定アシスト",
    page_icon="🦼",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ---------------------------------------------------------
# 2. スタイル設定
# ---------------------------------------------------------
st.markdown(
    """
    <meta name="google" content="notranslate">
    <style>
        html, body, [class*="css"] { font-size: 13.5px; }
        header[data-testid="stHeader"] { display: none !important; }
        .block-container { padding: 15px 2rem 200px 2rem !important; }
        .dock-title { font-size: 0.95rem; font-weight: 700; color: #5B7083; margin-bottom: 4px; display: flex; align-items: center; gap: 6px; }
        textarea { font-size: 12.5px !important; }
        .ime-alpha input { ime-mode: inactive !important; }
        .ime-hiragana input { ime-mode: active !important; }
        .sub-check-box { margin-top: -10px; margin-bottom: 15px; padding-left: 15px; border-left: 3px solid #cbd5e1; }
    </style>
    """,
    unsafe_allow_html=True
)

# ---------------------------------------------------------
# 3. データ永続化（保存・読み込み）関数
# ---------------------------------------------------------
def save_master_data():
    data = {
        "rent": st.session_state.rent_master,
        "sale": st.session_state.sale_master
    }
    with open(MASTER_FILE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_master_data():
    if os.path.exists(MASTER_FILE_PATH):
        try:
            with open(MASTER_FILE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("rent", []), data.get("sale", [])
        except Exception:
            pass
    return None, None

def normalize_text(text: str) -> str:
    if not text: return ""
    res = []
    for ch in text.lower():
        code = ord(ch)
        res.append(chr(code - 0x60) if 0x30A1 <= code <= 0x30F6 else ch)
    return "".join(res)

# ---------------------------------------------------------
# 4. セッションステート ＆ 初期マスタデータ設定
# ---------------------------------------------------------
if "proposals_data" not in st.session_state: st.session_state.proposals_data = None
if "meeting_summary" not in st.session_state: st.session_state.meeting_summary = ""
if "show_bell" not in st.session_state: st.session_state.show_bell = False
if "show_knowledge" not in st.session_state: st.session_state.show_knowledge = False
if "show_user" not in st.session_state: st.session_state.show_user = False
if "is_logged_in" not in st.session_state: st.session_state.is_logged_in = True
if "use_techno_aid" not in st.session_state: st.session_state.use_techno_aid = False
if "edit_memo_state" not in st.session_state: st.session_state.edit_memo_state = {}
if "edit_basic_state" not in st.session_state: st.session_state.edit_basic_state = {}

# マスタデータの読み込み（JSONがあれば優先、なければダミー）
if "rent_master" not in st.session_state or "sale_master" not in st.session_state:
    loaded_rent, loaded_sale = load_master_data()
    if loaded_rent is not None and loaded_sale is not None:
        st.session_state.rent_master = loaded_rent
        st.session_state.sale_master = loaded_sale
    else:
        st.session_state.rent_master = [
            {"tais_code": "00123-000001", "service_code": "171001", "category": "【貸与】車いす本体", "name": "超低床自走式車いす ネクストコア-ミニモ", "maker": "松永製作所", "is_active": True, "memo": "足こぎ移動を希望される小柄な方に非常に適応しやすい。", "catalog_ref": "総合カタログ2026 P.42", "catalog_specs": "座面高:35cm, 重量:11.8kg", "catalog_env": "室内、狭小な廊下", "catalog_features": "超低床設計でしっかり足が着く。超スリム＆コンパクト設計。"},
            {"tais_code": "00789-000001", "service_code": "171004", "category": "【貸与】特殊寝台本体", "name": "楽匠プラス 2モーター", "maker": "パラマウントベッド", "is_active": True, "memo": "起き上がり時の腹部への圧迫感が少なく、痛みを気にする方に好評。", "catalog_ref": "ベッドカタログ2026 P.10", "catalog_specs": "全幅:99cm, 全長:201cm", "catalog_env": "一般的な居室", "catalog_features": "背上げ・高さ調整機能。"},
            {"tais_code": "00789-000002", "service_code": "171005", "category": "【貸与】特殊寝台付属品（マットレス）", "name": "ストレッチフィットマットレス", "maker": "パラマウントベッド", "is_active": True, "memo": "寝返りが打ちやすく、端座位も安定する。", "catalog_ref": "ベッドカタログ2026 P.25", "catalog_specs": "厚さ:9cm, 幅:91cm", "catalog_env": "ベッド上", "catalog_features": "独自のストレッチ構造。"},
            {"tais_code": "00789-000003", "service_code": "171006", "category": "【貸与】特殊寝台付属品（サイドレール・手すり）", "name": "スイングアーム介助バー", "maker": "パラマウントベッド", "is_active": True, "memo": "立ち上がり時の支えとして非常に安心感がある。", "catalog_ref": "ベッドカタログ2026 P.40", "catalog_specs": "角度調整:0〜120度", "catalog_env": "ベッドサイド", "catalog_features": "スイングアームで立ち上がり動線をサポート。"},
            {"tais_code": "00999-000001", "service_code": "171007", "category": "【貸与】手すり", "name": "ルーツHS あがりかまちタイプ", "maker": "モルテン", "is_active": True, "memo": "置くだけで設置できるので、急ぎの退院時に重宝する。", "catalog_ref": "手すりカタログ2026 P.5", "catalog_specs": "ベースプレート:幅70×奥行60cm", "catalog_env": "玄関、段差のある場所", "catalog_features": "工事不要の据え置き型。"}
        ]
        st.session_state.sale_master = [
            {"tais_code": "00456-000001", "service_code": "271001", "category": "【購入】入浴補助用具", "name": "折りたたみシャワーベンチ FSフィット", "maker": "アロン化成", "is_active": True, "memo": "片手でたためるため、介助者が片手でシャワーを持っている状況で便利。", "catalog_ref": "入浴機器カタログ2026 P.12", "catalog_specs": "重量:約4kg", "catalog_env": "狭小な浴室", "catalog_features": "ワンタッチ折りたたみ機能。"}
        ]
        save_master_data()

# ---------------------------------------------------------
# 5. AI通信 ＆ PDF-OCR解析関数
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
    prompt = """あなたは福祉用具カタログの解析エキスパートです。以下のPDFから情報を抽出し、JSONフォーマットで出力してください。
【厳守事項】基本情報（TAIS、商品名、メーカー）と「主な仕様」「環境」「特徴（簡潔な要約）」を抽出。
【フォーマット】: [{"tais_code":"", "name":"", "maker":"", "catalog_specs":"", "catalog_env":"", "catalog_features":"", "page_info":""}]"""
    pdf_part = types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
    config = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
    response = client.models.generate_content(model="gemini-3.6-flash", contents=[pdf_part, prompt], config=config)
    clean_json = response.text.strip().replace("```json", "").replace("```", "")
    return json.loads(clean_json)

# ---------------------------------------------------------
# 6. 一覧表モーダルビュー
# ---------------------------------------------------------
@st.dialog("📄 福祉用具マスタ 全件一覧ビュー", width="large")
def show_master_table_modal(mode="rent"):
    data_list = st.session_state.rent_master if mode == "rent" else st.session_state.sale_master
    st.markdown("#### 📋 福祉用具マスタ一覧")
    st.markdown('<div class="ime-alpha">', unsafe_allow_html=True)
    modal_query = st.text_input("🔍 全件内リアルタイム絞り込み検索", key="modal_query_input")
    st.markdown('</div>', unsafe_allow_html=True)

    filtered = [d for d in data_list if not modal_query.strip() or normalize_text(modal_query.strip()) in normalize_text(f"{d['tais_code']} {d['name']} {d['maker']} {d['memo']}")]
    df = pd.DataFrame(filtered).rename(columns={"tais_code": "TAIS", "category": "種目", "name": "商品名", "maker": "メーカー", "is_active": "対象", "memo": "自社ノウハウ"})
    
    if not df.empty:
        st.dataframe(df[["TAIS", "種目", "商品名", "メーカー", "対象", "自社ノウハウ"]], use_container_width=True, hide_index=True, height=380)
    else:
        st.warning("一致する商品は見つかりませんでした。")

# ---------------------------------------------------------
# 7. ヘッダー ＆ ナレッジ管理パネル
# ---------------------------------------------------------
h_left, h_space, h_bell, h_know, h_user = st.columns([5.5, 0.7, 0.9, 1.7, 1.2], gap="small")

with h_left:
    st.markdown("""
        <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 2px;">
            <div style="background-color: #5B7083; color: #ffffff; font-weight: 800; font-size: 15px; padding: 4px 10px; border-radius: 6px;">AI</div>
            <div style="display: flex; align-items: baseline; gap: 8px;">
                <span style="font-size: 1.5rem; font-weight: 800; color: #5B7083; letter-spacing: -0.5px;">Aidist AI</span>
                <span style="font-size: 0.85rem; font-weight: 600; color: #7B8E9E;">福祉用具選定アシスト</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

with h_know:
    if st.button("マスタ・ナレッジ管理", use_container_width=True):
        st.session_state.show_knowledge = not st.session_state.show_knowledge
        st.session_state.show_bell = st.session_state.show_user = False

if st.session_state.show_knowledge:
    with st.container(border=True):
        st.markdown("<div class='dock-title'>📚 福祉用具マスタ ＆ 商品ナレッジ管理</div>", unsafe_allow_html=True)
        
        # 1. 個別編集
        with st.expander("📦 1. 福祉用具マスタ 個別編集・検索", expanded=True):
            m_tab1, m_tab2 = st.tabs(["【貸与】個別編集", "【販売】個別編集"])
            with m_tab1:
                tb_btn_col1, tb_btn_col2 = st.columns([3, 1])
                with tb_btn_col1: st.caption("検索窓に入力すると個別編集スペースが開きます。")
                with tb_btn_col2:
                    if st.button("📄 全件一覧を別画面で開く", key="btn_open_rent"): show_master_table_modal(mode="rent")

                s_col1, s_col2 = st.columns([1.2, 2.8])
                with s_col1:
                    st.markdown('<div class="ime-alpha">', unsafe_allow_html=True)
                    s_tais = st.text_input("TAIS検索（英数字）", key="s_rent_tais")
                    st.markdown('</div>', unsafe_allow_html=True)
                with s_col2:
                    st.markdown('<div class="ime-hiragana">', unsafe_allow_html=True)
                    s_name = st.text_input("商品名/メーカー検索", key="s_rent_name")
                    st.markdown('</div>', unsafe_allow_html=True)

                if s_tais.strip() or s_name.strip():
                    matched = [item for item in st.session_state.rent_master if (not s_tais.strip() or s_tais.strip() in item["tais_code"]) and (not s_name.strip() or normalize_text(s_name.strip()) in normalize_text(item["name"] + " " + item["maker"]))]
                    if matched:
                        for m_item in matched:
                            code = m_item['tais_code']
                            is_memo_edit = st.session_state.edit_memo_state.get(code, False)
                            is_basic_edit = st.session_state.edit_basic_state.get(code, False)
                            
                            with st.container(border=True):
                                b_top1, b_top2 = st.columns([4, 1.2])
                                with b_top1: st.markdown("##### 📦 商品基本情報")
                                with b_top2:
                                    if not is_basic_edit:
                                        if st.button("⚙️ 基本情報編集", key=f"btn_eb_{code}", use_container_width=True):
                                            st.session_state.edit_basic_state[code] = True
                                            st.rerun()
                                    else:
                                        if st.button("💾 基本情報保存", key=f"btn_sb_{code}", type="primary", use_container_width=True):
                                            m_item["tais_code"] = st.session_state[f"i_tais_{code}"]
                                            m_item["name"] = st.session_state[f"i_name_{code}"]
                                            m_item["maker"] = st.session_state[f"i_maker_{code}"]
                                            st.session_state.edit_basic_state[code] = False
                                            save_master_data()
                                            st.success("更新しました。")
                                            st.rerun()

                                ic1, ic2, ic3 = st.columns([1.5, 3.5, 1.5])
                                with ic1: st.text_input("TAIS", value=m_item["tais_code"], disabled=not is_basic_edit, key=f"i_tais_{code}")
                                with ic2: st.text_input("商品名", value=m_item["name"], disabled=not is_basic_edit, key=f"i_name_{code}")
                                with ic3: st.text_input("メーカー", value=m_item["maker"], disabled=not is_basic_edit, key=f"i_maker_{code}")

                                st.markdown("<hr style='margin: 8px 0;'>", unsafe_allow_html=True)

                                n_top1, n_top2 = st.columns([4, 1.2])
                                with n_top1: st.markdown("##### 📝 独自ノウハウ・現場メモ")
                                with n_top2:
                                    if not is_memo_edit:
                                        if st.button("📝 ノウハウ編集", key=f"btn_em_{code}", use_container_width=True):
                                            st.session_state.edit_memo_state[code] = True
                                            st.rerun()
                                    else:
                                        if st.button("💾 ノウハウ保存", key=f"btn_sm_{code}", type="primary", use_container_width=True):
                                            m_item["memo"] = st.session_state[f"i_memo_{code}"]
                                            m_item["is_active"] = st.session_state[f"i_act_{code}"]
                                            st.session_state.edit_memo_state[code] = False
                                            save_master_data()
                                            st.success("更新しました。")
                                            st.rerun()

                                ec1, ec2 = st.columns([4, 1.2])
                                with ec1: st.text_area("独自ノウハウ", value=m_item["memo"], height=75, disabled=not is_memo_edit, key=f"i_memo_{code}")
                                with ec2:
                                    st.write("")
                                    st.checkbox("選定対象に含める", value=m_item["is_active"], disabled=not is_memo_edit, key=f"i_act_{code}")

            with m_tab2:
                if st.button("📄 全件一覧を別画面で開く（販売）", key="btn_open_sale"): show_master_table_modal(mode="sale")
        
        # 2. PDF登録
        with st.expander("📑 2. カタログPDF登録（OCR）", expanded=False):
            uploaded_pdf = st.file_uploader("最新カタログPDF", type=["pdf"])
            if uploaded_pdf and st.button("🔍 PDFを解析してマスタ反映", type="primary"):
                with st.spinner("AIが抽出中..."):
                    try:
                        extracted = process_catalog_pdf(uploaded_pdf.read(), uploaded_pdf.name)
                        for ext in extracted:
                            tais = ext.get("tais_code", "").strip()
                            if tais:
                                existing = next((item for item in st.session_state.rent_master if item["tais_code"] == tais), None)
                                if existing:
                                    existing["catalog_ref"] = f"{uploaded_pdf.name} {ext.get('page_info','')}"
                                    existing["catalog_features"] = ext.get("catalog_features", "")
                                else:
                                    st.session_state.rent_master.append({"tais_code": tais, "service_code": "新規未登録", "category": "【貸与】その他", "name": ext.get("name",""), "maker": ext.get("maker",""), "is_active": True, "memo": "", "catalog_features": ext.get("catalog_features","")})
                        save_master_data()
                        st.success("反映・保存が完了しました。")
                    except Exception as e:
                        st.error(f"エラー: {e}")

        # 3. ナレッジ設定
        with st.expander("🌐 3. 外部データ設定", expanded=False):
            st.session_state.use_techno_aid = st.checkbox("TAISデータを含める", value=st.session_state.use_techno_aid)
            
        # 4. データ連携 (インポート/エクスポート)
        with st.expander("🔄 4. マスタデータ連携（CSVインポート / エクスポート）", expanded=False):
            st.markdown("基幹システム等のデータを一括で連携します。")
            c_exp1, c_exp2 = st.columns(2)
            with c_exp1:
                st.markdown("**📤 エクスポート（全情報）**")
                df_export = pd.DataFrame(st.session_state.rent_master)
                csv_export = df_export.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 貸与マスタCSVをダウンロード", data=csv_export, file_name="aidist_rent_master.csv", mime="text/csv", use_container_width=True)
            with c_exp2:
                st.markdown("**📥 インポート（基幹システム等から）**")
                uploaded_csv = st.file_uploader("CSVファイルをアップロード", type=["csv"], key="csv_import")
                if uploaded_csv and st.button("💾 インポートを実行", use_container_width=True):
                    try:
                        df_import = pd.read_csv(uploaded_csv)
                        import_count = 0
                        for _, row in df_import.iterrows():
                            tais = str(row.get("tais_code", "")).strip()
                            if tais and tais != "nan":
                                existing = next((item for item in st.session_state.rent_master if item["tais_code"] == tais), None)
                                if not existing:
                                    st.session_state.rent_master.append({
                                        "tais_code": tais,
                                        "service_code": str(row.get("service_code", "")),
                                        "category": str(row.get("category", "【貸与】その他")),
                                        "name": str(row.get("name", "名称不明")),
                                        "maker": str(row.get("maker", "メーカー不明")),
                                        "is_active": True,
                                        "memo": "",
                                        "catalog_features": ""
                                    })
                                    import_count += 1
                        save_master_data()
                        st.success(f"{import_count}件の新規データをインポートして保存しました。")
                    except Exception as e:
                        st.error(f"インポートエラー: {e}")

st.markdown("<hr style='margin: 6px 0 14px 0; border: 0; border-top: 1px solid #E2E8F0;'>", unsafe_allow_html=True)

# ---------------------------------------------------------
# 8. メイン画面：入力 ＆ 動的UI提案生成
# ---------------------------------------------------------
with st.expander("📝 対象者アセスメント・利用環境の入力", expanded=True):
    c1, c2 = st.columns(2)
    with c1:
        care_level = st.selectbox("要介護度", ["要支援1", "要支援2", "要介護1", "要介護2", "要介護3", "要介護4", "要介護5"], index=3)
        user_status = st.text_area("身体状況・主訴・ADL・心理状況", value="80代女性。圧迫骨折後で腰部痛あり。歩行意欲はあるが疲労と転倒への不安が強く、長時間座っているのも辛い。", height=120)
        env_status = st.text_area("住環境・介助体制", value="マンション。廊下幅78cm。主な介助者は80代の夫で負担軽減が必要。", height=85)

    with c2:
        st.markdown("**📦 複合パッケージ（選定種目）の指定**")
        main_categories = st.multiselect("基本の福祉用具", ["特殊寝台（ベッド）", "車いす", "手すり", "床ずれ防止用具", "入浴補助・排泄（購入）"], default=["特殊寝台（ベッド）", "手すり"])
        
        selected_cats = []
        if "特殊寝台（ベッド）" in main_categories:
            selected_cats.append("【貸与】特殊寝台本体")
            st.markdown("<div class='sub-check-box'>", unsafe_allow_html=True)
            if st.checkbox("＋ マットレスも追加", value=True): selected_cats.append("【貸与】特殊寝台付属品（マットレス）")
            if st.checkbox("＋ サイドレール・介助バーも追加", value=True): selected_cats.append("【貸与】特殊寝台付属品（サイドレール・手すり）")
            st.markdown("</div>", unsafe_allow_html=True)
        if "車いす" in main_categories:
            selected_cats.append("【貸与】車いす本体")
        if "手すり" in main_categories:
            selected_cats.append("【貸与】手すり")

generate_btn = st.button("🔍 実情に寄り添うパッケージ提案を生成", type="primary", use_container_width=True)

# ---------------------------------------------------------
# 9. 生成処理の実行
# ---------------------------------------------------------
if generate_btn:
    with st.spinner("AIが対象者の不安や疲労を読み解き、最適な複合パッケージを構築中..."):
        try:
            active_items = [item for cat in selected_cats for item in st.session_state.rent_master + st.session_state.sale_master if item.get("is_active", True) and item.get("category") == cat]
            master_text = "【利用可能な自社登録マスタ】\n"
            for item in active_items:
                master_text += f"- TAIS:{item['tais_code']} | 品名:{item['name']} | 種目:{item['category']}\n"
                if item.get('memo'): master_text += f"  [ノウハウ]: {item['memo']}\n"
                master_text += f"  [仕様]: {item.get('catalog_features', '')}\n"

            system_prompt = f"""
あなたは福祉用具専門相談員のアシスタントAIです。
以下の【マスタデータ】から、指定された【複数種目の用具】を組み合わせた「パッケージ（一式）」を3軸で提案してください。

【マスタデータ】
{master_text}

【対象者情報】
・状況・心理: {user_status}
・環境: {env_status}
・指定用具リスト: {', '.join(selected_cats)}

【提案要件】
・対話形式は禁止。専門相談員が見て接客の引き出しとなる「スタッフへの提案ヒント（カンペ）」を箇条書きで簡潔に出力。
・対象者の不安などを読み取り、どういうメリットを伝えると効果的かを含める。
・meeting_summaryは「選定アシストによる提案方針（検討段階）」まで。合意内容は絶対に書かない。

【厳守JSONフォーマット】
{{
  "proposals": [
    {{
      "axis_title": "① 【自立支援・機能維持 特化セット】",
      "tool_name": "提案する用具一式（例: ベッド本体＋マットレス＋手すり）",
      "axis_description": "選定の狙い",
      "talk_script": "スタッフへの提案ヒント（箇条書き）",
      "plan_target": "計画書の目標",
      "plan_reason": "選定理由"
    }},
    {{ "axis_title": "② 【住環境適合・介助軽減 特化セット】", "tool_name": "...", "axis_description": "...", "talk_script": "...", "plan_target": "...", "plan_reason": "..." }},
    {{ "axis_title": "③ 【身体ケア・疼痛緩和 特化セット】", "tool_name": "...", "axis_description": "...", "talk_script": "...", "plan_target": "...", "plan_reason": "..." }}
  ],
  "meeting_summary": "【対象者の現状と課題】\\n...\\n\\n【選定アシストによる提案方針（検討段階）】\\n..."
}}
"""
            result_data = json.loads(call_gemini(system_prompt, is_json=True))
            st.session_state.proposals_data = result_data
            st.session_state.meeting_summary = result_data.get("meeting_summary", "")
            st.rerun()
        except Exception as e:
            st.error(f"提案生成中にエラー: {e}")

# ---------------------------------------------------------
# 10. 結果表示エリア
# ---------------------------------------------------------
if st.session_state.proposals_data:
    data = st.session_state.proposals_data
    st.markdown("---")
    st.markdown("<h4 style='color: #5B7083; margin-bottom: 8px;'>💡 選定提案結果（3つのパッケージアプローチ）</h4>", unsafe_allow_html=True)

    tabs = st.tabs([p["axis_title"] for p in data["proposals"]])

    for i, tab in enumerate(tabs):
        p = data["proposals"][i]
        with tab:
            st.markdown(f"**提案パッケージ:** `{p['tool_name']}`")
            st.markdown(f"**選定の狙い:** {p['axis_description']}")
            st.markdown("**💡 スタッフへの提案ヒント・カンペ**")
            st.info(p["talk_script"])
            
            st.markdown("**📋 福祉用具サービス計画書（原案テキスト）**")
            plan_full_text = f"【利用目標】\n{p['plan_target']}\n\n【選定理由・具体的な適合状況】\n{p['plan_reason']}"
            # コピーしやすいコードブロック（ネイティブのコピーボタン付き）で表示
            st.code(plan_full_text, language="text")

# ---------------------------------------------------------
# 11. 最下部スクロール固定：要点AIまとめ ＆ メモ入力欄
# ---------------------------------------------------------
st.markdown("---")
st.markdown("<div class='dock-title'>📑 要点AIまとめ ＆ 提案後メモ（サービス担当者会議用）</div>", unsafe_allow_html=True)
with st.container(border=True):
    if st.session_state.meeting_summary:
        st.markdown("**■ アセスメント・提案の要点（検討段階）**")
        st.code(st.session_state.meeting_summary, language="text")
        
        st.markdown("**■ 提案後のメモ・合意内容（担当者記入）**")
        st.text_area("提案後のメモ", placeholder="例：\n・提案後、ご本人様より「転倒が不安」との声があり、①のセットで合意。\n・※選択制対象品目（手すり等）のため、貸与と販売の両方が可能である旨を説明し貸与で決定。", height=100, label_visibility="collapsed")
    else:
        st.caption("「選定提案をアシスト生成」を実行すると、アセスメントの要点と提案方針がここにまとめられます。")