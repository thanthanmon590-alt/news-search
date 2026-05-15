import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from groq import Groq
from supabase import create_client, Client
import re

st.set_page_config(page_title="AI 뉴스 에이전트", layout="wide")

# --- 시크릿 로드 ---
GROQ_API_KEY = st.secrets["GROQ_API_KEY"]
NAVER_CLIENT_ID = st.secrets["NAVER_CLIENT_ID"]
NAVER_CLIENT_SECRET = st.secrets["NAVER_CLIENT_SECRET"]
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

client = Groq(api_key=GROQ_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# --- HTML 태그 제거 ---
def clean_html(text):
    if not text:
        return ""
    text = re.sub(r"<.*?>", "", text)
    text = text.replace("&quot;", '"')
    text = text.replace("&amp;", "&")
    text = text.replace("&lt;", "<")
    text = text.replace("&gt;", ">")
    return text


# --- Naver News API로 최신 뉴스 검색 ---
def search_naver_news(keyword, display=5):
    url = "https://openapi.naver.com/v1/search/news.json"

    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }

    params = {
        "query": keyword,
        "display": display,
        "start": 1,
        "sort": "date",
    }

    response = requests.get(url, headers=headers, params=params, timeout=10)

    if response.status_code != 200:
        st.error(f"Naver News API 오류: {response.status_code}")
        st.write(response.text)
        return []

    data = response.json()
    news_list = []

    for item in data.get("items", []):
        title = clean_html(item.get("title", ""))
        description = clean_html(item.get("description", ""))
        link = item.get("originallink") or item.get("link")
        source = "Naver News"

        pub_date = item.get("pubDate", "")
        try:
            news_date = datetime.strptime(
                pub_date, "%a, %d %b %Y %H:%M:%S %z"
            ).date().isoformat()
        except Exception:
            news_date = datetime.today().date().isoformat()

        news_list.append({
            "keyword": keyword,
            "title": title,
            "source": source,
            "news_date": news_date,
            "url": link,
            "description": description,
        })

    return news_list


# --- Groq로 뉴스 요약 ---
def summarize_with_groq(title, description):
    prompt = f"""
다음 뉴스 제목과 설명을 한국어로 2문장 정도로 자연스럽게 요약해 주세요.

제목: {title}
설명: {description}
"""

    try:
        chat_completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "system",
                    "content": "너는 한국어 뉴스를 짧고 정확하게 요약하는 도우미야.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
        )
        return chat_completion.choices[0].message.content.strip()
    except Exception as e:
        return f"요약 생성 실패: {e}"


# --- Supabase 저장 ---
def save_news_to_supabase(news, summary):
    record = {
        "keyword": news["keyword"],
        "title": news["title"],
        "source": news["source"],
        "news_date": news["news_date"],
        "url": news["url"],
        "summary": summary,
    }

    supabase.table("news_history").upsert(
        record,
        on_conflict="url"
    ).execute()


# --- 화면 ---
st.title("📰 AI 최신 뉴스 검색 & 자동 저장기")

tab1, tab2, tab3 = st.tabs(["🔍 검색하기", "🗂️ 저장된 뉴스 보기", "📊 통계 분석"])


# --- 검색 탭 ---
with tab1:
    keyword = st.text_input(
        "검색하고 싶은 뉴스 키워드를 입력하세요:",
        placeholder="예: 인공지능, 마케팅, 전기차"
    )

    search_btn = st.button("최신 뉴스 검색 및 저장")

    if search_btn:
        if not keyword.strip():
            st.warning("검색어를 입력해 주세요.")
        else:
            news_items = search_naver_news(keyword, display=5)

            if not news_items:
                st.warning("검색 결과가 없습니다.")
            else:
                for news in news_items:
                    summary = summarize_with_groq(
                        news["title"],
                        news["description"]
                    )

                    st.subheader(news["title"])
                    st.write(f"출처: {news['source']} | 날짜: {news['news_date']}")
                    st.write(summary)
                    st.markdown(f"[기사 원문 보기]({news['url']})")

                    try:
                        save_news_to_supabase(news, summary)
                        st.success(f"저장 완료: {news['title'][:40]}...")
                    except Exception as e:
                        st.error(f"Supabase 저장 오류: {e}")


# --- 저장된 뉴스 보기 탭 ---
with tab2:
    st.subheader("저장된 뉴스 목록")

    try:
        result = supabase.table("news_history").select("*").order(
            "created_at",
            desc=True
        ).execute()

        data = result.data

        if data:
            df = pd.DataFrame(data)
            st.dataframe(df)

            for row in data:
                st.markdown("---")
                st.subheader(row.get("title", "제목 없음"))
                st.write(f"키워드: {row.get('keyword', '')}")
                st.write(f"출처: {row.get('source', '')} | 날짜: {row.get('news_date', '')}")
                st.write(row.get("summary", ""))
                st.markdown(f"[기사 원문 보기]({row.get('url', '')})")
        else:
            st.info("아직 저장된 뉴스가 없습니다.")

    except Exception as e:
        st.error(f"데이터 불러오기 오류: {e}")


# --- 통계 분석 탭 ---
with tab3:
    st.subheader("키워드별 뉴스 비중")

    try:
        result = supabase.table("news_history").select("*").execute()
        data = result.data

        if data:
            df = pd.DataFrame(data)

            keyword_counts = df["keyword"].value_counts()
            st.bar_chart(keyword_counts)

            st.subheader("날짜별 저장 건수")
            date_counts = df["news_date"].value_counts().sort_index()
            st.bar_chart(date_counts)
        else:
            st.info("통계를 표시할 데이터가 없습니다.")

    except Exception as e:
        st.error(f"통계 분석 오류: {e}")
