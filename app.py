import streamlit as st
import pandas as pd
import json
import re
from google import genai
from google.genai import types
from supabase import create_client, Client

# --- 1. 환경 설정 및 세션 관리 ---
st.set_page_config(page_title="AI 뉴스 에이전트", layout="wide")

# 시크릿 로드
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

# 클라이언트 초기화
client = genai.Client(api_key=GEMINI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. 도움 함수 ---
def parse_json_garbage(text):
    """Gemini 응답에서 JSON만 추출하는 함수"""
    try:
        # ```json ... ``` 형태나 그냥 [ ... ] 형태 대응
        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return None
    except:
        return None

# --- 3. 화면 구성 ---
st.title("📰 AI 최신 뉴스 검색 & 자동 저장기")

tab1, tab2, tab3 = st.tabs(["🔍 검색하기", "💾 저장된 뉴스 보기", "📊 통계 분석"])

# --- Tab 1: 검색하기 ---
with tab1:
    keyword = st.text_input("검색하고 싶은 뉴스 키워드를 입력하세요:", placeholder="예: 생성형 AI 트렌드")
    search_btn = st.button("최신 뉴스 검색 및 저장")

    if search_btn and keyword:
        with st.spinner("Gemini가 구글 검색을 통해 뉴스를 분석 중입니다..."):
            # Gemini API 호출 (Google Search Tool 활성화)
            # 주의: gemini-2.0-flash-exp 또는 gemini-1.5-flash 사용 가능
            prompt = f"키워드 '{keyword}'에 대한 가장 최신 뉴스 딱 2건만 검색해. 제목(title), 출처(source), 날짜(news_date), 원본 URL(url), 요약(summary)을 포함한 JSON 배열 형식으로만 응답해. 절대 URL을 지어내지 마."
            
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash-preview-05-20", # 최신 모델 사용
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        tools=[types.Tool(google_search=types.GoogleSearchRetrieval())],
                        temperature=0.0
                    )
                )
                
                # 결과 파싱
                news_list = parse_json_garbage(response.text)
                
                if news_list:
                    for news in news_list:
                        # 화면 출력
                        with st.container():
                            st.subheader(news.get('title'))
                            st.caption(f"출처: {news.get('source')} | 날짜: {news.get('news_date')}")
                            st.write(news.get('summary'))
                            st.write(f"[기사 원문 보기]({news.get('url')})")
                            
                            # Supabase 저장
                            data = {
                                "keyword": keyword,
                                "title": news.get('title'),
                                "source": news.get('source'),
                                "news_date": news.get('news_date'),
                                "url": news.get('url'),
                                "summary": news.get('summary')
                            }
                            
                            try:
                                supabase.table("news_history").insert(data).execute()
                                st.success(f"저장 완료: {news.get('title')[:20]}...")
                            except Exception as e:
                                if "duplicate" in str(e).lower():
                                    st.info("이미 저장된 뉴스입니다. (중복 생략)")
                                else:
                                    st.error(f"저장 오류: {e}")
                            st.divider()
                else:
                    st.warning("뉴스를 찾지 못했거나 형식이 올바르지 않습니다. 다시 시도해 주세요.")
                    st.write("모델 응답 원문:", response.text)
            
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")

# --- Tab 2: 저장된 뉴스 보기 ---
with tab2:
    st.subheader("최근 저장된 뉴스 목록")
    try:
        res = supabase.table("news_history").select("*").order("created_at", desc=True).execute()
        if res.data:
            df = pd.DataFrame(res.data)
            st.dataframe(df[["keyword", "title", "source", "news_date", "url", "summary", "created_at"]], use_container_width=True)
        else:
            st.write("저장된 뉴스가 없습니다.")
    except Exception as e:
        st.error(f"데이터 로드 실패: {e}")

# --- Tab 3: 통계 분석 ---
with tab3:
    st.subheader("데이터 분석 대시보드")
    try:
        res = supabase.table("news_history").select("*").execute()
        if res.data:
            df = pd.DataFrame(res.data)
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("전체 저장된 뉴스", len(df))
            
            # 키워드별 검색 건수
            st.write("### 키워드별 뉴스 비중")
            keyword_counts = df['keyword'].value_counts()
            st.bar_chart(keyword_counts)
            
            # 날짜별 저장 추이 (created_at 기준)
            st.write("### 날짜별 저장 건수")
            df['created_at_date'] = pd.to_datetime(df['created_at']).dt.date
            date_counts = df.groupby('created_at_date').size()
            st.line_chart(date_counts)
            
        else:
            st.write("분석할 데이터가 부족합니다.")
    except Exception as e:
        st.error(f"분석 로드 실패: {e}")
