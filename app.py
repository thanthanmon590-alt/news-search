import streamlit as st
import pandas as pd
import json
import re
from groq import Groq
from supabase import create_client, Client

st.set_page_config(page_title="AI 뉴스 에이전트", layout="wide")

GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

client = Groq(api_key=GROQ_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

def parse_json_garbage(text):
    try:
        json_match = re.search(r'\[.*\]', text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        return None
    except:
        return None

st.title("📰 AI 최신 뉴스 검색 & 자동 저장기")

tab1, tab2, tab3 = st.tabs(["🔍 검색하기", "💾 저장된 뉴스 보기", "📊 통계 분석"])

with tab1:
    keyword = st.text_input("검색하고 싶은 뉴스 키워드를 입력하세요:", placeholder="예: 생성형 AI 트렌드")
    search_btn = st.button("최신 뉴스 검색 및 저장")

    if search_btn and keyword:
        with st.spinner("AI가 뉴스를 분석 중입니다..."):
            prompt = f"키워드 '{keyword}'에 대한 최신 뉴스 2건을 검색해. 제목(title), 출처(source), 날짜(news_date), URL(url), 요약(summary)을 포함한 JSON 배열 형식으로만 응답해."
            
            try:
                response = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.0
                )
                
                news_list = parse_json_garbage(response.choices[0].message.content)
                
                if news_list:
                    for news in news_list:
                        with st.container():
                            st.subheader(news.get('title'))
                            st.caption(f"출처: {news.get('source')} | 날짜: {news.get('news_date')}")
                            st.write(news.get('summary'))
                            st.write(f"[기사 원문 보기]({news.get('url')})")
                            
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
                                    st.info("이미 저장된 뉴스입니다.")
                                else:
                                    st.error(f"저장 오류: {e}")
                            st.divider()
                else:
                    st.warning("뉴스를 찾지 못했습니다. 다시 시도해 주세요.")
                    
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")

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

with tab3:
    st.subheader("데이터 분석 대시보드")
    try:
        res = supabase.table("news_history").select("*").execute()
        if res.data:
            df = pd.DataFrame(res.data)
            col1, col2 = st.columns(2)
            with col1:
                st.metric("전체 저장된 뉴스", len(df))
            st.write("### 키워드별 뉴스 비중")
            keyword_counts = df['keyword'].value_counts()
            st.bar_chart(keyword_counts)
            st.write("### 날짜별 저장 건수")
            df['created_at_date'] = pd.to_datetime(df['created_at']).dt.date
            date_counts = df.groupby('created_at_date').size()
            st.line_chart(date_counts)
        else:
            st.write("분석할 데이터가 부족합니다.")
    except Exception as e:
        st.error(f"분석 로드 실패: {e}")
